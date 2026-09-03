"""Build and confirm exam-round proposals while preserving planning invariants."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select as sql_select
from sqlalchemy import update as sql_update

from .database import DEFAULT_DB_PATH, session_scope
from .exam_venues import room_is_usable_for_committee
from .models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    ConfirmedPlanRevision,
    ExamRound,
    ExamSlot,
)
from .store import Store

SIDES = ("employer", "employee", "school")


@dataclass(frozen=True)
class ShiftCrew:
    """A complete examiner crew for one day part, including its fallback member."""

    crew: tuple[int, int, int]
    fallback: int


@dataclass(frozen=True)
class PlanSlot:
    """One immutable slot identity; sequence and times are server-derived."""

    round_candidate_id: int
    slot_type: str
    id: int | None = None
    sequence_number: int = 0
    starts_at: str = ""
    ends_at: str = ""
    status: str = "proposed"


@dataclass(frozen=True)
class PlanAssignment:
    """One examiner or fallback assignment within a proposal day part."""

    committee_member_id: int
    assignment_role: str
    day_part: str
    id: int | None = None
    fallback_status: str | None = None


@dataclass(frozen=True)
class PlanDay:
    """One candidate exam day and all slots and assignments planned for it."""

    candidate_exam_day_id: int
    room_id: int
    slots: tuple[PlanSlot, ...]
    assignments: tuple[PlanAssignment, ...]
    id: int | None = None
    date: str = ""
    status: str = "proposed"


@dataclass(frozen=True)
class PlanningProposal:
    """The complete, revisioned proposal aggregate for one exam round."""

    round_id: int
    revision: int
    days: tuple[PlanDay, ...]


@dataclass(frozen=True)
class ConfirmedPlanChange:
    """One requested complete change to a confirmed plan aggregate."""

    plan: PlanningProposal
    reason: str


@dataclass(frozen=True)
class PlanValidationIssue:
    """A stable domain validation finding suitable for the later API contract."""

    code: str
    message: str
    day_id: int | None = None
    slot_id: int | None = None
    member_id: int | None = None


@dataclass
class _ProposalValidationContext:
    """Loaded reference data and accumulated counts for proposal validation."""

    exam_round: dict[str, Any]
    settings: dict[str, Any]
    active_candidates: dict[int, dict[str, Any]]
    candidate_days: dict[int, dict[str, Any]]
    members: dict[int, dict[str, Any]]
    availability: dict[tuple[int, int], str]
    blocked: dict[tuple[str, str], dict[int, str]]
    slot_counts: dict[tuple[int, str], int] = field(default_factory=lambda: defaultdict(int))
    used_candidate_days: set[int] = field(default_factory=set)
    days_by_week: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class PlanValidationError(ValueError):
    """Reject an invalid complete proposal without persisting a partial state."""

    def __init__(self, issues: list[PlanValidationIssue]):
        self.issues = tuple(issues)
        super().__init__(issues[0].message if issues else "Planning proposal is invalid")


class PlanConflictError(ValueError):
    """Reject a stale revision or a proposal whose round status changed."""


class ConfirmedPlanConflictError(PlanConflictError):
    """Reject a stale or locked mutation of a confirmed plan."""


class PlanningService:
    """Coordinate proposal generation and confirmation within one database transaction.

    The service owns the planning-specific invariants; callers must use the
    returned validation information instead of inferring validity from created
    rows. Each public operation runs in one :func:`session_scope`, so partial
    proposals and partially confirmed plans are rolled back on errors.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def request_availabilities(self, round_id: int) -> dict[str, Any]:
        """Move a prepared draft into availability coordination.

        The transition is idempotent so a retried request cannot skip a later
        workflow phase. Planning settings, an active candidate day and a
        response deadline must already be persisted before coordination starts.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            context = self._load_context(store, round_id)
            exam_round = context["round"]
            if exam_round is None:
                raise ValueError("Exam round not found")
            if exam_round["status"] == "availability_requested":
                return exam_round
            if exam_round["status"] != "draft":
                raise ValueError("Availabilities can only be requested for a draft round")
            if context["settings"] is None:
                raise ValueError("Planning settings not found")
            if not context["candidate_days"]:
                raise ValueError("No active candidate exam days found")
            if not exam_round.get("availability_deadline"):
                raise ValueError("Availability deadline is required")

            return (
                store.update(EXAM_ROUND, round_id, {"status": "availability_requested"})
                or exam_round
            )

    def generate_proposal(self, round_id: int) -> dict[str, Any]:
        """Create a replaceable proposal for an exam round.

        Regular candidates are scheduled before MEP candidates, every planned
        shift needs all three representation sides plus a fallback, and a day
        cannot consist solely of MEP slots. Existing non-confirmed proposals
        are replaced atomically; confirmed days raise ``ValueError`` instead.

        Args:
            round_id: Identifier of the exam round to plan.

        Returns:
            The persisted proposal, validation messages, and slot counts.

        Raises:
            ValueError: If required planning data is missing or a confirmed
                proposal would be replaced.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            context = self._load_context(store, round_id)
            if context["round"] is None:
                raise ValueError("Exam round not found")
            if context["round"]["status"] not in {
                "availability_requested",
                "availability_closed",
                "plan_proposed",
            }:
                raise ValueError("A proposal requires an availability coordination round")
            if context["settings"] is None:
                raise ValueError("Planning settings not found")
            if not context["candidate_days"]:
                raise ValueError("No active candidate exam days found")

            generated = self._build_proposal(context)
            proposal = self._generated_aggregate(context, generated)
            proposal = self._normalize_proposal(store, proposal)
            self._raise_for_invalid_proposal(store, proposal)
            next_revision = self._claim_revision(
                store,
                round_id,
                proposal.revision,
                allowed_statuses={
                    "availability_requested",
                    "availability_closed",
                    "plan_proposed",
                },
                target_status="plan_proposed",
            )
            self._clear_existing_proposal(store, round_id)
            self._persist_aggregate(store, proposal)
            persisted = self._read_proposal(store, round_id, revision=next_revision)

            return {
                "round_id": round_id,
                "status": "plan_proposed",
                "revision": persisted.revision,
                "exam_days": self._proposal_days(persisted),
                "validation": {"passed": True, "messages": []},
                "counts": generated["counts"],
            }

    def get_proposal(self, round_id: int) -> PlanningProposal:
        """Read the complete persisted proposal aggregate and its revision."""
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            if exam_round["status"] != "plan_proposed":
                raise PlanConflictError("Only a planning proposal can be read")
            return self._read_proposal(store, round_id)

    def save_proposal(self, proposal: PlanningProposal) -> PlanningProposal:
        """Validate and replace one proposal atomically using optimistic revision."""
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, proposal.round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            if exam_round["status"] != "plan_proposed":
                raise PlanConflictError("Only a planning proposal can be changed")
            round_model = store.session.get(ExamRound, proposal.round_id)
            if round_model is None or round_model.plan_revision != proposal.revision:
                raise PlanConflictError("Planning proposal revision is stale")

            normalized = self._normalize_proposal(store, proposal)
            self._raise_for_invalid_proposal(store, normalized)
            next_revision = self._claim_revision(
                store,
                proposal.round_id,
                proposal.revision,
                allowed_statuses={"plan_proposed"},
                target_status="plan_proposed",
            )
            self._clear_existing_proposal(store, proposal.round_id)
            self._persist_aggregate(store, normalized)
            return self._read_proposal(store, proposal.round_id, revision=next_revision)

    def get_confirmed_plan(self, round_id: int) -> PlanningProposal:
        """Read the complete, still editable confirmed plan aggregate."""
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            if exam_round["status"] != "plan_confirmed":
                raise ConfirmedPlanConflictError("Only a confirmed plan can be changed")
            return self._read_proposal(store, round_id)

    def save_confirmed_plan(
        self,
        change: ConfirmedPlanChange,
        *,
        actor_member_id: int,
    ) -> tuple[PlanningProposal, dict[str, Any]]:
        """Atomically revise a confirmed plan and record immutable before/after states.

        The existing day, slot, and assignment identities are retained.  This
        deliberately prevents an aggregate update from deleting operational
        evidence that later workflow steps may reference.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            proposal = change.plan
            exam_round = store.get(EXAM_ROUND, proposal.round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            if exam_round["status"] != "plan_confirmed":
                raise ConfirmedPlanConflictError("Only a confirmed plan can be changed")
            round_model = store.session.get(ExamRound, proposal.round_id)
            if round_model is None or round_model.plan_revision != proposal.revision:
                raise ConfirmedPlanConflictError("Confirmed plan revision is stale")

            before = self._read_proposal(store, proposal.round_id)
            self._raise_for_confirmed_plan_shape(before, proposal)
            protected_day_ids = self._protected_confirmed_day_ids(store, before)
            normalized = self._normalize_proposal(store, proposal, status="confirmed")
            self._raise_for_invalid_proposal(store, normalized, status="confirmed")
            self._raise_for_protected_confirmed_days_unchanged(
                before,
                normalized,
                protected_day_ids,
            )

            reason = change.reason.strip()
            if not reason:
                raise PlanValidationError(
                    [
                        PlanValidationIssue(
                            "change_reason_required",
                            "A confirmed plan change needs a reason",
                        )
                    ]
                )
            actor = store.get(COMMITTEE_MEMBER, actor_member_id)
            if (
                actor is None
                or not actor["is_active"]
                or actor["committee_id"] != exam_round["committee_id"]
            ):
                raise PermissionError("The acting member may not change this confirmed plan")

            before_payload = self.confirmed_plan_payload(before)
            next_revision = self._claim_revision(
                store,
                proposal.round_id,
                proposal.revision,
                allowed_statuses={"plan_confirmed"},
                target_status="plan_confirmed",
            )
            self._persist_confirmed_aggregate(store, normalized, protected_day_ids)
            saved = self._read_proposal(store, proposal.round_id, revision=next_revision)
            after_payload = self.confirmed_plan_payload(saved)
            audit = ConfirmedPlanRevision(
                exam_round_id=proposal.round_id,
                previous_revision=proposal.revision,
                resulting_revision=next_revision,
                reason=reason,
                actor_member_id=actor_member_id,
                before_state_json=self._snapshot_json(before_payload),
                after_state_json=self._snapshot_json(after_payload),
            )
            session.add(audit)
            session.flush()
            return saved, self._revision_payload(audit)

    def confirmed_plan_revisions(self, round_id: int) -> list[dict[str, Any]]:
        """Return the append-only revision history for one confirmed plan."""
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            return [
                self._revision_payload(item)
                for item in session.scalars(
                    sql_select(ConfirmedPlanRevision)
                    .where(ConfirmedPlanRevision.exam_round_id == round_id)
                    .order_by(ConfirmedPlanRevision.resulting_revision)
                )
            ]

    def confirm_plan(self, round_id: int) -> dict[str, Any]:
        """Confirm every day, slot, and fallback belonging to a proposal.

        Confirmation is an all-or-nothing state transition. Cancelled days are
        rejected before writes begin, and the containing session rolls back if
        any later persistence operation fails.

        Args:
            round_id: Identifier of the round whose proposal is confirmed.

        Returns:
            The confirmed days and aggregate confirmation counts.

        Raises:
            ValueError: If the exam round is absent or the persisted proposal
                violates a mandatory planning rule.
            PlanConflictError: If no proposal exists or the round status or
                revision changed before confirmation.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            exam_days = store.where(EXAM_DAY, exam_round_id=round_id)
            if not exam_days:
                raise PlanConflictError("No planning proposal found")
            if exam_round["status"] != "plan_proposed":
                raise PlanConflictError("Only a planning proposal can be confirmed")

            proposal = self._read_proposal(store, round_id)
            self._raise_for_invalid_proposal(store, proposal)
            confirmed_revision = self._claim_revision(
                store,
                round_id,
                proposal.revision,
                allowed_statuses={"plan_proposed"},
                target_status="plan_confirmed",
            )

            confirmed_days = []
            confirmed_slot_count = 0
            for exam_day in exam_days:
                confirmed_day = store.update(
                    EXAM_DAY,
                    exam_day["id"],
                    {"status": "confirmed"},
                )
                confirmed_days.append(confirmed_day)
                for slot in store.where(EXAM_SLOT, exam_day_id=exam_day["id"]):
                    store.update(EXAM_SLOT, slot["id"], {"status": "confirmed"})
                    confirmed_slot_count += 1
                for assignment in store.where(
                    EXAM_DAY_ASSIGNMENT,
                    exam_day_id=exam_day["id"],
                ):
                    if assignment["assignment_role"] == "fallback":
                        store.update(
                            EXAM_DAY_ASSIGNMENT,
                            assignment["id"],
                            {"fallback_status": "confirmed"},
                        )

            return {
                "round_id": round_id,
                "status": "plan_confirmed",
                "revision": confirmed_revision,
                "exam_days": confirmed_days,
                "counts": {
                    "confirmed_exam_days": len(confirmed_days),
                    "confirmed_slots": confirmed_slot_count,
                },
            }

    def _generated_aggregate(
        self,
        context: dict[str, Any],
        generated: dict[str, Any],
    ) -> PlanningProposal:
        settings = context["settings"]
        days = []
        for planned_day in generated["days"]:
            assignments: list[PlanAssignment] = []
            for part in ("morning", "afternoon"):
                crew = planned_day[part]
                if crew is None:
                    continue
                assignments.extend(
                    PlanAssignment(member_id, "examiner", part) for member_id in crew.crew
                )
                assignments.append(PlanAssignment(crew.fallback, "fallback", part))
            slots = [
                PlanSlot(round_candidate_id, "regular")
                for round_candidate_id in planned_day["regular_candidate_ids"]
            ]
            slots.extend(
                PlanSlot(round_candidate_id, "mep")
                for round_candidate_id in planned_day["mep_candidate_ids"]
            )
            days.append(
                PlanDay(
                    candidate_exam_day_id=planned_day["candidate_exam_day_id"],
                    room_id=settings["default_room_id"],
                    slots=tuple(slots),
                    assignments=tuple(assignments),
                )
            )
        return PlanningProposal(
            round_id=context["round"]["id"],
            revision=context["round"]["plan_revision"],
            days=tuple(days),
        )

    def _normalize_proposal(
        self,
        store: Store,
        proposal: PlanningProposal,
        *,
        status: str = "proposed",
    ) -> PlanningProposal:
        candidate_days = {
            row["id"]: row
            for row in store.where(CANDIDATE_EXAM_DAY, exam_round_id=proposal.round_id)
        }
        settings = store.first(PLANNING_SETTINGS, exam_round_id=proposal.round_id)
        lunch_break = bool(settings and settings["lunch_break_enabled"])
        normalized_days = []
        for day in proposal.days:
            candidate_day = candidate_days.get(day.candidate_exam_day_id)
            date = candidate_day["date"] if candidate_day else ""
            times = self._slot_times(len(day.slots), lunch_break)
            normalized_slots = tuple(
                replace(
                    slot,
                    sequence_number=index,
                    starts_at=f"{date} {starts_at}:00",
                    ends_at=f"{date} {ends_at}:00",
                    status=status,
                )
                for index, (slot, (starts_at, ends_at)) in enumerate(
                    zip(day.slots, times, strict=True), start=1
                )
            )
            normalized_assignments = tuple(
                replace(
                    assignment,
                    fallback_status=(
                        ("requested" if status == "proposed" else "confirmed")
                        if assignment.assignment_role == "fallback"
                        else None
                    ),
                )
                for assignment in day.assignments
            )
            normalized_days.append(
                replace(
                    day,
                    date=date,
                    slots=normalized_slots,
                    assignments=normalized_assignments,
                    status=status,
                )
            )
        return replace(proposal, days=tuple(normalized_days))

    def _read_proposal(
        self,
        store: Store,
        round_id: int,
        *,
        revision: int | None = None,
    ) -> PlanningProposal:
        exam_round = store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            raise ValueError("Exam round not found")
        round_model = store.session.get(ExamRound, round_id)
        if round_model is None:
            raise ValueError("Exam round not found")
        candidate_days = {
            row["date"]: row for row in store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
        }
        days = []
        for row in store.where(EXAM_DAY, exam_round_id=round_id):
            candidate_day = candidate_days.get(row["date"])
            slots = tuple(
                PlanSlot(
                    round_candidate_id=slot["round_candidate_id"],
                    slot_type=slot["slot_type"],
                    id=slot["id"],
                    sequence_number=slot["sequence_number"],
                    starts_at=slot["starts_at"],
                    ends_at=slot["ends_at"],
                    status=slot["status"],
                )
                for slot in store.where(EXAM_SLOT, exam_day_id=row["id"])
            )
            assignments = tuple(
                PlanAssignment(
                    committee_member_id=assignment["committee_member_id"],
                    assignment_role=assignment["assignment_role"],
                    day_part=assignment["day_part"],
                    id=assignment["id"],
                    fallback_status=assignment["fallback_status"],
                )
                for assignment in store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=row["id"])
            )
            days.append(
                PlanDay(
                    candidate_exam_day_id=candidate_day["id"] if candidate_day else -1,
                    room_id=row["room_id"],
                    slots=slots,
                    assignments=assignments,
                    id=row["id"],
                    date=row["date"],
                    status=row["status"],
                )
            )
        return PlanningProposal(
            round_id=round_id,
            revision=round_model.plan_revision if revision is None else revision,
            days=tuple(days),
        )

    def _persist_aggregate(self, store: Store, proposal: PlanningProposal) -> None:
        settings = store.first(PLANNING_SETTINGS, exam_round_id=proposal.round_id)
        if settings is None:
            raise ValueError("Planning settings not found")
        for day in proposal.days:
            exam_day = store.create(
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
                store.create(
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
                store.create(
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

    def _persist_confirmed_aggregate(
        self,
        store: Store,
        proposal: PlanningProposal,
        protected_day_ids: set[int],
    ) -> None:
        """Update only open confirmed-plan parts without changing row identities."""
        editable_days = [day for day in proposal.days if day.id not in protected_day_ids]
        slots = [slot for day in editable_days for slot in day.slots]
        temporary_sequence_base = 1_000_000
        for slot in slots:
            if slot.id is None:
                raise ValueError("Confirmed plan slots need stable identities")
            persisted_slot = store.session.get(ExamSlot, slot.id)
            if persisted_slot is None:
                raise ValueError("Confirmed plan slot no longer exists")
            # ``(exam_day_id, sequence_number)`` is unique and the schema
            # requires a positive sequence.  Temporarily move every retained
            # row outside the bounded planning range so swaps cannot collide
            # while the aggregate is persisted one row at a time.
            persisted_slot.sequence_number = temporary_sequence_base + slot.id
        store.session.flush()
        for day in editable_days:
            if day.id is None:
                raise ValueError("Confirmed plan days need stable identities")
            store.update(
                EXAM_DAY,
                day.id,
                {
                    "room_id": day.room_id,
                    "date": day.date,
                    "status": "confirmed",
                },
            )
            for assignment in day.assignments:
                if assignment.id is None:
                    raise ValueError("Confirmed plan assignments need stable identities")
                store.update(
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
                store.update(
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

    def _claim_revision(
        self,
        store: Store,
        round_id: int,
        expected_revision: int,
        *,
        allowed_statuses: set[str],
        target_status: str,
    ) -> int:
        result = store.session.execute(
            sql_update(ExamRound)
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
        if result.rowcount != 1:
            raise PlanConflictError("Planning proposal revision or status changed")
        return expected_revision + 1

    @staticmethod
    def _proposal_days(proposal: PlanningProposal) -> list[dict[str, Any]]:
        return [
            {
                "id": day.id,
                "candidate_exam_day_id": day.candidate_exam_day_id,
                "date": day.date,
                "room_id": day.room_id,
                "status": day.status,
                "slots": [
                    {
                        "id": slot.id,
                        "round_candidate_id": slot.round_candidate_id,
                        "slot_type": slot.slot_type,
                        "starts_at": slot.starts_at,
                        "ends_at": slot.ends_at,
                        "sequence_number": slot.sequence_number,
                        "status": slot.status,
                    }
                    for slot in day.slots
                ],
                "assignments": [
                    {
                        "id": assignment.id,
                        "committee_member_id": assignment.committee_member_id,
                        "assignment_role": assignment.assignment_role,
                        "day_part": assignment.day_part,
                        "fallback_status": assignment.fallback_status,
                    }
                    for assignment in day.assignments
                ],
            }
            for day in proposal.days
        ]

    @classmethod
    def proposal_payload(cls, proposal: PlanningProposal) -> dict[str, Any]:
        """Serialize the complete editable aggregate for the HTTP boundary."""
        return {
            "round_id": proposal.round_id,
            "revision": proposal.revision,
            "exam_days": cls._proposal_days(proposal),
        }

    @classmethod
    def confirmed_plan_payload(cls, proposal: PlanningProposal) -> dict[str, Any]:
        """Serialize a revisioned confirmed aggregate without a mutation reason."""
        return cls.proposal_payload(proposal)

    def _protected_confirmed_day_ids(
        self,
        store: Store,
        proposal: PlanningProposal,
    ) -> set[int]:
        """Return confirmed-plan days whose operational state makes them immutable."""
        protected_day_ids: set[int] = set()
        for day in proposal.days:
            if day.id is None:
                raise ConfirmedPlanConflictError("Confirmed plan day identity is missing")
            current_day = store.get(EXAM_DAY, day.id)
            if (
                current_day is None
                or current_day["status"] != "confirmed"
                or current_day["closure_status"] != "open"
            ):
                protected_day_ids.add(day.id)
                continue
            for slot in store.where(EXAM_SLOT, exam_day_id=day.id):
                if (
                    slot["status"] != "confirmed"
                    or slot["execution_status"] != "open"
                    or slot["actual_started_at"] is not None
                    or slot["actual_completed_at"] is not None
                ):
                    protected_day_ids.add(day.id)
                    break
        return protected_day_ids

    @staticmethod
    def _raise_for_protected_confirmed_days_unchanged(
        before: PlanningProposal,
        proposed: PlanningProposal,
        protected_day_ids: set[int],
    ) -> None:
        """Keep each begun or terminal day aggregate exactly as it was read."""
        proposed_by_id = {day.id: day for day in proposed.days}
        for before_day in before.days:
            if before_day.id not in protected_day_ids:
                continue
            protected_proposal = proposed_by_id.get(before_day.id)
            if protected_proposal is None:
                raise ConfirmedPlanConflictError(
                    "Started, completed, or cancelled exam days cannot be changed"
                )
            if (
                PlanningService._restore_protected_server_state(before_day, protected_proposal)
                != before_day
            ):
                raise ConfirmedPlanConflictError(
                    "Started, completed, or cancelled exam days cannot be changed"
                )

    @staticmethod
    def _restore_protected_server_state(before: PlanDay, proposed: PlanDay) -> PlanDay:
        """Restore state fields which the revision payload deliberately cannot alter."""
        before_slots = {slot.id: slot for slot in before.slots}
        before_assignments = {assignment.id: assignment for assignment in before.assignments}
        return replace(
            proposed,
            status=before.status,
            slots=tuple(
                replace(
                    slot,
                    status=(
                        before_slots[slot.id].status if slot.id in before_slots else slot.status
                    ),
                )
                for slot in proposed.slots
            ),
            assignments=tuple(
                replace(
                    assignment,
                    fallback_status=(
                        before_assignments[assignment.id].fallback_status
                        if assignment.id in before_assignments
                        else assignment.fallback_status
                    ),
                )
                for assignment in proposed.assignments
            ),
        )

    @staticmethod
    def _raise_for_confirmed_plan_shape(
        before: PlanningProposal,
        proposed: PlanningProposal,
    ) -> None:
        """Require a complete update of the existing controlled aggregate."""
        issues: list[PlanValidationIssue] = []

        def identities(items: list[int | None]) -> set[int]:
            return {item for item in items if item is not None}

        def require_same(label: str, before_ids: list[int | None], proposed_ids: list[int | None]):
            expected = identities(before_ids)
            actual = identities(proposed_ids)
            if (
                len(actual) != len(proposed_ids)
                or len(expected) != len(before_ids)
                or actual != expected
            ):
                issues.append(
                    PlanValidationIssue(
                        "confirmed_plan_shape_invalid",
                        f"Confirmed plan {label} must retain every existing identity",
                    )
                )

        require_same("days", [day.id for day in before.days], [day.id for day in proposed.days])
        require_same(
            "slots",
            [slot.id for day in before.days for slot in day.slots],
            [slot.id for day in proposed.days for slot in day.slots],
        )
        require_same(
            "assignments",
            [assignment.id for day in before.days for assignment in day.assignments],
            [assignment.id for day in proposed.days for assignment in day.assignments],
        )
        if issues:
            raise PlanValidationError(issues)

    @staticmethod
    def _snapshot_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _revision_payload(revision: ConfirmedPlanRevision) -> dict[str, Any]:
        return {
            "id": revision.id,
            "previous_revision": revision.previous_revision,
            "resulting_revision": revision.resulting_revision,
            "reason": revision.reason,
            "actor_member_id": revision.actor_member_id,
            "before": json.loads(revision.before_state_json),
            "after": json.loads(revision.after_state_json),
            "created_at": revision.created_at,
        }

    def _raise_for_invalid_proposal(
        self,
        store: Store,
        proposal: PlanningProposal,
        *,
        status: str = "proposed",
    ) -> None:
        issues = self._validate_proposal(store, proposal, status=status)
        if issues:
            raise PlanValidationError(issues)

    def _validate_proposal(
        self,
        store: Store,
        proposal: PlanningProposal,
        *,
        status: str = "proposed",
    ) -> list[PlanValidationIssue]:
        """Apply every mandatory proposal invariant through one validation path."""
        issues: list[PlanValidationIssue] = []
        exam_round = store.get(EXAM_ROUND, proposal.round_id)
        settings = store.first(PLANNING_SETTINGS, exam_round_id=proposal.round_id)
        if exam_round is None:
            return [PlanValidationIssue("round_not_found", "Exam round not found")]
        if settings is None:
            return [PlanValidationIssue("settings_missing", "Planning settings not found")]
        if not proposal.days:
            issues.append(
                PlanValidationIssue("plan_empty", "A planning proposal needs at least one exam day")
            )
        context = self._proposal_validation_context(store, proposal, exam_round, settings)
        for day in proposal.days:
            self._validate_proposal_day(store, day, context, issues, status=status)
        self._validate_weekly_day_limits(context, issues)
        self._validate_candidate_requirements(store, proposal, context, issues)
        return issues

    def _proposal_validation_context(
        self,
        store: Store,
        proposal: PlanningProposal,
        exam_round: dict[str, Any],
        settings: dict[str, Any],
    ) -> _ProposalValidationContext:
        active_candidates = {
            row["id"]: row
            for row in store.where(
                ROUND_CANDIDATE,
                exam_round_id=proposal.round_id,
                is_active=1,
            )
        }
        candidate_days = {
            row["id"]: row
            for row in store.where(CANDIDATE_EXAM_DAY, exam_round_id=proposal.round_id)
        }
        availability = self._availability_index(
            store.where(MEMBER_AVAILABILITY, exam_round_id=proposal.round_id)
        )
        return _ProposalValidationContext(
            exam_round=exam_round,
            settings=settings,
            active_candidates=active_candidates,
            candidate_days=candidate_days,
            members={row["id"]: row for row in store.all(COMMITTEE_MEMBER)},
            availability=availability,
            blocked=self._blocked_person_ids(store, exam_round),
        )

    def _validate_proposal_day(
        self,
        store: Store,
        day: PlanDay,
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
        *,
        status: str,
    ) -> None:
        candidate_day = self._validated_candidate_day(day, context, issues)
        if candidate_day is None:
            return
        self._validate_exam_day_state(store, day, candidate_day, context, issues, status=status)
        self._validate_day_slots(day, candidate_day, context, issues, status=status)
        self._validate_day_assignments(day, candidate_day, context, issues)

    @staticmethod
    def _validated_candidate_day(
        day: PlanDay,
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> dict[str, Any] | None:
        candidate_day = context.candidate_days.get(day.candidate_exam_day_id)
        if day.candidate_exam_day_id in context.used_candidate_days:
            issues.append(
                PlanValidationIssue(
                    "candidate_day_duplicate",
                    "A candidate exam day may only occur once in a proposal",
                    day_id=day.id,
                )
            )
        context.used_candidate_days.add(day.candidate_exam_day_id)
        if candidate_day is None or not candidate_day["is_active"]:
            issues.append(
                PlanValidationIssue(
                    "candidate_day_inactive",
                    "Exam days must use an active candidate exam day of the round",
                    day_id=day.id,
                )
            )
            return None
        return candidate_day

    @staticmethod
    def _week_key(date: str) -> str:
        week = datetime.strptime(date, "%Y-%m-%d").isocalendar()
        return f"{week.year}-W{week.week:02d}"

    def _validate_exam_day_state(
        self,
        store: Store,
        day: PlanDay,
        candidate_day: dict[str, Any],
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
        *,
        status: str,
    ) -> None:
        if day.date != candidate_day["date"] or day.status != status:
            issues.append(
                PlanValidationIssue(
                    "exam_day_state_invalid",
                    "Exam-day date and status must match the active proposal day",
                    day_id=day.id,
                )
            )
        if not room_is_usable_for_committee(
            store.session, day.room_id, context.exam_round["committee_id"]
        ):
            issues.append(
                PlanValidationIssue(
                    "room_invalid",
                    "Exam-day room must be active and usable by the round committee",
                    day_id=day.id,
                )
            )
        if not day.slots:
            issues.append(
                PlanValidationIssue(
                    "exam_day_empty", "A proposal day needs at least one slot", day_id=day.id
                )
            )
        if len(day.slots) > context.settings["exams_per_day"]:
            issues.append(
                PlanValidationIssue(
                    "daily_capacity_exceeded",
                    "Exam-day capacity is exceeded",
                    day_id=day.id,
                )
            )
        context.days_by_week[self._week_key(candidate_day["date"])] += 1

    def _validate_day_slots(
        self,
        day: PlanDay,
        candidate_day: dict[str, Any],
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
        *,
        status: str,
    ) -> None:
        expected_times = self._slot_times(
            len(day.slots), bool(context.settings["lunch_break_enabled"])
        )
        seen_mep = False
        has_regular = False
        for index, (slot, (start, end)) in enumerate(
            zip(day.slots, expected_times, strict=True), start=1
        ):
            seen_mep, slot_is_regular = self._validate_slot(
                day, slot, candidate_day, context, issues, index, start, end, seen_mep, status
            )
            has_regular = has_regular or slot_is_regular
        if day.slots and not has_regular:
            issues.append(
                PlanValidationIssue(
                    "mep_only_day", "An exam day cannot contain only MEP slots", day_id=day.id
                )
            )

    @staticmethod
    def _validate_slot(
        day: PlanDay,
        slot: PlanSlot,
        candidate_day: dict[str, Any],
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
        index: int,
        start: str,
        end: str,
        seen_mep: bool,
        status: str,
    ) -> tuple[bool, bool]:
        if slot.round_candidate_id not in context.active_candidates:
            issues.append(
                PlanValidationIssue(
                    "round_candidate_invalid",
                    "Slots may only use active candidates of the round",
                    day_id=day.id,
                    slot_id=slot.id,
                )
            )
        if slot.slot_type not in {"regular", "mep"}:
            issues.append(
                PlanValidationIssue(
                    "slot_type_invalid",
                    "Unknown exam slot type",
                    day_id=day.id,
                    slot_id=slot.id,
                )
            )
        else:
            context.slot_counts[(slot.round_candidate_id, slot.slot_type)] += 1
        if slot.slot_type == "mep":
            seen_mep = True
        elif seen_mep:
            issues.append(
                PlanValidationIssue(
                    "mep_not_last",
                    "MEP slots must be at the end of their exam day",
                    day_id=day.id,
                    slot_id=slot.id,
                )
            )
        if (
            slot.sequence_number != index
            or slot.starts_at != f"{candidate_day['date']} {start}:00"
            or slot.ends_at != f"{candidate_day['date']} {end}:00"
            or slot.status != status
        ):
            issues.append(
                PlanValidationIssue(
                    "slot_schedule_invalid",
                    "Slot sequence and times must use the server-derived 60-minute schedule",
                    day_id=day.id,
                    slot_id=slot.id,
                )
            )
        return seen_mep, slot.slot_type == "regular"

    def _validate_day_assignments(
        self,
        day: PlanDay,
        candidate_day: dict[str, Any],
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> None:
        used_parts = ("morning", "afternoon") if len(day.slots) > 4 else ("morning",)
        for assignment in day.assignments:
            self._validate_assignment_shape(assignment, day, used_parts, issues)
        for part in used_parts:
            self._validate_crew(day, candidate_day, part, context, issues)

    @staticmethod
    def _validate_assignment_shape(
        assignment: PlanAssignment,
        day: PlanDay,
        used_parts: tuple[str, ...],
        issues: list[PlanValidationIssue],
    ) -> None:
        if assignment.assignment_role not in {"examiner", "fallback"}:
            issues.append(
                PlanValidationIssue(
                    "assignment_role_invalid",
                    "Assignments must be examiners or fallbacks",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )
        if assignment.day_part not in {"morning", "afternoon", "full_day"}:
            issues.append(
                PlanValidationIssue(
                    "assignment_day_part_invalid",
                    "Assignments need a valid day part",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )
        if assignment.day_part not in {*used_parts, "full_day"}:
            issues.append(
                PlanValidationIssue(
                    "assignment_day_part_unused",
                    "Assignments may only target a used day part",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )

    def _validate_crew(
        self,
        day: PlanDay,
        candidate_day: dict[str, Any],
        part: str,
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> None:
        applicable = [
            assignment
            for assignment in day.assignments
            if assignment.day_part in {part, "full_day"}
        ]
        examiners = [item for item in applicable if item.assignment_role == "examiner"]
        fallbacks = [item for item in applicable if item.assignment_role == "fallback"]
        examiner_sides = []
        for assignment in applicable:
            side = self._validate_assigned_member(
                assignment, day, candidate_day, part, context, issues
            )
            if side is not None:
                examiner_sides.append(side)
        if len(examiners) != 3 or set(examiner_sides) != set(SIDES):
            issues.append(
                PlanValidationIssue(
                    "examiner_crew_incomplete",
                    "Each used day part needs one examiner from every representing side",
                    day_id=day.id,
                )
            )
        if len(fallbacks) != 1:
            issues.append(
                PlanValidationIssue(
                    "fallback_missing",
                    "Each used day part needs exactly one fallback",
                    day_id=day.id,
                )
            )
        member_ids = [item.committee_member_id for item in applicable]
        if len(set(member_ids)) != len(member_ids):
            issues.append(
                PlanValidationIssue(
                    "assignment_member_duplicate",
                    "Examiner and fallback members must be distinct within a day part",
                    day_id=day.id,
                )
            )

    def _validate_assigned_member(
        self,
        assignment: PlanAssignment,
        day: PlanDay,
        candidate_day: dict[str, Any],
        part: str,
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> str | None:
        member = context.members.get(assignment.committee_member_id)
        if (
            member is None
            or not member["is_active"]
            or member["committee_id"] != context.exam_round["committee_id"]
        ):
            issues.append(
                PlanValidationIssue(
                    "member_invalid",
                    "Assignments require active members of the round committee",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )
            return None
        member_availability = context.availability.get(
            (assignment.committee_member_id, day.candidate_exam_day_id), "pending"
        )
        if not self._available_for(member_availability, part):
            issues.append(
                PlanValidationIssue(
                    "member_unavailable",
                    "Assigned members must be available for the day part",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )
        reservation = context.blocked.get((candidate_day["date"], part), {}).get(
            member["person_id"]
        )
        if reservation:
            issues.append(
                PlanValidationIssue(
                    "member_reserved",
                    f"Assigned member is already reserved by another {reservation}",
                    day_id=day.id,
                    member_id=assignment.committee_member_id,
                )
            )
        return member["representing_side"] if assignment.assignment_role == "examiner" else None

    @staticmethod
    def _validate_weekly_day_limits(
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> None:
        for week_key, count in context.days_by_week.items():
            if count > context.settings["max_exam_days_per_week"]:
                issues.append(
                    PlanValidationIssue(
                        "weekly_day_limit_exceeded",
                        f"Maximum exam days exceeded for {week_key}",
                    )
                )

    def _validate_candidate_requirements(
        self,
        store: Store,
        proposal: PlanningProposal,
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> None:
        for candidate_id, candidate in context.active_candidates.items():
            self._validate_candidate_slot_counts(candidate_id, candidate, context, issues)
            active_assignment = store.first(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                round_candidate_id=candidate_id,
                ended_at=None,
            )
            if active_assignment is None or active_assignment["exam_round_id"] != proposal.round_id:
                issues.append(
                    PlanValidationIssue(
                        "candidate_assignment_inactive",
                        "Candidates need an active responsibility assignment for this round",
                    )
                )

    @staticmethod
    def _validate_candidate_slot_counts(
        candidate_id: int,
        candidate: dict[str, Any],
        context: _ProposalValidationContext,
        issues: list[PlanValidationIssue],
    ) -> None:
        if context.slot_counts[(candidate_id, "regular")] != 1:
            issues.append(
                PlanValidationIssue(
                    "regular_slot_count_invalid",
                    "Every active candidate needs exactly one regular slot",
                    slot_id=None,
                )
            )
        expected_mep = 1 if candidate["requires_mep"] else 0
        if context.slot_counts[(candidate_id, "mep")] != expected_mep:
            issues.append(
                PlanValidationIssue(
                    "mep_slot_count_invalid",
                    "MEP slot count must match the active candidate assignment",
                    slot_id=None,
                )
            )

    def _load_context(self, store: Store, round_id: int) -> dict[str, Any]:
        exam_round = store.get(EXAM_ROUND, round_id)
        if exam_round is not None:
            round_model = store.session.get(ExamRound, round_id)
            exam_round["plan_revision"] = round_model.plan_revision if round_model else 0
        settings = store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        return {
            "round": exam_round,
            "settings": settings,
            "round_candidates": store.where(
                ROUND_CANDIDATE,
                exam_round_id=round_id,
                is_active=1,
            ),
            "candidates": {row["id"]: row for row in store.all(CANDIDATE)},
            "members": [
                row
                for row in store.where(
                    COMMITTEE_MEMBER,
                    committee_id=exam_round["committee_id"] if exam_round else -1,
                )
                if row["is_active"]
            ],
            "candidate_days": [
                row
                for row in store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
                if row["is_active"]
            ],
            "availability": store.where(MEMBER_AVAILABILITY, exam_round_id=round_id),
            "blocked_person_ids": self._blocked_person_ids(store, exam_round),
        }

    def _blocked_person_ids(
        self,
        store: Store,
        exam_round: dict[str, Any] | None,
    ) -> dict[tuple[str, str], dict[int, str]]:
        """Reserve people per half-year and day part for existing plans.

        Confirmed plans have precedence over proposals.  A proposal is still a
        reservation for another proposal so independently generated plans do
        not double-book a person while both are awaiting confirmation.
        """
        blocked: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
        if exam_round is None:
            return blocked
        for assignment in store.all(EXAM_DAY_ASSIGNMENT):
            exam_day = store.get(EXAM_DAY, assignment["exam_day_id"])
            member = store.get(COMMITTEE_MEMBER, assignment["committee_member_id"])
            other_round = store.get(EXAM_ROUND, exam_day["exam_round_id"]) if exam_day else None
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

    def _clear_existing_proposal(self, store: Store, round_id: int) -> None:
        for exam_day in store.where(EXAM_DAY, exam_round_id=round_id):
            if exam_day["status"] == "confirmed":
                raise ValueError("Confirmed exam days cannot be replaced")
            store.delete(EXAM_DAY, exam_day["id"])

    def _build_proposal(self, context: dict[str, Any]) -> dict[str, Any]:
        settings = context["settings"]
        if settings["default_room_id"] is None:
            raise ValueError("Planning settings need a default room")
        round_candidates = sorted(context["round_candidates"], key=lambda row: row["id"])
        regular_queue = list(round_candidates)
        mep_queue = [row for row in round_candidates if row["requires_mep"]]
        required_slots = len(regular_queue) + len(mep_queue)
        remaining_slots = required_slots
        load: dict[int, float] = defaultdict(float)
        days_by_week = self._days_by_week(context["candidate_days"])
        availability = self._availability_index(context["availability"])
        validation = {"passed": True, "messages": []}
        planned_days: list[dict[str, Any]] = []

        for week_key in sorted(days_by_week):
            options = self._planning_options_for_week(
                context, days_by_week[week_key], availability, load, validation
            )
            remaining_slots = self._plan_week(
                context,
                options,
                availability,
                load,
                validation,
                planned_days,
                remaining_slots,
            )
        return self._proposal_build_result(
            planned_days, regular_queue, mep_queue, required_slots, remaining_slots, validation
        )

    def _planning_options_for_week(
        self,
        context: dict[str, Any],
        week_days: list[dict[str, Any]],
        availability: dict[tuple[int, int], str],
        load: dict[int, float],
        validation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        options = []
        for day in sorted(week_days, key=lambda row: row["date"]):
            morning = self._choose_shift_crew(context, availability, day["id"], "morning", load)
            if morning is None:
                validation["messages"].append(
                    f"{day['date']}: keine vollstaendige Vormittagsbesetzung"
                )
                conflict = self._reservation_message(context, day["date"], "morning")
                if conflict:
                    validation["messages"].append(conflict)
                continue
            afternoon = self._choose_shift_crew(context, availability, day["id"], "afternoon", load)
            capacity = context["settings"]["exams_per_day"]
            if capacity > 4 and afternoon is None:
                capacity = 4
            options.append({"day": day, "capacity": capacity})
        return sorted(options, key=lambda option: (-option["capacity"], option["day"]["date"]))

    def _plan_week(
        self,
        context: dict[str, Any],
        options: list[dict[str, Any]],
        availability: dict[tuple[int, int], str],
        load: dict[int, float],
        validation: dict[str, Any],
        planned_days: list[dict[str, Any]],
        remaining_slots: int,
    ) -> int:
        used_days = 0
        for option in options:
            if remaining_slots <= 0 or used_days >= context["settings"]["max_exam_days_per_week"]:
                break
            planned_day = self._plan_day_option(
                context, option, availability, load, validation, remaining_slots
            )
            if planned_day is None:
                continue
            self._apply_load(load, planned_day["morning"])
            if planned_day["afternoon"]:
                self._apply_load(load, planned_day["afternoon"])
            planned_days.append(planned_day)
            remaining_slots -= planned_day["exams"]
            used_days += 1
        return remaining_slots

    def _plan_day_option(
        self,
        context: dict[str, Any],
        option: dict[str, Any],
        availability: dict[tuple[int, int], str],
        load: dict[int, float],
        validation: dict[str, Any],
        remaining_slots: int,
    ) -> dict[str, Any] | None:
        exams = min(option["capacity"], remaining_slots)
        needs_afternoon = exams > 4
        morning = self._choose_shift_crew(
            context, availability, option["day"]["id"], "morning", load
        )
        afternoon = (
            self._choose_shift_crew(context, availability, option["day"]["id"], "afternoon", load)
            if needs_afternoon
            else None
        )
        if morning is None or (needs_afternoon and afternoon is None):
            missing_part = "morning" if morning is None else "afternoon"
            conflict = self._reservation_message(context, option["day"]["date"], missing_part)
            if conflict:
                validation["messages"].append(conflict)
            return None
        return {
            "date": option["day"]["date"],
            "candidate_exam_day_id": option["day"]["id"],
            "exams": exams,
            "morning": morning,
            "afternoon": afternoon,
            "regular_candidate_ids": [],
            "mep_candidate_ids": [],
        }

    def _proposal_build_result(
        self,
        planned_days: list[dict[str, Any]],
        regular_queue: list[dict[str, Any]],
        mep_queue: list[dict[str, Any]],
        required_slots: int,
        remaining_slots: int,
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        self._assign_candidates(planned_days, regular_queue, mep_queue)
        validation["passed"] = remaining_slots == 0 and not regular_queue and not mep_queue
        if remaining_slots:
            validation["messages"].append(
                f"Fuer {remaining_slots} Pruefungstermine fehlt Kapazitaet"
            )
        if regular_queue:
            validation["messages"].append(
                f"{len(regular_queue)} regulaere Pruefungen konnten nicht platziert werden"
            )
        if mep_queue:
            validation["messages"].append(
                f"{len(mep_queue)} MEP-Termine konnten nicht regelkonform platziert werden"
            )
        if not planned_days:
            validation["messages"].append("Es konnte kein Pruefungstag geplant werden")

        planned_slots = sum(day["exams"] for day in planned_days)
        return {
            "days": planned_days,
            "validation": validation,
            "counts": {
                "required_slots": required_slots,
                "planned_slots": planned_slots,
                "regular_slots": sum(len(day["regular_candidate_ids"]) for day in planned_days),
                "mep_slots": sum(len(day["mep_candidate_ids"]) for day in planned_days),
            },
        }

    def _choose_shift_crew(
        self,
        context: dict[str, Any],
        availability: dict[tuple[int, int], str],
        candidate_exam_day_id: int,
        day_part: str,
        load: dict[int, float],
    ) -> ShiftCrew | None:
        candidate_day = next(
            (day for day in context["candidate_days"] if day["id"] == candidate_exam_day_id),
            None,
        )
        blocked = context["blocked_person_ids"].get(
            (candidate_day["date"], day_part) if candidate_day else ("", day_part),
            {},
        )
        available_members = [
            member
            for member in context["members"]
            if member["person_id"] not in blocked
            if self._available_for(
                availability.get((member["id"], candidate_exam_day_id), "pending"),
                day_part,
            )
        ]
        crew = []
        for side in SIDES:
            options = [
                member
                for member in available_members
                if member["representing_side"] == side and member["id"] not in crew
            ]
            options.sort(key=lambda member: (load[member["id"]], member["id"]))
            if not options:
                return None
            crew.append(options[0]["id"])
        fallback_options = [member for member in available_members if member["id"] not in set(crew)]
        fallback_options.sort(key=lambda member: (load[member["id"]], member["id"]))
        if not fallback_options:
            return None
        return ShiftCrew(tuple(crew), fallback_options[0]["id"])

    def _available_for(self, availability: str, day_part: str) -> bool:
        if availability == "full_day":
            return True
        return availability == day_part

    def _reservation_message(
        self,
        context: dict[str, Any],
        date: str,
        day_part: str,
    ) -> str | None:
        reservations = context["blocked_person_ids"].get((date, day_part), {})
        if not reservations:
            return None
        confirmed = any(value == "bestätigten Termin" for value in reservations.values())
        label = "Vormittag" if day_part == "morning" else "Nachmittag"
        priority = "bestätigte Termine" if confirmed else "andere Planungsvorschläge"
        return f"{date} ({label}): Personen sind durch {priority} in anderen Ausschüssen reserviert"

    def _apply_load(self, load: dict[int, float], shift: ShiftCrew) -> None:
        for member_id in shift.crew:
            load[member_id] += 1
        load[shift.fallback] += 0.35

    def _assign_candidates(
        self,
        planned_days: list[dict[str, Any]],
        regular_queue: list[dict[str, Any]],
        mep_queue: list[dict[str, Any]],
    ) -> None:
        mep_counts_by_index = [0 for _ in planned_days]
        for index in reversed(range(len(planned_days))):
            day = planned_days[index]
            mep_capacity = max(0, day["exams"] - 1)
            count = min(mep_capacity, len(mep_queue))
            mep_counts_by_index[index] = count
            for _ in range(count):
                day["mep_candidate_ids"].append(mep_queue.pop(0)["id"])

        for index, day in enumerate(planned_days):
            regular_count = day["exams"] - mep_counts_by_index[index]
            day["regular_candidate_ids"] = [
                regular_queue.pop(0)["id"] for _ in range(min(regular_count, len(regular_queue)))
            ]

    def _slot_times(self, count: int, lunch_break: bool) -> list[tuple[str, str]]:
        starts = []
        current = datetime.strptime("08:30", "%H:%M")
        lunch = datetime.strptime("12:30", "%H:%M")
        lunch_end = datetime.strptime("13:30", "%H:%M")
        for _ in range(count):
            if lunch_break and current == lunch:
                current = lunch_end
            end = current + timedelta(hours=1)
            starts.append((current.strftime("%H:%M"), end.strftime("%H:%M")))
            current = end
        return starts

    def _availability_index(
        self,
        rows: list[dict[str, Any]],
    ) -> dict[tuple[int, int], str]:
        return {
            (row["committee_member_id"], row["candidate_exam_day_id"]): row["availability"]
            for row in rows
        }

    def _days_by_week(
        self,
        candidate_days: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for day in candidate_days:
            week = datetime.strptime(day["date"], "%Y-%m-%d").isocalendar()
            grouped[f"{week.year}-W{week.week:02d}"].append(day)
        return grouped
