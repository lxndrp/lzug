from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from sqlalchemy import text

from backend.database import connect
from backend.models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    LOCATION,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.planning import PlanConflictError, PlanningService, PlanValidationError
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class PlanningTests(unittest.TestCase):
    def test_request_availabilities_moves_prepared_draft_into_coordination(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            repository.update(EXAM_ROUND, 1, {"status": "draft"})

            requested = PlanningService(db_path).request_availabilities(1)
            persisted = repository.get(EXAM_ROUND, 1)

        self.assertEqual("availability_requested", requested["status"])
        self.assertEqual("availability_requested", persisted["status"])

    def test_missing_round_is_rejected(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with self.assertRaisesRegex(ValueError, "Exam round not found"):
                PlanningService(db_path).generate_proposal(1)

    def test_missing_planning_settings_are_rejected(self) -> None:
        with TempDatabase() as db_path:
            with connect(db_path) as connection:
                connection.execute(text("DELETE FROM planning_settings"))
                connection.commit()

            with self.assertRaisesRegex(ValueError, "Planning settings not found"):
                PlanningService(db_path).generate_proposal(1)

    def test_no_active_candidate_days_are_rejected(self) -> None:
        with TempDatabase() as db_path:
            with connect(db_path) as connection:
                connection.execute(text("DELETE FROM candidate_exam_day"))
                connection.commit()

            with self.assertRaisesRegex(ValueError, "No active candidate exam days found"):
                PlanningService(db_path).generate_proposal(1)

    def test_confirmation_without_proposal_is_rejected(self) -> None:
        with TempDatabase() as db_path:
            with self.assertRaisesRegex(ValueError, "No planning proposal found"):
                PlanningService(db_path).confirm_plan(1)

    def test_generate_proposal_persists_days_slots_assignments(self) -> None:
        with TempDatabase() as db_path:
            proposal = PlanningService(db_path).generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            exam_slots = repository.list(EXAM_SLOT)
            assignments = repository.list(EXAM_DAY_ASSIGNMENT)
            exam_round = repository.get(EXAM_ROUND, 1)

        self.assertTrue(proposal["validation"]["passed"])
        self.assertEqual("plan_proposed", proposal["status"])
        self.assertEqual("plan_proposed", exam_round["status"])
        self.assertEqual(16, proposal["counts"]["planned_slots"])
        self.assertEqual(16, len(exam_slots))
        self.assertGreaterEqual(len(exam_days), 3)
        self.assertGreaterEqual(len(assignments), len(exam_days) * 4)

    def test_mep_slots_are_at_the_end_of_each_day(self) -> None:
        with TempDatabase() as db_path:
            PlanningService(db_path).generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            slots = repository.list(EXAM_SLOT)

        for exam_day in exam_days:
            day_slots = [slot for slot in slots if slot["exam_day_id"] == exam_day["id"]]
            slot_types = [slot["slot_type"] for slot in day_slots]
            if "mep" in slot_types:
                first_mep = slot_types.index("mep")
                self.assertTrue(all(slot_type == "mep" for slot_type in slot_types[first_mep:]))
                self.assertIn("regular", slot_types[:first_mep])

    def test_generate_proposal_replaces_existing_proposal(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            first = service.generate_proposal(1)
            second = service.generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_slots = repository.list(EXAM_SLOT)

        self.assertEqual(16, first["counts"]["planned_slots"])
        self.assertEqual(16, second["counts"]["planned_slots"])
        self.assertEqual(16, len(exam_slots))

    def test_complete_proposal_can_be_read_reordered_and_saved_with_new_revision(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            generated = service.generate_proposal(1)
            proposal = service.get_proposal(1)
            first_day = proposal.days[0]
            regular = [slot for slot in first_day.slots if slot.slot_type == "regular"]
            mep = [slot for slot in first_day.slots if slot.slot_type == "mep"]
            changed = replace(
                proposal,
                days=(
                    replace(first_day, slots=tuple([*reversed(regular), *mep])),
                    *proposal.days[1:],
                ),
            )

            saved = service.save_proposal(changed)
            persisted = service.get_proposal(1)

        self.assertEqual(1, generated["revision"])
        self.assertEqual(1, proposal.revision)
        self.assertEqual(2, saved.revision)
        self.assertEqual(saved, persisted)
        self.assertEqual(
            [slot.round_candidate_id for slot in reversed(regular)],
            [slot.round_candidate_id for slot in saved.days[0].slots[: len(regular)]],
        )
        self.assertEqual(
            list(range(1, len(saved.days[0].slots) + 1)),
            [slot.sequence_number for slot in saved.days[0].slots],
        )
        self.assertEqual("2026-11-16 08:30:00", saved.days[0].slots[0].starts_at)

    def test_stale_revision_and_validation_failure_leave_proposal_unchanged(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            original = service.get_proposal(1)
            saved = service.save_proposal(original)

            with self.assertRaises(PlanConflictError):
                service.save_proposal(original)

            invalid_slot = replace(
                saved.days[0].slots[0],
                round_candidate_id=saved.days[0].slots[1].round_candidate_id,
            )
            invalid = replace(
                saved,
                days=(
                    replace(
                        saved.days[0],
                        slots=(invalid_slot, *saved.days[0].slots[1:]),
                    ),
                    *saved.days[1:],
                ),
            )
            with self.assertRaises(PlanValidationError) as error:
                service.save_proposal(invalid)
            unchanged = service.get_proposal(1)

        self.assertTrue(
            {"regular_slot_count_invalid", "mep_slot_count_invalid"}
            & {issue.code for issue in error.exception.issues}
        )
        self.assertEqual(saved, unchanged)

    def test_status_conflict_and_persistence_error_roll_back_revision_and_rows(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            original = service.get_proposal(1)

            with connect(db_path) as connection:
                connection.execute(
                    text("UPDATE exam_round SET status = 'availability_closed' WHERE id = 1")
                )
                connection.commit()
            with self.assertRaises(PlanConflictError):
                service.save_proposal(original)
            with connect(db_path) as connection:
                connection.execute(
                    text("UPDATE exam_round SET status = 'plan_proposed' WHERE id = 1")
                )
                connection.commit()

            persist = service._persist_aggregate

            def persist_partly_then_fail(store, proposal):
                persist(store, replace(proposal, days=proposal.days[:1]))
                raise RuntimeError("simulated persistence failure")

            with patch.object(
                service,
                "_persist_aggregate",
                side_effect=persist_partly_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated persistence failure"):
                    service.save_proposal(original)
            unchanged = service.get_proposal(1)

        self.assertEqual(original, unchanged)

    def test_confirmation_reuses_full_validator(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            proposal = service.get_proposal(1)
            with connect(db_path) as connection:
                connection.execute(
                    text("UPDATE exam_slot SET starts_at = '2026-11-16 09:00:00' WHERE id = :id"),
                    {"id": proposal.days[0].slots[0].id},
                )
                connection.commit()

            with self.assertRaises(PlanValidationError) as error:
                service.confirm_plan(1)
            repository = ResourceRepository(db_path)
            exam_round = repository.get(EXAM_ROUND, 1)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})

        self.assertIn("slot_schedule_invalid", {issue.code for issue in error.exception.issues})
        self.assertEqual("plan_proposed", exam_round["status"])
        self.assertTrue(all(day["status"] == "proposed" for day in exam_days))

    def test_generic_writes_cannot_bypass_plan_aggregate(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            proposal = service.get_proposal(1)
            repository = ResourceRepository(db_path)

            for resource, resource_id in (
                (EXAM_DAY, proposal.days[0].id),
                (EXAM_SLOT, proposal.days[0].slots[0].id),
                (EXAM_DAY_ASSIGNMENT, proposal.days[0].assignments[0].id),
            ):
                with self.subTest(resource=resource.table):
                    with self.assertRaisesRegex(ValueError, "planning aggregate"):
                        repository.create(resource, {})
                    with self.assertRaisesRegex(ValueError, "planning aggregate"):
                        repository.update(resource, resource_id, {})
                    with self.assertRaisesRegex(ValueError, "planning aggregate"):
                        repository.delete(resource, resource_id)

    def test_validator_covers_day_slot_location_crew_and_capacity_rules(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            proposal = service.get_proposal(1)
            repository = ResourceRepository(db_path)

            invalid_location = replace(
                proposal,
                days=(replace(proposal.days[0], location_id=999999), *proposal.days[1:]),
            )
            with self.assertRaises(PlanValidationError) as location_error:
                service.save_proposal(invalid_location)

            without_fallback = replace(
                proposal,
                days=(
                    replace(
                        proposal.days[0],
                        assignments=tuple(
                            assignment
                            for assignment in proposal.days[0].assignments
                            if not (
                                assignment.assignment_role == "fallback"
                                and assignment.day_part == "morning"
                            )
                        ),
                    ),
                    *proposal.days[1:],
                ),
            )
            with self.assertRaises(PlanValidationError) as crew_error:
                service.save_proposal(without_fallback)

            mep_day_index = next(
                index
                for index, day in enumerate(proposal.days)
                if any(slot.slot_type == "mep" for slot in day.slots)
            )
            mep_day = proposal.days[mep_day_index]
            mep_slots = [slot for slot in mep_day.slots if slot.slot_type == "mep"]
            regular_slots = [slot for slot in mep_day.slots if slot.slot_type == "regular"]
            reordered_days = list(proposal.days)
            reordered_days[mep_day_index] = replace(
                mep_day,
                slots=tuple([mep_slots[0], *regular_slots, *mep_slots[1:]]),
            )
            with self.assertRaises(PlanValidationError) as mep_error:
                service.save_proposal(replace(proposal, days=tuple(reordered_days)))

            settings = repository.list_filtered(PLANNING_SETTINGS, {"exam_round_id": 1})[0]
            repository.update(PLANNING_SETTINGS, settings["id"], {"exams_per_day": 1})
            with self.assertRaises(PlanValidationError) as capacity_error:
                service.save_proposal(proposal)
            repository.update(
                PLANNING_SETTINGS,
                settings["id"],
                {"exams_per_day": settings["exams_per_day"]},
            )

            candidate_day = repository.get(
                CANDIDATE_EXAM_DAY, proposal.days[0].candidate_exam_day_id
            )
            repository.update(CANDIDATE_EXAM_DAY, candidate_day["id"], {"is_active": 0})
            with self.assertRaises(PlanValidationError) as day_error:
                service.save_proposal(proposal)

        self.assertIn("location_invalid", {issue.code for issue in location_error.exception.issues})
        self.assertIn("fallback_missing", {issue.code for issue in crew_error.exception.issues})
        self.assertIn("mep_not_last", {issue.code for issue in mep_error.exception.issues})
        self.assertIn(
            "daily_capacity_exceeded",
            {issue.code for issue in capacity_error.exception.issues},
        )
        self.assertIn(
            "candidate_day_inactive",
            {issue.code for issue in day_error.exception.issues},
        )

    def test_confirm_plan_updates_statuses_and_blocks_replacement(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            confirmed = service.confirm_plan(1)
            repository = ResourceRepository(db_path)
            exam_round = repository.get(EXAM_ROUND, 1)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            exam_slots = repository.list(EXAM_SLOT)
            assignments = repository.list(EXAM_DAY_ASSIGNMENT)

            with self.assertRaises(ValueError):
                service.generate_proposal(1)

        self.assertEqual("plan_confirmed", confirmed["status"])
        self.assertEqual("plan_confirmed", exam_round["status"])
        self.assertTrue(all(day["status"] == "confirmed" for day in exam_days))
        self.assertTrue(all(slot["status"] == "confirmed" for slot in exam_slots))
        self.assertTrue(
            all(
                assignment["fallback_status"] == "confirmed"
                for assignment in assignments
                if assignment["assignment_role"] == "fallback"
            )
        )

    def test_confirmed_other_committee_reservation_blocks_proposal(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            other_round = self._create_overlapping_round(repository)
            for member_id in range(5, 9):
                repository.update(COMMITTEE_MEMBER, member_id, {"is_active": 0})

            PlanningService(db_path).generate_proposal(other_round["id"])
            PlanningService(db_path).confirm_plan(other_round["id"])
            with self.assertRaises(PlanValidationError) as error:
                PlanningService(db_path).generate_proposal(1)
            exam_round = repository.get(EXAM_ROUND, 1)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})

        self.assertTrue(
            any(
                issue.code in {"plan_empty", "regular_slot_count_invalid"}
                for issue in error.exception.issues
            )
        )
        self.assertEqual("availability_requested", exam_round["status"])
        self.assertEqual([], exam_days)

    def test_other_proposal_and_fallback_reserve_person_before_confirmation(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            other_round = self._create_overlapping_round(repository)
            for member_id in range(5, 9):
                repository.update(COMMITTEE_MEMBER, member_id, {"is_active": 0})

            PlanningService(db_path).generate_proposal(other_round["id"])
            other_assignments = repository.list(EXAM_DAY_ASSIGNMENT)
            with self.assertRaises(PlanValidationError):
                PlanningService(db_path).generate_proposal(1)
            exam_round = repository.get(EXAM_ROUND, 1)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})

        self.assertTrue(any(item["assignment_role"] == "fallback" for item in other_assignments))
        self.assertEqual("availability_requested", exam_round["status"])
        self.assertEqual([], exam_days)

    def _create_overlapping_round(self, repository: ResourceRepository) -> dict[str, object]:
        committee = repository.create(COMMITTEE, {"name": "PA 2", "occupation": "FI"})
        members = []
        for person_id, side in enumerate(("employer", "employee", "school", "employer"), start=1):
            members.append(
                repository.create_membership(
                    {
                        "person_id": person_id,
                        "committee_id": committee["id"],
                        "member_status": "ordinary",
                        "committee_role": "member",
                        "representing_side": side,
                        "is_active": 1,
                    }
                )
            )
        location = repository.create(
            LOCATION,
            {
                "committee_id": committee["id"],
                "name": "Raum 2",
                "street": "Testweg 1",
                "postal_code": "00000",
                "city": "Teststadt",
                "room": "2.01",
                "is_active": 1,
            },
        )
        exam_round = repository.create(
            EXAM_ROUND,
            {
                "exam_half_year_id": 1,
                "committee_id": committee["id"],
                "name": "Winter 2026/27 PA 2",
                "availability_deadline": "2026-10-15 18:00:00",
                "created_by_member_id": members[0]["id"],
            },
        )
        for index in range(5):
            candidate = repository.create(
                CANDIDATE,
                {
                    "first_name": "Prüfling",
                    "last_name": f"Konflikt-{index}",
                    "ihk_exam_number": f"TEST-88-{index}",
                    "specialization": "system_integration",
                    "training_company": "Testbetrieb Konflikt",
                },
            )
            repository.create(
                ROUND_CANDIDATE,
                {
                    "exam_round_id": exam_round["id"],
                    "candidate_id": candidate["id"],
                    "attempt_number": 1,
                    "requires_mep": 0,
                    "is_active": 1,
                },
            )
        repository.create(
            PLANNING_SETTINGS,
            {
                "exam_round_id": exam_round["id"],
                "calendar_week_from": "2026-W47",
                "calendar_week_to": "2026-W47",
                "exams_per_day": 1,
                "max_exam_days_per_week": 5,
                "lunch_break_enabled": 1,
                "exclude_public_holidays": 0,
                "holiday_subdivision_code": None,
                "default_location_id": location["id"],
                "updated_by_member_id": members[0]["id"],
            },
        )
        for date in ("2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"):
            candidate_day = repository.create(
                CANDIDATE_EXAM_DAY,
                {"exam_round_id": exam_round["id"], "date": date, "is_active": 1},
            )
            for member in members:
                repository.create(
                    MEMBER_AVAILABILITY,
                    {
                        "exam_round_id": exam_round["id"],
                        "committee_member_id": member["id"],
                        "candidate_exam_day_id": candidate_day["id"],
                        "availability": "full_day",
                        "responded_at": "2026-01-01T00:00:00+00:00",
                    },
                )
        PlanningService(repository.db_path).request_availabilities(exam_round["id"])
        return exam_round


if __name__ == "__main__":
    unittest.main()
