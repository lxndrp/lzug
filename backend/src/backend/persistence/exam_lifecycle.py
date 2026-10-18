"""SQLite composition for the Application-owned exam lifecycle UoW."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.errors import ExamRoundConflictError
from backend.mutation_locks import MutationLockCommand, MutationLockKind
from backend.persistence.application_consequence_store import SQLiteLifecycleConsequenceReadPort
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.calendar_lifecycle import SQLiteCalendarLifecycleWork
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.day_closure_snapshot import SQLiteExamDayClosureReadSnapshotReader
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity_lifecycle import SQLiteIdentityLifecycleWork
from backend.persistence.models import (
    AbsenceReport,
    ExamDay,
    ExamDayAssignment,
    ExamDayClosure,
    ExamDayExport,
    ExamProtocol,
    ExamResult,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundReopening,
    RoundCandidate,
)
from backend.persistence.planning_lifecycle import SQLitePlanningLifecycleWork
from backend.persistence.round_lifecycle_snapshot import SQLiteExamRoundLifecycleReadSnapshotReader


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class SQLiteExamLifecycleUnitOfWorkFactory:
    """Compose domain-owned ports over one SQLite transaction."""

    def __init__(
        self,
        execution_factory: SQLiteExecutionUnitOfWorkFactory,
        assessment_factory: SQLiteAssessmentUnitOfWorkFactory,
        db_path: Path = DEFAULT_DB_PATH,
        assessment_lifecycle_factory: Callable[[Session], object] | None = None,
    ) -> None:
        self._execution_factory = execution_factory
        self._assessment_factory = assessment_factory
        self._db_path = Path(db_path)
        self._assessment_lifecycle_factory = assessment_lifecycle_factory

    def __call__(self) -> AbstractContextManager[_SQLiteExamLifecycleUnitOfWork]:
        return self._scope()

    def read_scope(self) -> AbstractContextManager[_SQLiteExamLifecycleUnitOfWork]:
        return self._read_scope()

    def in_session(self, session: Session) -> _SQLiteExamLifecycleUnitOfWork:
        """Compose both domain capabilities over an already owned transaction."""
        return _SQLiteExamLifecycleUnitOfWork(
            self._execution_factory.in_session(session),
            self._assessment_factory.in_session(session),
            session,
            (
                self._assessment_lifecycle_factory(session)
                if self._assessment_lifecycle_factory is not None
                else None
            ),
            SQLitePlanningLifecycleWork(session),
            SQLiteIdentityLifecycleWork(session),
            SQLiteCalendarLifecycleWork(session),
            SQLiteLifecycleConsequenceReadPort(session),
        )

    @contextmanager
    def _scope(self) -> Iterator[_SQLiteExamLifecycleUnitOfWork]:
        with session_scope(self._db_path, begin_immediate=True) as session:
            yield self.in_session(session)

    @contextmanager
    def _read_scope(self) -> Iterator[_SQLiteExamLifecycleUnitOfWork]:
        with read_session_scope(self._db_path) as session:
            yield self.in_session(session)


class _SQLiteExamLifecycleUnitOfWork:
    """Provide detached domain capabilities without exposing the SQLAlchemy session."""

    def __init__(
        self,
        execution,
        assessment,
        session: Session,
        assessment_lifecycle,
        planning_lifecycle,
        identity_lifecycle,
        calendar_lifecycle,
        consequences,
    ) -> None:
        self._execution = _SQLiteExamLifecycleExecution(execution, session)
        self._assessment = assessment
        self._assessment_lifecycle = assessment_lifecycle
        self._planning_lifecycle = planning_lifecycle
        self._identity_lifecycle = identity_lifecycle
        self._calendar_lifecycle = calendar_lifecycle
        self._consequences = consequences

    @property
    def execution(self):
        return self._execution

    @property
    def assessment(self):
        return self._assessment

    @property
    def assessment_lifecycle(self):
        return self._assessment_lifecycle

    @property
    def planning_lifecycle(self):
        return self._planning_lifecycle

    @property
    def identity_lifecycle(self):
        return self._identity_lifecycle

    @property
    def calendar_lifecycle(self):
        return self._calendar_lifecycle

    @property
    def consequences(self):
        return self._consequences


class _SQLiteExamLifecycleExecution:
    """Add explicit lifecycle commands to the ordinary Execution UoW port."""

    def __init__(self, execution, session: Session) -> None:
        self._execution = execution
        self._session = session

    def __getattr__(self, name):
        return getattr(self._execution, name)

    def exam_day_round_id(self, day_id: int) -> int | None:
        day = self._session.get(ExamDay, day_id)
        return day.exam_round_id if day is not None else None

    def exam_day_ids_for_round(self, round_id: int) -> tuple[int, ...]:
        return tuple(
            self._session.scalars(
                select(ExamDay.id).where(ExamDay.exam_round_id == round_id).order_by(ExamDay.id)
            )
        )

    def assert_mutation_allowed(self, command: MutationLockCommand) -> None:
        planning = SQLitePlanningLifecycleWork(self._session)
        resolved = self._round_mutation_token(command, planning)
        if resolved is None:
            return
        round_id, token = resolved
        exam_round = planning.round_lifecycle_snapshot(round_id)
        if exam_round is None:
            raise ValueError("Prüfungsrunde nicht gefunden")
        if exam_round.lifecycle_status == "open":
            return
        if exam_round.lifecycle_status != "reopening":
            raise ExamRoundConflictError(
                "Die Prüfungsrunde ist fachlich beendet und für Änderungen gesperrt"
            )
        reopening = self._session.scalar(
            select(ExamRoundReopening).where(
                ExamRoundReopening.exam_round_id == round_id,
                ExamRoundReopening.status == "open",
            )
        )
        if reopening is None or token not in set(json.loads(reopening.scope_json)):
            raise ExamRoundConflictError(
                "Diese Daten gehören nicht zum freigegebenen Korrekturumfang"
            )

    def _round_mutation_token(self, command: MutationLockCommand, planning):
        kind = command.kind
        identifier = command.resource_id
        payload = command.payload
        if kind is MutationLockKind.EXAM_ROUND:
            return (identifier, f"planning:{identifier}") if identifier is not None else None
        if kind is MutationLockKind.PLANNING_PROPOSAL:
            round_id = payload.get("round_id")
            return (round_id, f"planning:{round_id}") if _is_int(round_id) else None
        planning_resources = {
            MutationLockKind.PLANNING_SETTINGS: "planning-settings",
            MutationLockKind.CANDIDATE_EXAM_DAY: "candidate-exam-days",
            MutationLockKind.MEMBER_AVAILABILITY: "member-availabilities",
            MutationLockKind.ROUND_CANDIDATE: "round-candidates",
        }
        if kind in planning_resources:
            target = planning.mutation_target(planning_resources[kind], identifier, dict(payload))
            if target is None:
                return None
            round_id, entity_id = target
            token_kind = (
                "availability"
                if kind is MutationLockKind.MEMBER_AVAILABILITY
                else (
                    "candidate_assignment"
                    if kind is MutationLockKind.ROUND_CANDIDATE
                    else "planning"
                )
            )
            return round_id, f"{token_kind}:{entity_id}"
        if kind is MutationLockKind.CONFIRMED_PLAN_DAY and identifier is not None:
            day = self._session.get(ExamDay, identifier)
            return (day.exam_round_id, f"exam_day:{identifier}") if day else None
        if kind is MutationLockKind.EXAM_PROTOCOL and identifier is not None:
            slot_id = self._session.scalar(
                select(ExamProtocol.exam_slot_id).where(ExamProtocol.id == identifier)
            )
            round_id = planning.round_id_for_slot(slot_id) if slot_id is not None else None
            return (round_id, f"exam_protocol:{identifier}") if round_id else None
        if kind is MutationLockKind.EXAM_RESULT and identifier is not None:
            round_id = self._session.scalar(
                select(RoundCandidate.exam_round_id)
                .join(ExamResult, ExamResult.round_candidate_id == RoundCandidate.id)
                .where(ExamResult.id == identifier)
            )
            return (round_id, f"exam_result:{identifier}") if round_id else None
        if kind is MutationLockKind.ABSENCE_REPORT:
            return self._absence_report_mutation_token(identifier, payload)
        return None

    def _absence_report_mutation_token(self, identifier, payload):
        if identifier is not None:
            round_id = self._session.scalar(
                select(ExamDay.exam_round_id)
                .join(AbsenceReport, AbsenceReport.exam_day_id == ExamDay.id)
                .where(AbsenceReport.id == identifier)
            )
            return (round_id, f"absence:{identifier}") if round_id else None
        day_id = payload.get("exam_day_id")
        if not _is_int(day_id):
            return None
        round_id = self._session.scalar(select(ExamDay.exam_round_id).where(ExamDay.id == day_id))
        assignment_id = payload.get("exam_day_assignment_id")
        if assignment_id is None and payload.get("committee_member_id") is not None:
            assignment_id = self._session.scalar(
                select(ExamDayAssignment.id).where(
                    ExamDayAssignment.exam_day_id == day_id,
                    ExamDayAssignment.committee_member_id == payload["committee_member_id"],
                )
            )
        if not _is_int(assignment_id):
            return (round_id, "unresolved_absence_report") if round_id else None
        return (round_id, f"staffing:{assignment_id}") if round_id else None

    def day_closure_read_snapshot(self, day_id: int):
        return SQLiteExamDayClosureReadSnapshotReader(self._session).load_day_closure_read_snapshot(
            day_id
        )

    def round_lifecycle_read_snapshot(self, round_id: int):
        return SQLiteExamRoundLifecycleReadSnapshotReader(
            self._session
        ).load_round_lifecycle_read_snapshot(round_id)

    def lifecycle_dependency_counts(self, round_id: int) -> dict[str, int]:
        day_ids = select(ExamDay.id).where(ExamDay.exam_round_id == round_id)
        return {
            "Prüfungstage": self._count(ExamDay, ExamDay.exam_round_id == round_id),
            "Ausfallvorgänge": self._count(AbsenceReport, AbsenceReport.exam_day_id.in_(day_ids)),
            "Lebenszyklushistorie": self._count(
                ExamRoundDecision, ExamRoundDecision.exam_round_id == round_id
            ),
        }

    def _count(self, model, criterion) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(model).where(criterion)) or 0
        )

    def record_round_export(self, round_id: int, actor_member_id: int, *, human: bool, facts):
        exam_round = facts.round
        decision = self._session.scalar(
            select(ExamRoundDecision)
            .where(ExamRoundDecision.exam_round_id == round_id)
            .order_by(
                (ExamRoundDecision.status == "current").desc(),
                ExamRoundDecision.id.desc(),
            )
        )
        row = ExamRoundExport(
            exam_round_id=round_id,
            decision_id=decision.id if decision else None,
            round_revision=exam_round.revision,
            export_kind="human" if human else "machine",
            lifecycle_status=exam_round.lifecycle_status,
            generated_by_member_id=actor_member_id,
            generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        )
        self._session.add(row)
        self._session.flush()
        reader = SQLiteExamRoundLifecycleReadSnapshotReader(self._session)
        lifecycle_snapshot = reader.load_round_lifecycle_read_snapshot(round_id)
        export_snapshot = reader.load_round_lifecycle_export_snapshot(round_id)
        if lifecycle_snapshot is None:
            raise ValueError("Prüfungsrunde nicht gefunden")
        export_record = {
            "id": row.id,
            "decision_id": row.decision_id,
            "round_revision": row.round_revision,
            "export_kind": row.export_kind,
            "lifecycle_status": row.lifecycle_status,
            "generated_by_member_id": row.generated_by_member_id,
            "generated_at": row.generated_at,
            "superseded_at": row.superseded_at,
            "superseded_by_revision": row.superseded_by_revision,
            "obsolete": row.superseded_at is not None,
        }
        return lifecycle_snapshot, export_snapshot, export_record

    def record_day_export(self, scope, day_id: int, *, human: bool, facts):
        if not scope.can_read_committee(facts.committee_id):
            raise PermissionError("Forbidden.")
        actor_id = scope.member_for_committee(facts.committee_id)
        if actor_id is None:
            raise PermissionError("Forbidden.")
        reader = SQLiteExamDayClosureReadSnapshotReader(self._session)
        day = reader.load_day_closure_read_snapshot(day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        latest_closure = self._session.scalar(
            select(ExamDayClosure)
            .where(ExamDayClosure.exam_day_id == day_id)
            .order_by(
                (ExamDayClosure.status == "current").desc(),
                ExamDayClosure.id.desc(),
            )
        )
        self._session.add(
            ExamDayExport(
                exam_day_id=day_id,
                closure_id=latest_closure.id if latest_closure is not None else None,
                export_kind="human" if human else "machine",
                status=day.day["closure_status"],
                generated_by_member_id=actor_id,
                generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            )
        )
        self._session.flush()
        snapshot = reader.load_day_closure_read_snapshot(day_id)
        if snapshot is None:
            raise ValueError("Prüfungstag nicht gefunden")
        return snapshot

    def evaluate_round_decision(self, service, scope, command, decision_type, facts):
        return service.evaluate_decision_intent(self._session, scope, command, decision_type, facts)

    def replay_round_decision(self, service, scope, intent, facts):
        return service.replay_decision_intent(self._session, scope, intent, facts)

    def refresh_round_decision_snapshot(self, service, intent, facts):
        return service.refresh_decision_snapshot(self._session, intent, facts)

    def apply_round_decision(self, service, scope, intent, facts, cancelled_recipients):
        return service.apply_decision_intent(
            self._session, scope, intent, facts, cancelled_recipients
        )

    def evaluate_round_reopen(self, service, scope, command, facts):
        return service.evaluate_reopen_intent(self._session, scope, command, facts)

    def round_reopening_impact(self, service, scope, facts, raw_scope):
        return service.reopening_impact_from_facts(self._session, scope, facts, raw_scope)

    def replay_round_reopen(self, service, scope, intent, facts):
        return service.replay_reopen_intent(self._session, scope, intent, facts)

    def apply_round_reopen(self, service, scope, intent, facts):
        return service.apply_reopen_intent(self._session, scope, intent, facts)

    def evaluate_day_close(self, service, scope, day_id, command, facts):
        return service.evaluate_close_intent(self._session, scope, day_id, command, facts)

    def apply_day_close(self, service, scope, intent, facts):
        return service.apply_close_intent(self._session, scope, intent, facts)

    def day_reopening_impact(self, service, scope, day_id, raw_scope, facts):
        return service.reopening_impact_from_facts(self._session, scope, day_id, raw_scope, facts)

    def evaluate_day_reopen(self, service, scope, day_id, command, facts):
        return service.evaluate_reopen_intent(self._session, scope, day_id, command, facts)

    def begin_day_reopen(self, service, intent):
        return service.begin_reopen_intent(self._session, intent)

    def complete_day_reopen(self, service, scope, handle, facts, assessment_corrections):
        return service.complete_reopen_intent(
            self._session, scope, handle, facts, assessment_corrections
        )

    def replay_day_reopen(self, service, scope, intent, facts):
        return service.replay_reopen_intent(self._session, scope, intent, facts)
