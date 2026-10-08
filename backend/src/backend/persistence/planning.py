"""SQLite Unit of Work adapter for planning proposals and confirmed plans."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from sqlalchemy import select, update

from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    ConfirmedPlanRevision,
    ExamDay,
    ExamRoom,
    ExamRound,
    ExamSlot,
    ExamVenue,
)
from backend.persistence.store import Store

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.planning.proposal_ports import (
        CommitteeMemberSnapshot,
        ConfirmedPlanRevisionSnapshot,
        PlanningContextSnapshot,
        PlanningIdentitySnapshots,
        PlanningProposalSnapshot,
        PlanningUnitOfWork,
    )


class _ExamRoundRecord(TypedDict):
    id: int
    committee_id: int
    exam_half_year_id: int
    status: str
    plan_revision: int
    availability_deadline: str | None


class _PlanningSettingsRecord(TypedDict):
    default_room_id: int | None
    lunch_break_enabled: int
    exams_per_day: int
    max_exam_days_per_week: int


class _RoundCandidateRecord(TypedDict):
    id: int
    requires_mep: int


class _CandidateRecord(TypedDict):
    id: int
    requires_mep: int


class _CandidateDayRecord(TypedDict):
    id: int
    date: str
    is_active: int


class _MemberAvailabilityRecord(TypedDict):
    committee_member_id: int
    candidate_exam_day_id: int
    availability: str


@dataclass(frozen=True)
class _SQLitePlanSlotSnapshot:
    round_candidate_id: int
    slot_type: str
    id: int | None
    sequence_number: int
    starts_at: str
    ends_at: str
    status: str


@dataclass(frozen=True)
class _SQLitePlanAssignmentSnapshot:
    committee_member_id: int
    assignment_role: str
    day_part: str
    id: int | None
    fallback_status: str | None


@dataclass(frozen=True)
class _SQLitePlanDaySnapshot:
    candidate_exam_day_id: int
    room_id: int
    slots: tuple[_SQLitePlanSlotSnapshot, ...]
    assignments: tuple[_SQLitePlanAssignmentSnapshot, ...]
    id: int | None
    date: str
    status: str


@dataclass(frozen=True)
class _SQLitePlanningProposalSnapshot:
    round_id: int
    revision: int
    days: tuple[_SQLitePlanDaySnapshot, ...]


@dataclass(frozen=True)
class _SQLitePlanningContextSnapshot:
    exam_round: _ExamRoundRecord | None
    settings: _PlanningSettingsRecord | None
    round_candidates: tuple[_RoundCandidateRecord, ...]
    candidates: dict[int, _CandidateRecord]
    members: dict[int, CommitteeMemberSnapshot]
    candidate_days: dict[int, _CandidateDayRecord]
    availability: tuple[_MemberAvailabilityRecord, ...]
    blocked_person_ids: dict[tuple[str, str], dict[int, str]]
    active_candidate_assignments: dict[int, int]
    usable_room_ids: frozenset[int]
    protected_confirmed_day_ids: frozenset[int]
    exam_day_records: tuple[dict[str, object], ...]
    proposal: _SQLitePlanningProposalSnapshot | None


@dataclass(frozen=True)
class _SQLiteConfirmedPlanRevisionSnapshot:
    id: int
    exam_round_id: int
    previous_revision: int
    resulting_revision: int
    reason: str
    actor_member_id: int
    before_state_json: str
    after_state_json: str
    created_at: str


class SQLitePlanningUnitOfWorkFactory:
    """Create an isolated SQLite transaction for one Planning use case."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        identity_snapshot_factory: Callable[[Session], PlanningIdentitySnapshots],
        require_confirmed_coordinates: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.identity_snapshot_factory = identity_snapshot_factory
        self.require_confirmed_coordinates = require_confirmed_coordinates

    def __call__(self, *, write: bool = False) -> AbstractContextManager[PlanningUnitOfWork]:
        return self._unit_of_work(write=write)

    @contextmanager
    def _unit_of_work(self, *, write: bool) -> Iterator[PlanningUnitOfWork]:
        scope = (
            session_scope(self.db_path, begin_immediate=True)
            if write
            else read_session_scope(self.db_path)
        )
        with scope as session:
            yield SQLitePlanningUnitOfWork(
                Store(session),
                identity_snapshots=self.identity_snapshot_factory(session),
                require_confirmed_coordinates=self.require_confirmed_coordinates,
            )


