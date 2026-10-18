"""SQLite adapter for the consumer-owned Execution absence UoW."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.execution.absence_ports import (
    AbsenceAssignmentSnapshot,
    AbsenceAuditSnapshot,
    AbsenceCandidateFacts,
    AbsenceDayMutationHandle,
    AbsenceDaySnapshot,
    AbsenceMemberSnapshot,
    AbsenceReportSnapshot,
    AbsenceResponseSnapshot,
    AbsenceRoundSnapshot,
    AbsenceTargetSnapshot,
    AbsenceUnitOfWork,
    AbsenceViewSnapshot,
)
from backend.mutation_locks import MutationLockCommand
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.day_mutations import (
    DayMutationGuard,
    complete_day_mutation,
    guard_day_mutation,
)
from backend.persistence.exam_lifecycle import _SQLiteExamLifecycleExecution
from backend.persistence.models import (
    AbsenceAuditEvent,
    AbsenceReport,
    CandidateExamDay,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    ReplacementResponse,
)


class SQLiteAbsenceUnitOfWorkFactory:
    """Open one SQLite read or immediate-write transaction for an absence use case."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)

    def __call__(self) -> AbstractContextManager[SQLiteAbsenceUnitOfWork]:
        return self._write_scope()

    def read_scope(self) -> AbstractContextManager[SQLiteAbsenceUnitOfWork]:
        return self._read_scope()

    @contextmanager
    def _write_scope(self) -> Iterator[SQLiteAbsenceUnitOfWork]:
        with session_scope(self._db_path, begin_immediate=True) as session:
            yield SQLiteAbsenceUnitOfWork(session)

    @contextmanager
    def _read_scope(self) -> Iterator[SQLiteAbsenceUnitOfWork]:
        with read_session_scope(self._db_path) as session:
            yield SQLiteAbsenceUnitOfWork(session)


@dataclass
class _SQLiteAbsenceDayMutation:
    """Transaction-local persistence guard retained behind an opaque port handle."""

    session: Session
    guard: DayMutationGuard


