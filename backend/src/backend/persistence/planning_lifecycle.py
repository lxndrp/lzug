"""SQLite adapter for Planning lifecycle facts in an existing transaction."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.lifecycle_ports import (
    PlanAssignmentLifecycleSnapshot,
    PlanningCandidateLifecycleSnapshot,
    PlanningRoundLifecycleSnapshot,
    PlanSlotLifecycleSnapshot,
)
from backend.persistence.models import (
    Candidate,
    CandidateCommitteeAssignment,
    CandidateExamDay,
    ConfirmedPlanRevision,
    ExamDay,
    ExamDayAssignment,
    ExamHalfYear,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    PlanConsequence,
    PlanConsequenceBatch,
    PlanningSettings,
    RoundCandidate,
)


class SQLitePlanningLifecycleWork:
    """Hide Planning-owned schema reads and writes behind detached values."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def round_lifecycle_snapshot(self, round_id: int) -> PlanningRoundLifecycleSnapshot | None:
        row = self._session.get(ExamRound, round_id)
        if row is None:
            return None
        return PlanningRoundLifecycleSnapshot(
            id=row.id,
            exam_half_year_id=row.exam_half_year_id,
            committee_id=row.committee_id,
            name=row.name,
            status=row.status,
            revision=row.revision,
            lifecycle_status=row.lifecycle_status,
            legacy_status=row.legacy_status,
        )

    def advance_round_lifecycle(
        self,
        round_id: int,
        expected_revision: int,
        now: str,
        *,
        lifecycle_status: str | None = None,
    ) -> bool:
        values = {"revision": ExamRound.revision + 1, "updated_at": now}
        if lifecycle_status is not None:
            values["lifecycle_status"] = lifecycle_status
        result = self._session.execute(
            update(ExamRound)
            .where(ExamRound.id == round_id, ExamRound.revision == expected_revision)
            .values(**values)
        )
        return result.rowcount == 1

    def delete_empty_draft_round(self, round_id: int, expected_revision: int) -> bool:
        result = self._session.execute(
            delete(ExamRound).where(
                ExamRound.id == round_id,
                ExamRound.revision == expected_revision,
                ExamRound.status == "draft",
                ExamRound.lifecycle_status == "open",
            )
        )
        return result.rowcount == 1

    def round_candidates(self, round_id: int) -> tuple[dict[str, Any], ...]:
        rows = self._session.scalars(
            select(RoundCandidate)
            .where(RoundCandidate.exam_round_id == round_id)
            .order_by(RoundCandidate.id)
        )
        return tuple(self._candidate(row) for row in rows)

    def candidate_details(self, candidate_ids):
        if not candidate_ids:
            return ()
        return tuple(
            PlanningCandidateLifecycleSnapshot(
                id=row.id,
                first_name=row.first_name,
                last_name=row.last_name,
                ihk_exam_number=row.ihk_exam_number,
            )
            for row in self._session.scalars(
                select(Candidate).where(Candidate.id.in_(candidate_ids)).order_by(Candidate.id)
            )
        )

    def round_candidate(self, round_id: int, candidate_id: int) -> dict[str, Any] | None:
        row = self._session.get(RoundCandidate, candidate_id)
        if row is None or row.exam_round_id != round_id:
            return None
        return self._candidate(row)

    def candidate_assignment(self, round_candidate_id: int, round_id: int) -> dict[str, Any] | None:
        row = self._session.scalar(
            select(CandidateCommitteeAssignment).where(
                CandidateCommitteeAssignment.round_candidate_id == round_candidate_id,
                CandidateCommitteeAssignment.exam_round_id == round_id,
            )
        )
        if row is None:
            return None
        return {"ended_at": row.ended_at}

    def effective_transfer_exists(
        self, source_half_year_id: int, target_round_id: int, candidate_id: int
    ) -> bool:
        target_round = self._session.get(ExamRound, target_round_id)
        if target_round is None or target_round.exam_half_year_id != source_half_year_id:
            return False
        return (
            self._session.scalar(
                select(CandidateCommitteeAssignment.id).where(
                    CandidateCommitteeAssignment.candidate_id == candidate_id,
                    CandidateCommitteeAssignment.exam_round_id == target_round_id,
                    CandidateCommitteeAssignment.ended_at.is_(None),
                )
            )
            is not None
        )

    def update_candidate_terminal(
        self,
        round_id: int,
        round_candidate_id: int,
        values,
        *,
        ended_at: str | None,
        change_reason: str | None,
    ) -> bool:
        candidate = self._session.get(RoundCandidate, round_candidate_id)
        if candidate is None or candidate.exam_round_id != round_id:
            return False
        assignment = self._session.scalar(
            select(CandidateCommitteeAssignment).where(
                CandidateCommitteeAssignment.round_candidate_id == candidate.id,
                CandidateCommitteeAssignment.exam_round_id == round_id,
            )
        )
        for name, value in values.items():
            setattr(candidate, name, value)
        if ended_at is not None and assignment is not None and assignment.ended_at is None:
            assignment.ended_at = ended_at
            assignment.change_reason = change_reason
            assignment.updated_at = ended_at
        return True

    def original_assignment_ended(self, round_candidate_id: int, round_id: int) -> bool:
        assignment = self._session.scalar(
            select(CandidateCommitteeAssignment).where(
                CandidateCommitteeAssignment.round_candidate_id == round_candidate_id,
                CandidateCommitteeAssignment.exam_round_id == round_id,
            )
        )
        return assignment is not None and assignment.ended_at is not None

    def lifecycle_context(self, round_id: int, half_year_id: int, candidate_ids):
        half_year = self._session.get(ExamHalfYear, half_year_id)
        assignments = (
            self._session.scalars(
                select(CandidateCommitteeAssignment)
                .where(
                    CandidateCommitteeAssignment.exam_half_year_id == half_year_id,
                    CandidateCommitteeAssignment.candidate_id.in_(candidate_ids),
                )
                .order_by(CandidateCommitteeAssignment.id)
            )
            if candidate_ids
            else ()
        )
        revisions = self._session.scalars(
            select(ConfirmedPlanRevision)
            .where(ConfirmedPlanRevision.exam_round_id == round_id)
            .order_by(ConfirmedPlanRevision.id)
        )
        pending = self._session.scalars(
            select(PlanConsequence.id)
            .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
            .join(
                ConfirmedPlanRevision,
                ConfirmedPlanRevision.id == PlanConsequenceBatch.confirmed_plan_revision_id,
            )
            .where(
                ConfirmedPlanRevision.exam_round_id == round_id,
                PlanConsequence.status.in_({"pending", "temporarily_failed"}),
            )
        )
        return {
            "half_year": (
                {
                    "id": half_year.id,
                    "season": half_year.season,
                    "year": half_year.year,
                    "status": half_year.status,
                    "legacy_status": half_year.legacy_status,
                }
                if half_year is not None
                else None
            ),
            "candidate_assignment_history": tuple(
                {
                    "id": row.id,
                    "candidate_id": row.candidate_id,
                    "exam_round_id": row.exam_round_id,
                    "round_candidate_id": row.round_candidate_id,
                    "assigned_at": row.assigned_at,
                    "ended_at": row.ended_at,
                    "change_reason": row.change_reason,
                }
                for row in assignments
            ),
            "plan_revisions": tuple(
                {
                    "id": row.id,
                    "previous_revision": row.previous_revision,
                    "resulting_revision": row.resulting_revision,
                    "reason": row.reason,
                    "actor_member_id": row.actor_member_id,
                    "created_at": row.created_at,
                }
                for row in revisions
            ),
            "pending_consequence_ids": tuple(pending),
        }

    def lifecycle_candidate_ids(self, round_id: int) -> set[int]:
        return set(
            self._session.scalars(
                select(RoundCandidate.id).where(RoundCandidate.exam_round_id == round_id)
            )
        )

    def mutation_target(self, resource: str, identifier: int | None, payload):
        resources = {
            "planning-settings": (PlanningSettings, "exam_round_id", "planning"),
            "candidate-exam-days": (CandidateExamDay, "exam_round_id", "planning"),
            "member-availabilities": (MemberAvailability, "exam_round_id", "availability"),
            "round-candidates": (RoundCandidate, "exam_round_id", "candidate_assignment"),
        }
        selected = resources.get(resource)
        if selected is None:
            return None
        model, round_field, kind = selected
        row = self._session.get(model, identifier) if identifier is not None else None
        round_id = getattr(row, round_field) if row is not None else payload.get(round_field)
        if not isinstance(round_id, int) or isinstance(round_id, bool):
            return None
        entity_id = round_id if kind in {"planning", "availability"} else (identifier or round_id)
        return round_id, entity_id

    def dependency_counts(self, round_id: int) -> dict[str, int]:
        return {
            "Prüflinge": self._count(RoundCandidate, RoundCandidate.exam_round_id == round_id),
            "Verfügbarkeiten": self._count(
                MemberAvailability, MemberAvailability.exam_round_id == round_id
            ),
            "Planungsparameter": self._count(
                PlanningSettings, PlanningSettings.exam_round_id == round_id
            ),
            "Planrevisionen": self._count(
                ConfirmedPlanRevision, ConfirmedPlanRevision.exam_round_id == round_id
            ),
        }

    def exam_day_plan(self, day_id: int):
        slots = tuple(
            PlanSlotLifecycleSnapshot(
                id=row.id,
                exam_day_id=row.exam_day_id,
                round_candidate_id=row.round_candidate_id,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                execution_status=row.execution_status,
                status_reason=row.status_reason,
                actual_started_at=row.actual_started_at,
                actual_completed_at=row.actual_completed_at,
            )
            for row in self._session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id == day_id).order_by(ExamSlot.id)
            )
        )
        assignments = tuple(
            PlanAssignmentLifecycleSnapshot(
                id=row.id,
                exam_day_id=row.exam_day_id,
                committee_member_id=row.committee_member_id,
                assignment_role=row.assignment_role,
                day_part=row.day_part,
                fallback_status=row.fallback_status,
            )
            for row in self._session.scalars(
                select(ExamDayAssignment)
                .where(ExamDayAssignment.exam_day_id == day_id)
                .order_by(ExamDayAssignment.id)
            )
        )
        return slots, assignments

    def exam_day_assignments(self, day_ids):
        if not day_ids:
            return ()
        return tuple(
            PlanAssignmentLifecycleSnapshot(
                id=row.id,
                exam_day_id=row.exam_day_id,
                committee_member_id=row.committee_member_id,
                assignment_role=row.assignment_role,
                day_part=row.day_part,
                fallback_status=row.fallback_status,
            )
            for row in self._session.scalars(
                select(ExamDayAssignment)
                .where(ExamDayAssignment.exam_day_id.in_(day_ids))
                .order_by(ExamDayAssignment.id)
            )
        )

    def exam_day_slots(self, day_ids):
        if not day_ids:
            return ()
        return tuple(
            PlanSlotLifecycleSnapshot(
                id=row.id,
                exam_day_id=row.exam_day_id,
                round_candidate_id=row.round_candidate_id,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                execution_status=row.execution_status,
                status_reason=row.status_reason,
                actual_started_at=row.actual_started_at,
                actual_completed_at=row.actual_completed_at,
            )
            for row in self._session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id.in_(day_ids)).order_by(ExamSlot.id)
            )
        )

    def exam_day_slot_ids(self, day_ids):
        if not day_ids:
            return ()
        return tuple(
            self._session.scalars(
                select(ExamSlot.id).where(ExamSlot.exam_day_id.in_(day_ids)).order_by(ExamSlot.id)
            )
        )

    def round_id_for_slot(self, slot_id):
        return self._session.scalar(
            select(ExamDay.exam_round_id)
            .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
            .where(ExamSlot.id == slot_id)
        )

    def round_committee_id(self, round_id):
        return self._session.scalar(select(ExamRound.committee_id).where(ExamRound.id == round_id))

    def cancel_exam_day_slots(self, day_ids, now):
        if not day_ids:
            return
        for slot in self._session.scalars(
            select(ExamSlot).where(ExamSlot.exam_day_id.in_(day_ids))
        ):
            slot.status = "cancelled"
            slot.execution_status = "cancelled"
            slot.status_reason = "Prüfungsrunde vollständig abgesagt"
            slot.status_changed_at = now
            slot.updated_at = now

    def _count(self, model, criterion) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(model).where(criterion)) or 0
        )

    @staticmethod
    def _candidate(row) -> dict[str, Any]:
        return {
            "id": row.id,
            "exam_round_id": row.exam_round_id,
            "candidate_id": row.candidate_id,
            "terminal_status": row.terminal_status,
            "terminal_reason": row.terminal_reason,
            "effective_new_round_id": row.effective_new_round_id,
            "postponed_until": row.postponed_until,
            "ihk_decision_reference": row.ihk_decision_reference,
            "terminal_at": row.terminal_at,
            "is_active": row.is_active,
        }