class SQLitePlanningUnitOfWork:
    """Map Planning use-case contracts to SQLite within one session."""

    def __init__(
        self,
        store: Store,
        *,
        identity_snapshots: PlanningIdentitySnapshots,
        require_confirmed_coordinates: bool,
    ) -> None:
        self._store = store
        self._session = store.session
        self._identity_snapshots = identity_snapshots
        self._require_confirmed_coordinates = require_confirmed_coordinates

    def planning_context(self, round_id: int) -> PlanningContextSnapshot:
        exam_round_row = self._store.get(EXAM_ROUND, round_id)
        if exam_round_row is not None:
            round_model = self._session.get(ExamRound, round_id)
            exam_round_row["plan_revision"] = round_model.plan_revision if round_model else 0
        exam_round = cast(_ExamRoundRecord | None, exam_round_row)
        settings = cast(
            _PlanningSettingsRecord | None,
            self._store.first(PLANNING_SETTINGS, exam_round_id=round_id),
        )
        round_candidates = tuple(
            cast(_RoundCandidateRecord, row)
            for row in self._store.where(
                ROUND_CANDIDATE,
                exam_round_id=round_id,
                is_active=1,
            )
        )
        candidates = {row["id"]: cast(_CandidateRecord, row) for row in self._store.all(CANDIDATE)}
        committee_id = exam_round["committee_id"] if exam_round else -1
        members = dict(self._identity_snapshots.active_committee_members(committee_id))
        candidate_days = {
            row["id"]: cast(_CandidateDayRecord, row)
            for row in self._store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
        }
        availability = tuple(
            cast(_MemberAvailabilityRecord, row)
            for row in self._store.where(MEMBER_AVAILABILITY, exam_round_id=round_id)
        )
        active_assignments = {
            row["round_candidate_id"]: row["exam_round_id"]
            for row in self._store.where(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                exam_round_id=round_id,
                ended_at=None,
            )
        }
        blocked = self._blocked_person_ids(exam_round)
        usable_rooms = self._usable_room_ids(committee_id)
        exam_days = tuple(
            cast(dict[str, object], row)
            for row in self._store.where(EXAM_DAY, exam_round_id=round_id)
        )
        proposal = self._read_proposal(round_id) if exam_round is not None else None
        protected = (
            self._protected_confirmed_day_ids(proposal) if proposal is not None else frozenset()
        )
        return _SQLitePlanningContextSnapshot(
            exam_round=exam_round,
            settings=settings,
            round_candidates=tuple(round_candidates),
            candidates=candidates,
            members=members,
            candidate_days=candidate_days,
            availability=availability,
            blocked_person_ids=blocked,
            active_candidate_assignments=active_assignments,
            usable_room_ids=usable_rooms,
            protected_confirmed_day_ids=protected,
            exam_day_records=exam_days,
            proposal=proposal,
        )

    def mark_availabilities_requested(self, round_id: int) -> dict[str, object] | None:
        return self._store.update(EXAM_ROUND, round_id, {"status": "availability_requested"})

    def replace_proposal(
        self,
        proposal: PlanningProposalSnapshot,
        *,
        expected_revision: int,
        allowed_statuses: frozenset[str],
        target_status: str,
    ) -> int | None:
        next_revision = self._claim_revision(
            proposal.round_id,
            expected_revision,
            allowed_statuses=allowed_statuses,
            target_status=target_status,
        )
        if next_revision is None:
            return None
        self._clear_existing_proposal(proposal.round_id)
        self._persist_proposal(proposal)
        return next_revision

    def confirm_proposal(self, round_id: int, *, expected_revision: int) -> int | None:
        next_revision = self._claim_revision(
            round_id,
            expected_revision,
            allowed_statuses=frozenset({"plan_proposed"}),
            target_status="plan_confirmed",
        )
        if next_revision is None:
            return None
        days = self._store.where(EXAM_DAY, exam_round_id=round_id)
        for exam_day in days:
            self._store.update(EXAM_DAY, exam_day["id"], {"status": "confirmed"})
            for slot in self._store.where(EXAM_SLOT, exam_day_id=exam_day["id"]):
                self._store.update(EXAM_SLOT, slot["id"], {"status": "confirmed"})
            for assignment in self._store.where(
                EXAM_DAY_ASSIGNMENT,
                exam_day_id=exam_day["id"],
            ):
                if assignment["assignment_role"] == "fallback":
                    self._store.update(
                        EXAM_DAY_ASSIGNMENT,
                        assignment["id"],
                        {"fallback_status": "confirmed"},
                    )
        return next_revision

    def revise_confirmed_plan(
        self,
        proposal: PlanningProposalSnapshot,
        *,
        expected_revision: int,
        protected_day_ids: frozenset[int],
        actor_member_id: int,
        reason: str,
        before_state_json: str,
        after_state_json: str,
    ) -> ConfirmedPlanRevisionSnapshot | None:
        exam_round = self._store.get(EXAM_ROUND, proposal.round_id)
        actor = self._identity_snapshots.members_by_id((actor_member_id,)).get(actor_member_id)
        if (
            exam_round is None
            or actor is None
            or not actor["is_active"]
            or actor["committee_id"] != exam_round["committee_id"]
        ):
            raise PermissionError("The acting member may not change this confirmed plan")
        next_revision = self._claim_revision(
            proposal.round_id,
            expected_revision,
            allowed_statuses=frozenset({"plan_confirmed"}),
            target_status="plan_confirmed",
        )
        if next_revision is None:
            return None
        self._persist_confirmed_plan(proposal, protected_day_ids)
        revision = ConfirmedPlanRevision(
            exam_round_id=proposal.round_id,
            previous_revision=expected_revision,
            resulting_revision=next_revision,
            reason=reason,
            actor_member_id=actor_member_id,
            before_state_json=before_state_json,
            after_state_json=after_state_json,
        )
        self._session.add(revision)
        self._session.flush()
        return _SQLiteConfirmedPlanRevisionSnapshot(
            id=revision.id,
            exam_round_id=revision.exam_round_id,
            previous_revision=revision.previous_revision,
            resulting_revision=revision.resulting_revision,
            reason=revision.reason,
            actor_member_id=revision.actor_member_id,
            before_state_json=revision.before_state_json,
            after_state_json=revision.after_state_json,
            created_at=revision.created_at,
        )

    def confirmed_plan_revisions(self, round_id: int) -> tuple[ConfirmedPlanRevisionSnapshot, ...]:
        revisions = self._session.scalars(
            select(ConfirmedPlanRevision)
            .where(ConfirmedPlanRevision.exam_round_id == round_id)
            .order_by(ConfirmedPlanRevision.resulting_revision)
        )
        return tuple(
            _SQLiteConfirmedPlanRevisionSnapshot(
                id=item.id,
                exam_round_id=item.exam_round_id,
                previous_revision=item.previous_revision,
                resulting_revision=item.resulting_revision,
                reason=item.reason,
                actor_member_id=item.actor_member_id,
                before_state_json=item.before_state_json,
                after_state_json=item.after_state_json,
                created_at=item.created_at,
            )
            for item in revisions
        )

    def confirmed_plan_revision(self, revision_id: int) -> ConfirmedPlanRevisionSnapshot | None:
        item = self._session.get(ConfirmedPlanRevision, revision_id)
        if item is None:
            return None
        return self._revision_snapshot(item)

    def all_confirmed_plan_revisions(self) -> tuple[ConfirmedPlanRevisionSnapshot, ...]:
        revisions = self._session.scalars(
            select(ConfirmedPlanRevision).order_by(
                ConfirmedPlanRevision.exam_round_id,
                ConfirmedPlanRevision.resulting_revision,
            )
        )
        return tuple(self._revision_snapshot(item) for item in revisions)

    def confirmed_plan_revision_ids(self) -> tuple[int, ...]:
        return tuple(
            self._session.scalars(
                select(ConfirmedPlanRevision.id).order_by(
                    ConfirmedPlanRevision.exam_round_id,
                    ConfirmedPlanRevision.resulting_revision,
                )
            )
        )

    @staticmethod
    def _revision_snapshot(item: ConfirmedPlanRevision) -> ConfirmedPlanRevisionSnapshot:
        return _SQLiteConfirmedPlanRevisionSnapshot(
            id=item.id,
            exam_round_id=item.exam_round_id,
            previous_revision=item.previous_revision,
            resulting_revision=item.resulting_revision,
            reason=item.reason,
            actor_member_id=item.actor_member_id,
            before_state_json=item.before_state_json,
            after_state_json=item.after_state_json,
            created_at=item.created_at,
        )

    def _claim_revision(
        self,
        round_id: int,
        expected_revision: int,
        *,
        allowed_statuses: frozenset[str],
        target_status: str,
    ) -> int | None:
        result = self._session.execute(
            update(ExamRound)
            .where(
                ExamRound.id == round_id,
                ExamRound.plan_revision == expected_revision,
                ExamRound.status.in_(allowed_statuses),
            )
            .values(
                plan_revision=expected_revision + 1,
                status=target_status,
                updated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
            )
        )
        return expected_revision + 1 if result.rowcount == 1 else None

    def _clear_existing_proposal(self, round_id: int) -> None:
        for exam_day in self._store.where(EXAM_DAY, exam_round_id=round_id):
            if exam_day["status"] == "confirmed":
                raise ValueError("Confirmed exam days cannot be replaced")
            self._store.delete(EXAM_DAY, exam_day["id"])

    def _persist_proposal(self, proposal: PlanningProposalSnapshot) -> None:
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=proposal.round_id)
        if settings is None:
            raise ValueError("Planning settings not found")
        for day in proposal.days:
            exam_day = self._store.create(
                EXAM_DAY,
                {
                    "exam_round_id": proposal.round_id,
                    "room_id": day.room_id,
                    "date": day.date,
                    "status": "proposed",
                    "lunch_break_enabled": int(bool(settings["lunch_break_enabled"])),
                    "created_from_proposal": 1,
                },
            )
            for assignment in day.assignments:
                self._store.create(
                    EXAM_DAY_ASSIGNMENT,
                    {
                        "exam_day_id": exam_day["id"],
                        "committee_member_id": assignment.committee_member_id,
                        "assignment_role": assignment.assignment_role,
                        "day_part": assignment.day_part,
                        "fallback_status": assignment.fallback_status,
                    },
                )
            for slot in day.slots:
                self._store.create(
                    EXAM_SLOT,
                    {
                        "exam_day_id": exam_day["id"],
                        "round_candidate_id": slot.round_candidate_id,
                        "slot_type": slot.slot_type,
                        "starts_at": slot.starts_at,
                        "ends_at": slot.ends_at,
                        "sequence_number": slot.sequence_number,
                        "status": "proposed",
                    },
                )

    def _persist_confirmed_plan(
        self,
        proposal: PlanningProposalSnapshot,
        protected_day_ids: frozenset[int],
    ) -> None:
        editable_days = [day for day in proposal.days if day.id not in protected_day_ids]
        slots = [slot for day in editable_days for slot in day.slots]
        for slot in slots:
            if slot.id is None:
                raise ValueError("Confirmed plan slots need stable identities")
            persisted_slot = self._session.get(ExamSlot, slot.id)
            if persisted_slot is None:
                raise ValueError("Confirmed plan slot no longer exists")
            persisted_slot.sequence_number = 1_000_000 + slot.id
        self._session.flush()
        for day in editable_days:
            if day.id is None:
                raise ValueError("Confirmed plan days need stable identities")
            self._store.update(
                EXAM_DAY,
                day.id,
                {"room_id": day.room_id, "date": day.date, "status": "confirmed"},
            )
            for assignment in day.assignments:
                if assignment.id is None:
                    raise ValueError("Confirmed plan assignments need stable identities")
                self._store.update(
                    EXAM_DAY_ASSIGNMENT,
                    assignment.id,
                    {
                        "exam_day_id": day.id,
                        "committee_member_id": assignment.committee_member_id,
                        "assignment_role": assignment.assignment_role,
                        "day_part": assignment.day_part,
                        "fallback_status": assignment.fallback_status,
                    },
                )
            for slot in day.slots:
                if slot.id is None:
                    raise ValueError("Confirmed plan slots need stable identities")
                self._store.update(
                    EXAM_SLOT,
                    slot.id,
                    {
                        "exam_day_id": day.id,
                        "round_candidate_id": slot.round_candidate_id,
                        "slot_type": slot.slot_type,
                        "starts_at": slot.starts_at,
                        "ends_at": slot.ends_at,
                        "sequence_number": slot.sequence_number,
                        "status": "confirmed",
                    },
                )

    def _read_proposal(self, round_id: int) -> _SQLitePlanningProposalSnapshot | None:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        round_model = self._session.get(ExamRound, round_id)
        if exam_round is None or round_model is None:
            return None
        candidate_days = {
            row["date"]: row
            for row in self._store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
        }
        days = []
        for row in self._store.where(EXAM_DAY, exam_round_id=round_id):
            candidate_day = candidate_days.get(row["date"])
            slots = tuple(
                _SQLitePlanSlotSnapshot(
                    round_candidate_id=slot["round_candidate_id"],
                    slot_type=slot["slot_type"],
                    id=slot["id"],
                    sequence_number=slot["sequence_number"],
                    starts_at=slot["starts_at"],
                    ends_at=slot["ends_at"],
                    status=slot["status"],
                )
                for slot in self._store.where(EXAM_SLOT, exam_day_id=row["id"])
            )
            assignments = tuple(
                _SQLitePlanAssignmentSnapshot(
                    committee_member_id=item["committee_member_id"],
                    assignment_role=item["assignment_role"],
                    day_part=item["day_part"],
                    id=item["id"],
                    fallback_status=item["fallback_status"],
                )
                for item in self._store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=row["id"])
            )
            days.append(
                _SQLitePlanDaySnapshot(
                    candidate_exam_day_id=candidate_day["id"] if candidate_day else -1,
                    room_id=row["room_id"],
                    slots=slots,
                    assignments=assignments,
                    id=row["id"],
                    date=row["date"],
                    status=row["status"],
                )
            )
        return _SQLitePlanningProposalSnapshot(round_id, round_model.plan_revision, tuple(days))

    def _blocked_person_ids(
        self,
        exam_round: _ExamRoundRecord | None,
    ) -> dict[tuple[str, str], dict[int, str]]:
        blocked: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
        if exam_round is None:
            return blocked
        assignments = self._store.all(EXAM_DAY_ASSIGNMENT)
        members = self._identity_snapshots.members_by_id(
            tuple({assignment["committee_member_id"] for assignment in assignments})
        )
        for assignment in assignments:
            exam_day = self._store.get(EXAM_DAY, assignment["exam_day_id"])
            member = members.get(assignment["committee_member_id"])
            other_round = (
                self._store.get(EXAM_ROUND, exam_day["exam_round_id"]) if exam_day else None
            )
            if (
                exam_day is None
                or member is None
                or other_round is None
                or exam_day["exam_round_id"] == exam_round["id"]
                or other_round["exam_half_year_id"] != exam_round["exam_half_year_id"]
                or exam_day["status"] in {"cancelled", "completed"}
            ):
                continue
            reservation = (
                "bestätigten Termin" if exam_day["status"] == "confirmed" else "Planungsvorschlag"
            )
            parts = (
                ("morning", "afternoon")
                if assignment["day_part"] == "full_day"
                else (assignment["day_part"],)
            )
            for part in parts:
                key = (exam_day["date"], part)
                previous = blocked[key].get(member["person_id"])
                if previous != "bestätigten Termin":
                    blocked[key][member["person_id"]] = reservation
        return blocked

    def _usable_room_ids(self, committee_id: int) -> frozenset[int]:
        rooms = self._session.execute(
            select(
                ExamRoom.id,
                ExamVenue.scope,
                ExamVenue.committee_id,
                ExamVenue.coordinate_status,
            )
            .join(ExamVenue, ExamVenue.id == ExamRoom.venue_id)
            .where(ExamRoom.is_active == 1, ExamVenue.is_active == 1)
        )
        return frozenset(
            room_id
            for room_id, scope, owner_id, coordinate_status in rooms
            if (scope == "global" or owner_id == committee_id)
            and (not self._require_confirmed_coordinates or coordinate_status == "confirmed")
        )

    def _protected_confirmed_day_ids(
        self,
        proposal: PlanningProposalSnapshot,
    ) -> frozenset[int]:
        protected: set[int] = set()
        for day in proposal.days:
            if day.id is None:
                raise ValueError("Confirmed plan day identity is missing")
            current = self._session.get(ExamDay, day.id)
            if current is None or current.status != "confirmed" or current.closure_status != "open":
                protected.add(day.id)
                continue
            for slot in self._session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id == day.id)
            ):
                if (
                    slot.status != "confirmed"
                    or slot.execution_status != "open"
                    or slot.actual_started_at is not None
                    or slot.actual_completed_at is not None
                ):
                    protected.add(day.id)
                    break
        return frozenset(protected)