class SQLiteAbsenceUnitOfWork(AbsenceUnitOfWork):
    """Materialize Execution facts and persist absence changes on one session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def assert_mutation_allowed(self, command: MutationLockCommand) -> None:
        _SQLiteExamLifecycleExecution(None, self._session).assert_mutation_allowed(command)

    def reports_for_committees(self, committee_ids: Sequence[int]) -> Sequence[AbsenceViewSnapshot]:
        if not committee_ids:
            return ()
        rows = self._session.scalars(
            select(AbsenceReport)
            .join(ExamDay, ExamDay.id == AbsenceReport.exam_day_id)
            .join(ExamRound, ExamRound.id == ExamDay.exam_round_id)
            .where(ExamRound.committee_id.in_(committee_ids))
            .order_by(AbsenceReport.reported_at.desc(), AbsenceReport.id.desc())
        ).all()
        return tuple(self._view(row) for row in rows)

    def report(self, report_id: int) -> AbsenceReportSnapshot | None:
        row = self._session.get(AbsenceReport, report_id)
        return self._report_snapshot(row) if row is not None else None

    def report_view(self, report_id: int) -> AbsenceViewSnapshot | None:
        row = self._session.get(AbsenceReport, report_id)
        return self._view(row) if row is not None else None

    def target(
        self, day_id: int, assignment_id: int | None, member_id: int | None
    ) -> AbsenceTargetSnapshot | None:
        assignment = (
            self._session.get(ExamDayAssignment, assignment_id)
            if assignment_id is not None
            else None
        )
        if assignment is None and member_id is not None:
            assignment = self._session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == day_id,
                    ExamDayAssignment.committee_member_id == member_id,
                )
            ).first()
        day = self._session.get(ExamDay, day_id)
        exam_round = self._session.get(ExamRound, day.exam_round_id) if day is not None else None
        target = (
            self._session.get(CommitteeMember, assignment.committee_member_id)
            if assignment is not None
            else None
        )
        if (
            day is None
            or exam_round is None
            or assignment is None
            or target is None
            or assignment.exam_day_id != day.id
        ):
            return None
        return AbsenceTargetSnapshot(
            day=self._day_snapshot(day),
            round=self._round_snapshot(exam_round),
            assignment=self._assignment_snapshot(assignment),
            target=self._member_snapshot(target),
        )

    def report_context(
        self, report_id: int
    ) -> tuple[AbsenceReportSnapshot, AbsenceDaySnapshot, AbsenceRoundSnapshot] | None:
        report = self._session.get(AbsenceReport, report_id)
        if report is None:
            return None
        day = self._session.get(ExamDay, report.exam_day_id)
        exam_round = self._session.get(ExamRound, day.exam_round_id) if day is not None else None
        if day is None or exam_round is None:
            return None
        return (
            self._report_snapshot(report),
            self._day_snapshot(day),
            self._round_snapshot(exam_round),
        )

    def response(self, response_id: int) -> AbsenceResponseSnapshot | None:
        row = self._session.get(ReplacementResponse, response_id)
        return self._response_snapshot(row) if row is not None else None

    def response_member_ids(self, report_id: int) -> frozenset[int]:
        return frozenset(
            self._session.scalars(
                select(ReplacementResponse.committee_member_id).where(
                    ReplacementResponse.absence_report_id == report_id
                )
            ).all()
        )

    def active_report_exists(self, assignment_id: int, statuses: frozenset[str]) -> bool:
        if not statuses:
            return False
        return (
            self._session.scalars(
                select(AbsenceReport.id).where(
                    AbsenceReport.exam_day_assignment_id == assignment_id,
                    AbsenceReport.status.in_(statuses),
                )
            ).first()
            is not None
        )

    def candidate_facts(
        self, day: AbsenceDaySnapshot, assignment: AbsenceAssignmentSnapshot
    ) -> AbsenceCandidateFacts:
        round_row = self._session.get(ExamRound, day.exam_round_id)
        if round_row is None:
            return AbsenceCandidateFacts((), frozenset(), frozenset(), frozenset(), frozenset())

        active_members = tuple(
            self._member_snapshot(member)
            for member in self._session.scalars(
                select(CommitteeMember).where(
                    CommitteeMember.committee_id == round_row.committee_id,
                    CommitteeMember.is_active == 1,
                )
            ).all()
        )
        assignments = self._session.scalars(
            select(ExamDayAssignment).where(ExamDayAssignment.exam_day_id == day.id)
        ).all()
        regular_ids = frozenset(
            row.committee_member_id for row in assignments if row.assignment_role == "examiner"
        )
        fallback_ids = frozenset(
            row.committee_member_id
            for row in assignments
            if row.assignment_role == "fallback"
            and row.day_part in (assignment.day_part, "full_day")
        )

        candidate_day_id = self._session.scalars(
            select(CandidateExamDay.id).where(
                CandidateExamDay.exam_round_id == day.exam_round_id,
                CandidateExamDay.date == day.date,
            )
        ).first()
        available_ids: frozenset[int] = frozenset()
        if candidate_day_id is not None:
            available_ids = frozenset(
                self._session.scalars(
                    select(MemberAvailability.committee_member_id).where(
                        MemberAvailability.candidate_exam_day_id == candidate_day_id,
                        MemberAvailability.availability.in_(("full_day", assignment.day_part)),
                    )
                ).all()
            )

        candidate_ids = tuple(member.id for member in active_members)
        conflict_free_ids = set(candidate_ids)
        if candidate_ids:
            other_assignments = self._session.execute(
                select(
                    ExamDay.date, ExamDayAssignment.committee_member_id, ExamDayAssignment.day_part
                )
                .join(ExamRound, ExamRound.id == ExamDay.exam_round_id)
                .join(ExamDayAssignment, ExamDayAssignment.exam_day_id == ExamDay.id)
                .where(
                    ExamRound.exam_half_year_id == round_row.exam_half_year_id,
                    ExamDay.id != day.id,
                    ExamDay.status == "confirmed",
                    ExamDay.date == day.date,
                    ExamDayAssignment.committee_member_id.in_(candidate_ids),
                )
            ).all()
            for other_date, member_id, other_part in other_assignments:
                if other_date == day.date and self._parts_overlap(assignment.day_part, other_part):
                    conflict_free_ids.discard(member_id)

        return AbsenceCandidateFacts(
            active_members=active_members,
            regular_member_ids=regular_ids,
            fallback_member_ids=fallback_ids,
            available_member_ids=available_ids,
            conflict_free_member_ids=frozenset(conflict_free_ids),
        )

    def member(self, member_id: int) -> AbsenceMemberSnapshot | None:
        row = self._session.get(CommitteeMember, member_id)
        return self._member_snapshot(row) if row is not None else None

    def assignment(self, assignment_id: int) -> AbsenceAssignmentSnapshot | None:
        row = self._session.get(ExamDayAssignment, assignment_id)
        return self._assignment_snapshot(row) if row is not None else None

    def assignment_slots(self, day_id: int) -> Sequence[str]:
        return tuple(
            self._session.scalars(
                select(ExamSlot.starts_at).where(ExamSlot.exam_day_id == day_id)
            ).all()
        )

    def notification_recipients(
        self,
        committee_id: int,
        *,
        roles: frozenset[str] | None = None,
        exclude_member_id: int | None = None,
    ) -> frozenset[int]:
        statement = select(CommitteeMember.id).where(
            CommitteeMember.committee_id == committee_id,
            CommitteeMember.is_active == 1,
        )
        if roles is not None:
            statement = statement.where(CommitteeMember.committee_role.in_(roles))
        if exclude_member_id is not None:
            statement = statement.where(CommitteeMember.id != exclude_member_id)
        return frozenset(self._session.scalars(statement).all())

    def guard_day_mutation(
        self,
        *,
        day_id: int,
        kind: str,
        entity_id: int,
        payload: dict[str, object],
        actor_member_id: int,
    ) -> AbsenceDayMutationHandle:
        day = self._session.get(ExamDay, day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        guard = guard_day_mutation(
            self._session,
            day=day,
            kind=kind,
            entity_id=entity_id,
            payload=cast(dict[str, object], payload),
            actor_member_id=actor_member_id,
        )
        return AbsenceDayMutationHandle(_SQLiteAbsenceDayMutation(self._session, guard))

    def complete_day_mutation(
        self,
        handle: AbsenceDayMutationHandle,
        *,
        actor_member_id: int,
        reason: str | None = None,
    ) -> None:
        mutation = cast(_SQLiteAbsenceDayMutation, handle)
        if mutation.session is not self._session:
            raise ValueError("Tagesänderung muss in derselben Transaktion abgeschlossen werden")
        complete_day_mutation(
            self._session,
            mutation.guard,
            actor_member_id=actor_member_id,
            reason=reason,
        )

    def insert_report(
        self,
        *,
        target: AbsenceTargetSnapshot,
        reported_by_member_id: int,
        reported_at: str,
        reason: str | None,
        status: str,
    ) -> AbsenceReportSnapshot:
        row = AbsenceReport(
            exam_day_id=target.day.id,
            exam_day_assignment_id=target.assignment.id,
            committee_member_id=target.target.id,
            reported_by_member_id=reported_by_member_id,
            reported_at=reported_at,
            reason=reason,
            status=status,
            version=0,
        )
        self._session.add(row)
        self._session.flush()
        return self._report_snapshot(row)

    def insert_response(
        self,
        *,
        report_id: int,
        member_id: int,
        requested_at: str,
        expires_at: str | None,
        urgent: bool,
    ) -> None:
        self._session.add(
            ReplacementResponse(
                absence_report_id=report_id,
                committee_member_id=member_id,
                response="pending",
                requested_at=requested_at,
                expires_at=expires_at,
                urgent=int(urgent),
            )
        )

    def insert_audit(
        self,
        *,
        report_id: int,
        actor_member_id: int,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        created_at: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            AbsenceAuditEvent(
                absence_report_id=report_id,
                actor_member_id=actor_member_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                details=(json.dumps(details, ensure_ascii=False) if details else None),
                created_at=created_at,
            )
        )

    def update_report(
        self,
        report_id: int,
        *,
        status: str,
        current: str,
        selected_replacement_member_id: int | None = None,
        update_selected_replacement: bool = False,
        increment_version: bool = True,
    ) -> AbsenceReportSnapshot:
        row = self._session.get(AbsenceReport, report_id)
        if row is None:
            raise ValueError("Ausfallmeldung nicht gefunden")
        row.status = status
        row.updated_at = current
        if update_selected_replacement:
            row.selected_replacement_member_id = selected_replacement_member_id
        if increment_version:
            row.version += 1
        self._session.flush()
        return self._report_snapshot(row)

    def update_response(
        self, response_id: int, *, response: str, responded_at: str
    ) -> AbsenceResponseSnapshot:
        row = self._session.get(ReplacementResponse, response_id)
        if row is None:
            raise ValueError("Ersatzanfrage nicht gefunden")
        row.response = response
        row.responded_at = responded_at
        self._session.flush()
        return self._response_snapshot(row)

    def update_assignment_member(
        self,
        assignment_id: int,
        member_id: int,
        *,
        fallback_status: str | None = None,
    ) -> None:
        row = self._session.get(ExamDayAssignment, assignment_id)
        if row is None:
            raise ValueError("Besetzung nicht gefunden")
        row.committee_member_id = member_id
        if fallback_status is not None:
            row.fallback_status = fallback_status

    def set_fallback_status(self, assignment_id: int, status: str) -> None:
        row = self._session.get(ExamDayAssignment, assignment_id)
        if row is None:
            raise ValueError("Besetzung nicht gefunden")
        row.fallback_status = status

    def _view(self, report: AbsenceReport) -> AbsenceViewSnapshot:
        context = self.report_context(report.id)
        if context is None:
            raise ValueError("Ausfallmeldung nicht gefunden")
        report_snapshot, day, exam_round = context
        assignment = self.assignment(report.exam_day_assignment_id)
        if assignment is None:
            raise ValueError("Besetzung nicht gefunden")
        responses = tuple(
            self._response_snapshot(row)
            for row in self._session.scalars(
                select(ReplacementResponse)
                .where(ReplacementResponse.absence_report_id == report.id)
                .order_by(ReplacementResponse.requested_at, ReplacementResponse.id)
            ).all()
        )
        audit = tuple(
            self._audit_snapshot(row)
            for row in self._session.scalars(
                select(AbsenceAuditEvent)
                .where(AbsenceAuditEvent.absence_report_id == report.id)
                .order_by(AbsenceAuditEvent.created_at, AbsenceAuditEvent.id)
            ).all()
        )
        return AbsenceViewSnapshot(report_snapshot, day, exam_round, assignment, responses, audit)

    @staticmethod
    def _parts_overlap(first: str, second: str) -> bool:
        return first == "full_day" or second == "full_day" or first == second

    @staticmethod
    def _report_snapshot(row: AbsenceReport) -> AbsenceReportSnapshot:
        return AbsenceReportSnapshot(
            id=row.id,
            exam_day_id=row.exam_day_id,
            exam_day_assignment_id=row.exam_day_assignment_id,
            committee_member_id=row.committee_member_id,
            reported_by_member_id=row.reported_by_member_id,
            reported_at=row.reported_at,
            reason=row.reason,
            status=row.status,
            selected_replacement_member_id=row.selected_replacement_member_id,
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _response_snapshot(row: ReplacementResponse) -> AbsenceResponseSnapshot:
        return AbsenceResponseSnapshot(
            id=row.id,
            absence_report_id=row.absence_report_id,
            committee_member_id=row.committee_member_id,
            response=row.response,
            requested_at=row.requested_at,
            expires_at=row.expires_at,
            urgent=bool(row.urgent),
            responded_at=row.responded_at,
        )

    @staticmethod
    def _audit_snapshot(row: AbsenceAuditEvent) -> AbsenceAuditSnapshot:
        return AbsenceAuditSnapshot(
            id=row.id,
            actor_member_id=row.actor_member_id,
            event_type=row.event_type,
            from_status=row.from_status,
            to_status=row.to_status,
            details=row.details,
            created_at=row.created_at,
        )

    @staticmethod
    def _day_snapshot(row: ExamDay) -> AbsenceDaySnapshot:
        return AbsenceDaySnapshot(
            id=row.id,
            exam_round_id=row.exam_round_id,
            date=row.date,
            status=row.status,
            closure_status=row.closure_status,
            revision=row.revision,
        )

    @staticmethod
    def _round_snapshot(row: ExamRound) -> AbsenceRoundSnapshot:
        return AbsenceRoundSnapshot(
            id=row.id,
            committee_id=row.committee_id,
            exam_half_year_id=row.exam_half_year_id,
            status=row.status,
        )

    @staticmethod
    def _assignment_snapshot(row: ExamDayAssignment) -> AbsenceAssignmentSnapshot:
        return AbsenceAssignmentSnapshot(
            id=row.id,
            exam_day_id=row.exam_day_id,
            committee_member_id=row.committee_member_id,
            assignment_role=row.assignment_role,
            day_part=row.day_part,
            fallback_status=row.fallback_status,
        )

    @staticmethod
    def _member_snapshot(row: CommitteeMember) -> AbsenceMemberSnapshot:
        return AbsenceMemberSnapshot(
            id=row.id,
            representing_side=row.representing_side,
            is_active=bool(row.is_active),
        )
