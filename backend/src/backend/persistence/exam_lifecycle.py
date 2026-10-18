"""SQLite composition for the Application-owned exam lifecycle UoW."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import replace
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
from backend.persistence.day_lifecycle_snapshot import SQLiteExamDayLifecycleSnapshotReader
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity_lifecycle import SQLiteIdentityLifecycleWork
from backend.persistence.models import (
    AbsenceReport,
    ExamDay,
    ExamDayAssignment,
    ExamDayAuditEvent,
    ExamDayClosure,
    ExamDayExport,
    ExamDayReopening,
    ExamDayTask,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolEntry,
    ExamProtocolParticipant,
    ExamProtocolRevision,
    ExamResult,
    ExamRoundAuditEvent,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundReopening,
    ExamRoundTask,
    RoundCandidate,
)
from backend.persistence.planning_lifecycle import SQLitePlanningLifecycleWork
from backend.persistence.round_lifecycle_snapshot import SQLiteExamRoundLifecycleReadSnapshotReader


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _day_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _day_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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

    def day_lifecycle_snapshot(self, day_id: int):
        return SQLiteExamDayLifecycleSnapshotReader(self._session).load_exam_day_lifecycle_snapshot(
            day_id
        )

    def round_lifecycle_read_snapshot(self, round_id: int):
        return SQLiteExamRoundLifecycleReadSnapshotReader(
            self._session
        ).load_round_lifecycle_read_snapshot(round_id)

    def round_lifecycle_export_snapshot(self, round_id: int):
        return SQLiteExamRoundLifecycleReadSnapshotReader(
            self._session
        ).load_round_lifecycle_export_snapshot(round_id)

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

    def apply_round_decision(self, intent, facts, cancelled_recipients):
        """Persist a detached round decision and its audit/task consequences."""

        def encode(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        previous = self._session.scalar(
            select(ExamRoundDecision)
            .where(ExamRoundDecision.exam_round_id == intent.round_id)
            .order_by((ExamRoundDecision.status == "current").desc(), ExamRoundDecision.id.desc())
        )
        if previous is not None:
            previous.status = "superseded"
        reopening = (
            self._session.get(ExamRoundReopening, intent.reopening_id)
            if intent.reopening_id
            else None
        )
        decision = ExamRoundDecision(
            exam_round_id=intent.round_id,
            decision_type=intent.decision_type,
            requested_revision=intent.expected_revision,
            resulting_revision=intent.expected_revision + 1,
            actor_member_id=intent.actor_member_id,
            reason=intent.reason,
            checklist_json=encode(intent.evaluation["items"]),
            snapshot_json=encode(intent.snapshot),
            previous_decision_id=previous.id if previous else None,
            status="current",
            command_fingerprint=intent.command_fingerprint,
            decided_at=intent.now,
        )
        self._session.add(decision)
        self._session.flush()
        lifecycle_status = "closed" if intent.decision_type == "close" else "cancelled"
        updated = replace(
            facts.round,
            revision=intent.expected_revision + 1,
            lifecycle_status=lifecycle_status,
        )
        if intent.decision_type == "cancel":
            for day in self._session.scalars(
                select(ExamDay).where(ExamDay.exam_round_id == intent.round_id)
            ):
                day.status = "cancelled"
                day.updated_at = intent.now
        if reopening is not None:
            reopening.status = "completed"
            reopening.completed_at = intent.now
            for task in self._session.scalars(
                select(ExamRoundTask).where(
                    ExamRoundTask.reopening_id == reopening.id,
                    ExamRoundTask.status == "open",
                )
            ):
                task.status = "completed"
                task.completed_at = intent.now
        self._session.add(
            ExamRoundAuditEvent(
                exam_round_id=intent.round_id,
                round_revision=updated.revision,
                event_type=(
                    ("reclosed" if intent.decision_type == "close" else "recancelled")
                    if reopening
                    else lifecycle_status
                ),
                actor_member_id=intent.actor_member_id,
                decision_id=decision.id,
                reopening_id=reopening.id if reopening else None,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json if reopening else "[]",
                created_at=intent.now,
            )
        )
        recipients = cancelled_recipients or set()
        return {
            "committee_id": intent.committee_id if recipients else None,
            "round_id": intent.round_id if recipients else None,
            "recipient_member_ids": frozenset(recipients),
            "title": "Prüfungsrunde abgesagt" if recipients else "",
            "message": (
                "Die Prüfungsrunde wurde vollständig und begründet abgesagt." if recipients else ""
            ),
            "origin_key": f"exam-round-decision:{decision.id}:cancelled" if recipients else "",
        }

    def apply_round_reopen(self, intent, facts):
        """Persist reopening evidence and correction tasks in the caller's UoW."""

        def encode(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        previous = self._session.scalar(
            select(ExamRoundDecision)
            .where(ExamRoundDecision.exam_round_id == intent.round_id)
            .order_by((ExamRoundDecision.status == "current").desc(), ExamRoundDecision.id.desc())
        )
        if previous is not None:
            previous.status = "superseded"
        reopening = ExamRoundReopening(
            exam_round_id=intent.round_id,
            previous_decision_id=previous.id if previous else None,
            requested_revision=intent.expected_revision,
            resulting_revision=intent.expected_revision + 1,
            occasion=intent.occasion,
            source=intent.source,
            reason=intent.reason,
            requested_scope_json=encode(intent.impact["requested_scope"]),
            scope_json=encode(intent.impact["expanded_scope"]),
            impacts_json=encode(intent.impact["impacts"]),
            actor_member_id=intent.actor_member_id,
            status="open",
            command_fingerprint=intent.command_fingerprint,
            opened_at=intent.now,
        )
        self._session.add(reopening)
        self._session.flush()
        updated = replace(
            facts.round,
            revision=intent.expected_revision + 1,
            lifecycle_status="reopening",
        )
        for export in self._session.scalars(
            select(ExamRoundExport).where(
                ExamRoundExport.exam_round_id == updated.id,
                ExamRoundExport.superseded_at.is_(None),
            )
        ):
            export.superseded_at = intent.now
            export.superseded_by_revision = updated.revision
        recipients = set(intent.impact["impacts"]["recipient_member_ids"])
        for recipient_id in sorted(recipients):
            self._session.add(
                ExamRoundTask(
                    exam_round_id=intent.round_id,
                    reopening_id=reopening.id,
                    recipient_member_id=recipient_id,
                    task_type="reconfirmation",
                    origin_key=f"exam-round-reopening:{reopening.id}:affected",
                    details_json=encode(
                        {"reason": intent.reason, "scope": intent.impact["expanded_scope"]}
                    ),
                    status="open",
                    created_at=intent.now,
                )
            )
        for result_id in intent.impact["impacts"]["ihk_processed_result_ids"]:
            for recipient_id in facts.management_member_ids:
                self._session.add(
                    ExamRoundTask(
                        exam_round_id=intent.round_id,
                        reopening_id=reopening.id,
                        recipient_member_id=recipient_id,
                        task_type="ihk_clarification",
                        origin_key=f"exam-round-reopening:{reopening.id}:ihk:{result_id}",
                        details_json=encode({"exam_result_id": result_id, "reason": intent.reason}),
                        status="open",
                        created_at=intent.now,
                    )
                )
        self._session.add(
            ExamRoundAuditEvent(
                exam_round_id=intent.round_id,
                round_revision=updated.revision,
                event_type="reopened",
                actor_member_id=intent.actor_member_id,
                reopening_id=reopening.id,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json,
                created_at=intent.now,
            )
        )
        return {
            "committee_id": updated.committee_id if recipients else None,
            "round_id": intent.round_id if recipients else None,
            "recipient_member_ids": frozenset(recipients),
            "title": "Prüfungsrunde zur Korrektur wieder geöffnet" if recipients else "",
            "message": (
                "Von Ihnen erfasste oder bestätigte Daten sind von einer begründeten "
                "Korrektur betroffen."
                if recipients
                else ""
            ),
            "origin_key": f"exam-round-reopening:{reopening.id}:affected" if recipients else "",
        }

    def apply_day_close(self, intent):
        day = self._session.get(ExamDay, intent.day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        if intent.replayed:
            return {"day_id": day.id}
        reopening = (
            self._session.get(ExamDayReopening, intent.reopening_id)
            if intent.reopening_id
            else None
        )
        previous = self._session.scalar(
            select(ExamDayClosure)
            .where(ExamDayClosure.exam_day_id == day.id)
            .order_by((ExamDayClosure.status == "current").desc(), ExamDayClosure.id.desc())
        )
        if previous is not None:
            previous.status = "superseded"
        now = _day_now()
        closure = ExamDayClosure(
            exam_day_id=day.id,
            requested_revision=day.revision,
            resulting_revision=day.revision + 1,
            closure_type=intent.closure_type,
            actor_member_id=intent.actor_member_id,
            reason=intent.reason,
            clarification_attempts=intent.clarification_attempts,
            checklist_json=_day_json(intent.evaluation["items"]),
            warnings_json=_day_json(intent.evaluation["warnings"]),
            protocol_references_json=_day_json(intent.evaluation["protocol_references"]),
            result_references_json=_day_json(intent.evaluation["result_references"]),
            previous_closure_id=previous.id if previous else None,
            status="current",
            command_fingerprint=intent.command_fingerprint,
            closed_at=now,
        )
        self._session.add(closure)
        self._session.flush()
        day.revision += 1
        day.closure_status = "closed" if intent.closure_type == "regular" else "closed_exception"
        day.updated_at = now
        recipients: set[int] = set()
        jobs: list[dict[str, object]] = []
        if reopening is not None:
            reopening.status, reopening.completed_at = "completed", now
            for task in self._session.scalars(
                select(ExamDayTask).where(
                    ExamDayTask.reopening_id == reopening.id, ExamDayTask.status == "open"
                )
            ):
                task.status, task.completed_at = "completed", now
            recipients.update(json.loads(reopening.impacts_json).get("recipient_member_ids", []))
        event_type = (
            "reclosed"
            if reopening
            else ("closed_exception" if intent.closure_type == "exception" else "closed")
        )
        self._session.add(
            ExamDayAuditEvent(
                exam_day_id=day.id,
                day_revision=day.revision,
                event_type=event_type,
                actor_member_id=intent.actor_member_id,
                closure_id=closure.id,
                reopening_id=reopening.id if reopening else None,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json if reopening else "[]",
                created_at=now,
            )
        )
        if intent.closure_type == "exception":
            candidate = intent.evaluation["exception_candidate"]
            recipients = {candidate["committee_member_id"]}
            self._session.add(
                ExamDayTask(
                    exam_day_id=day.id,
                    recipient_member_id=candidate["committee_member_id"],
                    task_type="protocol_follow_up",
                    origin_key=f"exam-day-closure:{closure.id}:protocol-follow-up",
                    exam_protocol_revision_id=candidate["exam_protocol_revision_id"],
                    details_json=_day_json(
                        {
                            "reason": intent.reason,
                            "clarification_attempts": intent.clarification_attempts,
                            "exam_protocol_id": candidate["exam_protocol_id"],
                        }
                    ),
                    status="open",
                    created_at=now,
                )
            )
            jobs.append(
                {
                    "recipient_member_ids": recipients,
                    "event_type": "exam_day_protocol_follow_up",
                    "title": "Protokollreaktion ausstehend",
                    "message": (
                        "Ein Prüfungstag wurde mit Ausnahme geschlossen. Bitte reagieren Sie "
                        "auf den unveränderten Protokollstand."
                    ),
                    "origin_key": f"exam-day-closure:{closure.id}:protocol-follow-up",
                }
            )
        elif reopening is not None and recipients:
            jobs.append(
                {
                    "recipient_member_ids": recipients,
                    "event_type": "exam_day_reclosed",
                    "title": "Prüfungstag erneut abgeschlossen",
                    "message": "Der korrigierte Prüfungstag wurde erneut formal abgeschlossen.",
                    "origin_key": f"exam-day-reopening:{reopening.id}:reclosed",
                }
            )
        return {
            "committee_id": intent.committee_id,
            "round_id": intent.round_id,
            "day_id": day.id,
            "notification_jobs": tuple(jobs),
        }

    def begin_day_reopen(self, intent):
        if intent.replayed:
            raise ValueError("A replayed reopening has no apply phase")
        day = self._session.get(ExamDay, intent.day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        if day.revision != intent.expected_revision or day.closure_status not in {
            "closed",
            "closed_exception",
            "historical",
        }:
            return {"conflict": "Der Prüfungstag wurde zwischenzeitlich geändert"}
        previous = self._session.scalar(
            select(ExamDayClosure)
            .where(ExamDayClosure.exam_day_id == day.id)
            .order_by((ExamDayClosure.status == "current").desc(), ExamDayClosure.id.desc())
        )
        if previous is not None:
            previous.status = "superseded"
        now = _day_now()
        reopening = ExamDayReopening(
            exam_day_id=day.id,
            previous_closure_id=previous.id if previous else None,
            requested_revision=day.revision,
            resulting_revision=day.revision + 1,
            occasion=intent.occasion,
            source=intent.source,
            reason=intent.reason,
            requested_scope_json=_day_json(intent.impact["requested_scope"]),
            scope_json=_day_json(intent.impact["expanded_scope"]),
            completed_scope_json="[]",
            impacts_json=_day_json(intent.impact["impacts"]),
            actor_member_id=intent.actor_member_id,
            status="open",
            command_fingerprint=intent.command_fingerprint,
            opened_at=now,
        )
        self._session.add(reopening)
        self._session.flush()
        day.revision += 1
        day.closure_status, day.updated_at = "reopening", now
        return {"reopening_id": reopening.id, "now": now}

    def complete_day_reopen(self, handle, facts, assessment_corrections):
        intent = handle.intent
        day = self._session.get(ExamDay, intent.day_id)
        reopening = self._session.get(ExamDayReopening, handle.reopening_id)
        if day is None or reopening is None:
            return {"conflict": "Der Wiederöffnungsstand ist inkonsistent"}
        for protocol_id in intent.impact["impacts"]["exam_protocol_ids"]:
            protocol = self._session.get(ExamProtocol, protocol_id)
            current = self._session.scalar(
                select(ExamProtocolRevision).where(
                    ExamProtocolRevision.exam_protocol_id == protocol.id,
                    ExamProtocolRevision.version == protocol.current_version,
                )
            )
            if current is None:
                raise ValueError("Der aktuelle Protokollstand fehlt")
            request = ExamProtocolCorrectionRequest(
                exam_protocol_id=protocol.id,
                exam_protocol_revision_id=current.id,
                requested_by_member_id=intent.actor_member_id,
                reason=intent.reason,
                status="opened",
                requested_at=handle.now,
                opened_by_member_id=intent.actor_member_id,
                opened_at=handle.now,
                reopening_reference=f"exam-day-reopening:{reopening.id}",
            )
            self._session.add(request)
            self._session.flush()
            revision = ExamProtocolRevision(
                exam_protocol_id=protocol.id,
                version=current.version + 1,
                declaration=current.declaration,
                workflow_state="correction_open",
                previous_revision_id=current.id,
                correction_request_id=request.id,
                changed_by_member_id=intent.actor_member_id,
                change_reason=intent.reason,
                created_at=handle.now,
            )
            self._session.add(revision)
            self._session.flush()
            for entry in self._session.scalars(
                select(ExamProtocolEntry).where(
                    ExamProtocolEntry.exam_protocol_revision_id == current.id
                )
            ):
                self._session.add(
                    ExamProtocolEntry(
                        exam_protocol_revision_id=revision.id,
                        category=entry.category,
                        statement=entry.statement,
                        occurred_from=entry.occurred_from,
                        occurred_to=entry.occurred_to,
                        recorded_by_member_id=entry.recorded_by_member_id,
                        created_at=entry.created_at,
                    )
                )
            protocol.current_version, protocol.updated_at = revision.version, handle.now
            participants = set(
                self._session.scalars(
                    select(ExamProtocolParticipant.committee_member_id).where(
                        ExamProtocolParticipant.exam_protocol_id == protocol.id
                    )
                )
            )
            self._persist_day_tasks(
                day.id,
                reopening.id,
                participants,
                "protocol_reconfirmation",
                f"exam-day-reopening:{reopening.id}:protocol:{protocol.id}",
                intent.reason,
                handle.now,
                protocol_revision_id=revision.id,
            )
        for result_id in intent.impact["impacts"]["exam_result_ids"]:
            correction = assessment_corrections.get(result_id)
            if correction is None or correction["determination_id"] is None:
                continue
            determination_id = correction["determination_id"]
            for recipients, task_type, origin in (
                (
                    set(correction["participant_member_ids"]),
                    "result_reconfirmation",
                    f"exam-day-reopening:{reopening.id}:result:{result_id}",
                ),
                (
                    set(facts.management_member_ids),
                    "result_recommunication",
                    f"exam-day-reopening:{reopening.id}:recommunicate:{result_id}",
                ),
                (
                    set(facts.management_member_ids),
                    "ihk_clarification",
                    f"exam-day-reopening:{reopening.id}:ihk:{result_id}",
                ),
            ):
                if task_type == "result_recommunication" and not correction["communicated"]:
                    continue
                if task_type == "ihk_clarification" and not correction["ihk_processed"]:
                    continue
                self._persist_day_tasks(
                    day.id,
                    reopening.id,
                    recipients,
                    task_type,
                    origin,
                    intent.reason,
                    handle.now,
                    determination_id=determination_id,
                )
        self._session.add(
            ExamDayAuditEvent(
                exam_day_id=day.id,
                day_revision=day.revision,
                event_type="reopened",
                actor_member_id=intent.actor_member_id,
                reopening_id=reopening.id,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json,
                created_at=handle.now,
            )
        )
        recipients = set(intent.impact["impacts"]["recipient_member_ids"])
        jobs = (
            (
                {
                    "recipient_member_ids": recipients,
                    "event_type": "exam_day_reopened",
                    "title": "Prüfungstag zur Korrektur wieder geöffnet",
                    "message": (
                        "Von Ihnen erfasste oder bestätigte Daten sind von einer begründeten "
                        "Korrektur betroffen."
                    ),
                    "origin_key": f"exam-day-reopening:{reopening.id}:affected",
                },
            )
            if recipients
            else ()
        )
        return {
            "committee_id": intent.committee_id,
            "round_id": intent.round_id,
            "day_id": day.id,
            "notification_jobs": jobs,
        }

    def _persist_day_tasks(
        self,
        day_id,
        reopening_id,
        recipients,
        task_type,
        origin_key,
        reason,
        now,
        *,
        protocol_revision_id=None,
        determination_id=None,
    ):
        for member_id in recipients:
            self._session.add(
                ExamDayTask(
                    exam_day_id=day_id,
                    reopening_id=reopening_id,
                    recipient_member_id=member_id,
                    task_type=task_type,
                    origin_key=origin_key,
                    exam_protocol_revision_id=protocol_revision_id,
                    result_determination_id=determination_id,
                    details_json=_day_json({"reason": reason}),
                    status="open",
                    created_at=now,
                )
            )
