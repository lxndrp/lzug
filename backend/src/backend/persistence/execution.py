"""SQLite adapter for Execution attendance and exam-start use cases."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.day_mutations import (
    DayMutationGuard,
    complete_day_mutation,
    guard_day_mutation,
)
from backend.persistence.models import (
    CANDIDATE_EXAM_ATTENDANCE,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_EXAM_ATTENDANCE,
    ExamDay,
    ExamProtocol,
    ExamProtocolParticipant,
    ExamProtocolRevision,
    ExamSlot,
)
from backend.persistence.store import Store

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.execution.slot_ports import (
        AssignmentSnapshot,
        AttendanceSnapshot,
        DayExecutionSnapshot,
        DayMutationHandle,
        DayMutationRequest,
        ExecutionIdentitySnapshots,
        ExecutionUnitOfWork,
        MemberExecutionSnapshot,
        SlotSnapshot,
    )


def create_started_protocol(
    session: Session,
    *,
    slot_id: int,
    participant_member_ids: set[int],
    created_by_member_id: int | None,
    created_at: str,
) -> int:
    """Persist one protocol and its participant snapshot inside the caller's UoW."""
    existing_id = session.scalar(
        select(ExamProtocol.id).where(ExamProtocol.exam_slot_id == slot_id)
    )
    if existing_id is not None:
        return int(existing_id)
    if not participant_member_ids:
        raise ValueError("Ein Prüfungsprotokoll benötigt tatsächlich beteiligte Prüfer")
    protocol = ExamProtocol(
        exam_slot_id=slot_id,
        current_version=1,
        created_by_member_id=created_by_member_id,
        source="application",
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(protocol)
    session.flush()
    session.add_all(
        ExamProtocolParticipant(
            exam_protocol_id=protocol.id,
            committee_member_id=member_id,
            created_at=created_at,
        )
        for member_id in sorted(participant_member_ids)
    )
    session.add(
        ExamProtocolRevision(
            exam_protocol_id=protocol.id,
            version=1,
            workflow_state="draft",
            changed_by_member_id=created_by_member_id,
            change_reason="exam_started",
            created_at=created_at,
        )
    )
    session.flush()
    return int(protocol.id)


class SQLiteExecutionUnitOfWorkFactory:
    """Open one SQLite transaction and bind identity reads to that session."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        identity_snapshot_factory: Callable[[Session], ExecutionIdentitySnapshots],
    ) -> None:
        self.db_path = Path(db_path)
        self.identity_snapshot_factory = identity_snapshot_factory

    def __call__(self, *, write: bool = False) -> AbstractContextManager[ExecutionUnitOfWork]:
        return self._unit_of_work(write=write)

    @contextmanager
    def _unit_of_work(self, *, write: bool) -> Iterator[ExecutionUnitOfWork]:
        scope = (
            session_scope(self.db_path, begin_immediate=True)
            if write
            else read_session_scope(self.db_path)
        )
        with scope as session:
            yield SQLiteExecutionUnitOfWork(
                session,
                Store(session),
                self.identity_snapshot_factory(session),
            )


class SQLiteExecutionUnitOfWork:
    """Map Execution-owned snapshots and commands to SQLite persistence."""

    def __init__(
        self,
        session: Session,
        store: Store,
        identity_snapshots: ExecutionIdentitySnapshots,
    ) -> None:
        self._session = session
        self._store = store
        self._identity_snapshots = identity_snapshots
        self._day_mutation_guards: dict[int, DayMutationGuard] = {}
        self._next_day_mutation_handle = 1

    def confirmed_slot(self, day_id: int, slot_id: int) -> SlotSnapshot:
        slot = self._store.get(EXAM_SLOT, slot_id)
        day = self._store.get(EXAM_DAY, day_id)
        if (
            slot is None
            or day is None
            or slot["exam_day_id"] != day_id
            or slot["status"] != "confirmed"
            or day["status"] not in {"confirmed", "completed", "cancelled"}
        ):
            raise ValueError(
                "Nur ein bestätigter Prüfungsslot des ausgewählten Tages darf geändert werden"
            )
        exam_round = self._store.get(EXAM_ROUND, day["exam_round_id"])
        if exam_round is None or exam_round["status"] != "plan_confirmed":
            raise ValueError(
                "Der Prüfungstag ist nicht Bestandteil eines bestätigten Prüfungsplans"
            )
        return cast("SlotSnapshot", slot)

    def day_execution_state(self, day_id: int) -> DayExecutionSnapshot:
        day = self._store.get(EXAM_DAY, day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        return cast("DayExecutionSnapshot", {"closure_status": day["closure_status"]})

    def guard_day_mutation(self, request: DayMutationRequest) -> DayMutationHandle:
        """Guard a mutation inside this UoW without opening or committing a transaction."""
        guard = guard_day_mutation(
            self._session,
            day=self._required_day(request["day_id"]),
            kind=request["kind"],
            entity_id=request["entity_id"],
            payload=dict(request["payload"]),
            actor_member_id=request["actor_member_id"],
            protocol_revision_id=request["protocol_revision_id"],
        )
        handle = self._next_day_mutation_handle
        self._next_day_mutation_handle += 1
        self._day_mutation_guards[handle] = guard
        return handle

    def complete_day_mutation(
        self,
        handle: DayMutationHandle,
        *,
        actor_member_id: int,
        reason: str | None = None,
        protocol_revision_id: int | None = None,
    ) -> None:
        """Complete a guard in the current transaction; the UoW owns the commit."""
        try:
            guard = self._day_mutation_guards.pop(handle)
        except KeyError as exc:
            raise ValueError(
                "Tagesänderungs-Guard ist unbekannt oder bereits abgeschlossen"
            ) from exc
        complete_day_mutation(
            self._session,
            guard,
            actor_member_id=actor_member_id,
            reason=reason,
            protocol_revision_id=protocol_revision_id,
        )

    def assert_slot_status_mutable(
        self,
        day_id: int,
        slot_id: int,
        *,
        actor_member_id: int,
        payload: Mapping[str, object],
    ) -> None:
        self.confirmed_slot(day_id, slot_id)
        guard_day_mutation(
            self._session,
            day=self._required_day(day_id),
            kind="slot_status",
            entity_id=slot_id,
            payload=dict(payload),
            actor_member_id=actor_member_id,
        )

    def candidate_attendance(self, slot_id: int) -> AttendanceSnapshot | None:
        return cast(
            "AttendanceSnapshot | None",
            self._store.first(CANDIDATE_EXAM_ATTENDANCE, exam_slot_id=slot_id),
        )

    def member_attendance(self, day_id: int, member_id: int) -> AttendanceSnapshot | None:
        return cast(
            "AttendanceSnapshot | None",
            self._store.first(
                MEMBER_EXAM_ATTENDANCE,
                exam_day_id=day_id,
                committee_member_id=member_id,
            ),
        )

    def assignments(self, day_id: int) -> Sequence[AssignmentSnapshot]:
        return cast(
            "Sequence[AssignmentSnapshot]",
            self._store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=day_id),
        )

    def confirmed_assignment(self, day_id: int, assignment_id: int) -> AssignmentSnapshot:
        assignment = self._store.get(EXAM_DAY_ASSIGNMENT, assignment_id)
        day = self._store.get(EXAM_DAY, day_id)
        if assignment is None or day is None or assignment["exam_day_id"] != day_id:
            raise ValueError(
                "Nur eine Besetzung des ausgewählten Prüfungstags darf geändert werden"
            )
        exam_round = self._store.get(EXAM_ROUND, day["exam_round_id"])
        if (
            day["status"] not in {"confirmed", "completed", "cancelled"}
            or exam_round is None
            or exam_round["status"] != "plan_confirmed"
        ):
            raise ValueError(
                "Der Prüfungstag ist nicht Bestandteil eines bestätigten Prüfungsplans"
            )
        return cast("AssignmentSnapshot", assignment)

    def members_by_id(self, member_ids: Sequence[int]) -> Mapping[int, MemberExecutionSnapshot]:
        return self._identity_snapshots.members_by_id(member_ids)

    def save_candidate_attendance(
        self,
        day_id: int,
        slot_id: int,
        values: Mapping[str, object],
        *,
        actor_member_id: int,
        payload: Mapping[str, object],
    ) -> AttendanceSnapshot:
        existing = self.candidate_attendance(slot_id)
        guard = self.guard_day_mutation(
            {
                "day_id": day_id,
                "kind": "candidate_attendance",
                "entity_id": slot_id,
                "payload": payload,
                "actor_member_id": actor_member_id,
                "protocol_revision_id": None,
            }
        )
        result = (
            self._store.create(CANDIDATE_EXAM_ATTENDANCE, {**values, "exam_slot_id": slot_id})
            if existing is None
            else self._store.update(CANDIDATE_EXAM_ATTENDANCE, existing["id"], dict(values))
            or dict(existing)
        )
        self.complete_day_mutation(guard, actor_member_id=actor_member_id)
        return cast("AttendanceSnapshot", result)

    def save_member_attendance(
        self,
        day_id: int,
        assignment_id: int,
        member_id: int,
        values: Mapping[str, object],
        *,
        actor_member_id: int,
        payload: Mapping[str, object],
    ) -> AttendanceSnapshot:
        assignment = self._store.get(EXAM_DAY_ASSIGNMENT, assignment_id)
        if assignment is None or assignment["exam_day_id"] != day_id:
            raise ValueError(
                "Nur eine Besetzung des ausgewählten Prüfungstags darf geändert werden"
            )
        if assignment["committee_member_id"] != member_id:
            raise ValueError("Die Besetzung wurde zwischenzeitlich geändert")
        day = self._required_day(day_id)
        exam_round = self._store.get(EXAM_ROUND, day.exam_round_id)
        if (
            day.status not in {"confirmed", "completed", "cancelled"}
            or exam_round is None
            or exam_round["status"] != "plan_confirmed"
        ):
            raise ValueError(
                "Der Prüfungstag ist nicht Bestandteil eines bestätigten Prüfungsplans"
            )
        existing = self.member_attendance(day_id, member_id)
        guard = self.guard_day_mutation(
            {
                "day_id": day_id,
                "kind": "member_attendance",
                "entity_id": assignment_id,
                "payload": payload,
                "actor_member_id": actor_member_id,
                "protocol_revision_id": None,
            }
        )
        fields = {**values, "exam_day_id": day_id, "committee_member_id": member_id}
        result = (
            self._store.create(MEMBER_EXAM_ATTENDANCE, fields)
            if existing is None
            else self._store.update(MEMBER_EXAM_ATTENDANCE, existing["id"], dict(values))
            or dict(existing)
        )
        self.complete_day_mutation(guard, actor_member_id=actor_member_id)
        return cast("AttendanceSnapshot", result)

    def start_slot(
        self,
        day_id: int,
        slot_id: int,
        *,
        started_at: str,
        participant_member_ids: frozenset[int],
        actor_member_id: int,
        payload: Mapping[str, object],
    ) -> SlotSnapshot:
        slot = self.confirmed_slot(day_id, slot_id)
        guard = self.guard_day_mutation(
            {
                "day_id": day_id,
                "kind": "slot_status",
                "entity_id": slot_id,
                "payload": payload,
                "actor_member_id": actor_member_id,
                "protocol_revision_id": None,
            }
        )
        model = self._session.get(ExamSlot, slot_id)
        if model is None:
            raise ValueError("Prüfungsslot nicht gefunden")
        model.actual_started_at = started_at
        model.execution_status = "running"
        model.status_changed_at = started_at
        create_started_protocol(
            self._session,
            slot_id=slot_id,
            participant_member_ids=set(participant_member_ids),
            created_by_member_id=actor_member_id,
            created_at=started_at,
        )
        self._session.flush()
        self.complete_day_mutation(guard, actor_member_id=actor_member_id)
        return cast(
            "SlotSnapshot",
            {
                **slot,
                "actual_started_at": started_at,
                "execution_status": "running",
                "status_changed_at": started_at,
            },
        )

    def ensure_started_protocol(
        self,
        slot_id: int,
        *,
        participant_member_ids: frozenset[int],
        actor_member_id: int,
        started_at: str,
    ) -> None:
        create_started_protocol(
            self._session,
            slot_id=slot_id,
            participant_member_ids=set(participant_member_ids),
            created_by_member_id=actor_member_id,
            created_at=started_at,
        )

    def update_slot_status(
        self,
        day_id: int,
        slot_id: int,
        *,
        status: str,
        changed_at: str,
        reason: str | None,
        actual_started_at: str | None,
        actual_completed_at: str | None,
        actor_member_id: int,
        payload: Mapping[str, object],
    ) -> SlotSnapshot:
        slot = self.confirmed_slot(day_id, slot_id)
        guard = self.guard_day_mutation(
            {
                "day_id": day_id,
                "kind": "slot_status",
                "entity_id": slot_id,
                "payload": payload,
                "actor_member_id": actor_member_id,
                "protocol_revision_id": None,
            }
        )
        model = self._session.get(ExamSlot, slot_id)
        if model is None:
            raise ValueError("Prüfungsslot nicht gefunden")
        model.execution_status = status
        model.status_changed_at = changed_at
        model.status_reason = reason
        model.actual_started_at = actual_started_at
        model.actual_completed_at = actual_completed_at
        self._session.flush()
        self.complete_day_mutation(guard, actor_member_id=actor_member_id, reason=reason)
        return cast(
            "SlotSnapshot",
            {
                **slot,
                "execution_status": status,
                "status_changed_at": changed_at,
                "actual_started_at": actual_started_at,
                "actual_completed_at": actual_completed_at,
                "status_reason": reason,
            },
        )

    def _required_day(self, day_id: int) -> ExamDay:
        day = self._session.get(ExamDay, day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        return day
