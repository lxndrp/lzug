from __future__ import annotations

import unittest

from sqlalchemy.exc import IntegrityError

from backend.models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class RepositoryTests(unittest.TestCase):
    def test_candidate_list_adds_human_readable_specialization_labels(self) -> None:
        with TempDatabase() as db_path:
            candidates = ResourceRepository(db_path).candidate_list()

        self.assertEqual(12, len(candidates))
        self.assertIn("specialization_label", candidates[0])
        self.assertIn(
            "Anwendungsentwicklung",
            {candidate["specialization_label"] for candidate in candidates},
        )

    def test_create_candidate_can_attach_candidate_to_exam_round(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            created = repository.create_candidate(
                {
                    "first_name": "Prüfling",
                    "last_name": "Repository",
                    "ihk_exam_number": "TEST-2026-9001",
                    "specialization": "system_integration",
                    "training_company": "Testbetrieb Repository",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": 1,
                }
            )
            summary = repository.round_summary(1)

        self.assertEqual("Prüfling", created["first_name"])
        self.assertIsNotNone(summary)
        self.assertEqual(13, summary["counts"]["candidates"])
        self.assertEqual(5, summary["counts"]["mep_count"])
        self.assertEqual(18, summary["counts"]["required_exam_slots"])

    def test_delete_candidate_removes_round_link_first(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self.assertTrue(repository.delete_candidate(1))
            summary = repository.round_summary(1)
            candidate = repository.get(CANDIDATE, 1)

        self.assertIsNone(candidate)
        self.assertEqual(11, summary["counts"]["candidates"])

    def test_update_candidate_updates_round_data_atomically(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            updated = repository.update_candidate(
                1,
                {
                    "last_name": "Neu",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": 1,
                },
            )
            round_candidate = repository.list_filtered(
                ROUND_CANDIDATE,
                {"candidate_id": 1, "exam_round_id": 1},
            )[0]

            with self.assertRaises(ValueError):
                repository.update_candidate(
                    1,
                    {
                        "last_name": "Nicht gespeichert",
                        "exam_round_id": 999,
                        "attempt_number": 2,
                    },
                )
            after_failed_update = repository.get(CANDIDATE, 1)

        self.assertIsNotNone(updated)
        self.assertEqual("Neu", updated["last_name"])
        self.assertEqual(3, round_candidate["attempt_number"])
        self.assertEqual(1, round_candidate["requires_mep"])
        self.assertEqual("Neu", after_failed_update["last_name"])

    def test_candidate_committee_change_preserves_history_and_deactivates_old_round(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            committee = repository.create(
                COMMITTEE,
                {
                    "name": "Prüfungsausschuss Teststadt 2",
                    "occupation": "Fachinformatiker/in",
                },
            )
            member = repository.create(
                COMMITTEE_MEMBER,
                {
                    "person_id": 1,
                    "committee_id": committee["id"],
                    "member_status": "ordinary",
                    "committee_role": "chair",
                    "representing_side": "employer",
                    "is_active": 1,
                },
            )
            target_round = repository.create(
                EXAM_ROUND,
                {
                    "exam_half_year_id": 1,
                    "committee_id": committee["id"],
                    "name": "Winter 2026/27 · Prüfungsausschuss Teststadt 2",
                    "created_by_member_id": member["id"],
                },
            )

            with self.assertRaisesRegex(ValueError, "reason is required"):
                repository.update_candidate(
                    1,
                    {"exam_round_id": target_round["id"], "attempt_number": 2},
                )

            repository.update_candidate(
                1,
                {
                    "exam_round_id": target_round["id"],
                    "attempt_number": 2,
                    "requires_mep": 1,
                    "assignment_change_reason": "Wechsel in den zuständigen Ausschuss",
                },
            )
            history = repository.candidate_committee_assignments(1)
            old_round_candidate = repository.list_filtered(
                ROUND_CANDIDATE,
                {"candidate_id": 1, "exam_round_id": 1},
            )[0]
            new_round_candidate = repository.list_filtered(
                ROUND_CANDIDATE,
                {"candidate_id": 1, "exam_round_id": target_round["id"]},
            )[0]
            old_summary = repository.round_summary(1)
            new_summary = repository.round_summary(target_round["id"])

        self.assertEqual(2, len(history))
        historic = next(item for item in history if item["exam_round_id"] == 1)
        active = next(item for item in history if item["exam_round_id"] == target_round["id"])
        self.assertIsNotNone(historic["ended_at"])
        self.assertEqual("Wechsel in den zuständigen Ausschuss", historic["change_reason"])
        self.assertIsNone(active["ended_at"])
        self.assertEqual(0, old_round_candidate["is_active"])
        self.assertEqual(1, new_round_candidate["is_active"])
        self.assertEqual(11, old_summary["counts"]["candidates"])
        self.assertEqual(1, new_summary["counts"]["candidates"])

    def test_update_exam_round_updates_metadata_and_timestamp(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            before = repository.get(EXAM_ROUND, 1)
            updated = repository.update_exam_round(
                1,
                {
                    "name": "Sommer 2027",
                    "availability_deadline": "2027-04-15 18:00:00",
                    "availability_reminder_at": "2027-04-08 09:00:00",
                },
            )

        self.assertIsNotNone(updated)
        self.assertEqual("Sommer 2027", updated["name"])
        self.assertEqual("2027-04-15 18:00:00", updated["availability_deadline"])
        self.assertNotEqual(before["updated_at"], updated["updated_at"])

    def test_update_exam_round_rejects_invalid_metadata(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            with self.assertRaisesRegex(ValueError, "name is required"):
                repository.update_exam_round(1, {"name": "  "})
            with self.assertRaisesRegex(ValueError, "before the deadline"):
                repository.update_exam_round(
                    1,
                    {
                        "availability_deadline": "2027-04-08 09:00:00",
                        "availability_reminder_at": "2027-04-15 18:00:00",
                    },
                )

    def test_exam_round_requires_a_unique_committee_half_year_pair(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            half_year = repository.create(
                EXAM_HALF_YEAR,
                {"season": "summer", "year": 2027, "status": "draft"},
            )
            created = repository.create(
                EXAM_ROUND,
                {
                    "exam_half_year_id": half_year["id"],
                    "committee_id": 1,
                    "name": "Sommer 2027 · Prüfungsausschuss Teststadt 1",
                    "created_by_member_id": 1,
                },
            )
            with self.assertRaisesRegex(ValueError, "Creating member"):
                invalid_half_year = repository.create(
                    EXAM_HALF_YEAR,
                    {"season": "winter", "year": 2027, "status": "draft"},
                )
                repository.create(
                    EXAM_ROUND,
                    {
                        "exam_half_year_id": invalid_half_year["id"],
                        "committee_id": 1,
                        "name": "Ungültige Runde",
                        "created_by_member_id": 999,
                    },
                )
            with self.assertRaises(IntegrityError):
                repository.create(
                    EXAM_ROUND,
                    {
                        "exam_half_year_id": half_year["id"],
                        "committee_id": 1,
                        "name": "Doppelte Runde",
                        "created_by_member_id": 1,
                    },
                )
            summary = repository.round_summary(created["id"])

        self.assertEqual(half_year["id"], created["exam_half_year_id"])
        self.assertEqual(half_year["id"], summary["round"]["exam_half_year"]["id"])

    def test_planning_settings_upsert_enforces_chair_for_week_limit(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            updated = repository.save_planning_settings(
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W47",
                    "calendar_week_to": "2026-W50",
                    "exams_per_day": 5,
                    "max_exam_days_per_week": 4,
                    "lunch_break_enabled": 0,
                    "exclude_public_holidays": 1,
                    "holiday_subdivision_code": "DE-NW",
                    "default_location_id": 2,
                    "updated_by_member_id": 1,
                }
            )

            with self.assertRaises(ValueError):
                repository.save_planning_settings(
                    {
                        "exam_round_id": 1,
                        "calendar_week_from": "2026-W47",
                        "calendar_week_to": "2026-W50",
                        "exams_per_day": 5,
                        "max_exam_days_per_week": 5,
                        "lunch_break_enabled": 0,
                        "exclude_public_holidays": 1,
                        "holiday_subdivision_code": "DE-NW",
                        "default_location_id": 2,
                        "updated_by_member_id": 2,
                    }
                )

            settings = repository.list_filtered(PLANNING_SETTINGS, {"exam_round_id": 1})

        self.assertEqual(1, updated["id"])
        self.assertEqual(4, updated["max_exam_days_per_week"])
        self.assertEqual(1, updated["exclude_public_holidays"])
        self.assertEqual("DE-NW", updated["holiday_subdivision_code"])
        self.assertEqual(1, len(settings))

    def test_planning_settings_require_valid_state_for_holiday_exclusion(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            payload = {
                "exam_round_id": 1,
                "calendar_week_from": "2026-W47",
                "calendar_week_to": "2026-W50",
                "exams_per_day": 5,
                "max_exam_days_per_week": 3,
                "lunch_break_enabled": 1,
                "exclude_public_holidays": 1,
                "holiday_subdivision_code": None,
                "default_location_id": 1,
                "updated_by_member_id": 1,
            }

            with self.assertRaisesRegex(ValueError, "Federal state is required"):
                repository.save_planning_settings(payload)

            payload["holiday_subdivision_code"] = "DE-XX"
            with self.assertRaisesRegex(ValueError, "Unknown German federal state"):
                repository.save_planning_settings(payload)

    def test_availability_upsert_manages_response_timestamp(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            answered = repository.save_member_availability(
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": 1,
                    "availability": "morning",
                }
            )
            pending = repository.update_member_availability(
                answered["id"],
                {"availability": "pending"},
            )
            rows = repository.list_filtered(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": 1,
                },
            )

        self.assertIsNotNone(answered["responded_at"])
        self.assertIsNotNone(pending)
        self.assertIsNone(pending["responded_at"])
        self.assertEqual(1, len(rows))

    def test_availability_is_shared_by_person_only_within_the_same_half_year(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            committee = repository.create(COMMITTEE, {"name": "PA 2", "occupation": "FI"})
            membership = repository.create_membership(
                {
                    "person_id": 1,
                    "committee_id": committee["id"],
                    "member_status": "ordinary",
                    "committee_role": "member",
                    "representing_side": "employer",
                    "is_active": 1,
                }
            )
            shared_round = repository.create(
                EXAM_ROUND,
                {
                    "exam_half_year_id": 1,
                    "committee_id": committee["id"],
                    "name": "Winter PA 2",
                    "created_by_member_id": membership["id"],
                },
            )
            shared_day = repository.create(
                CANDIDATE_EXAM_DAY,
                {"exam_round_id": shared_round["id"], "date": "2026-11-16", "is_active": 1},
            )
            next_half_year = repository.create(
                EXAM_HALF_YEAR,
                {"season": "summer", "year": 2027, "status": "active"},
            )
            separate_round = repository.create(
                EXAM_ROUND,
                {
                    "exam_half_year_id": next_half_year["id"],
                    "committee_id": committee["id"],
                    "name": "Sommer PA 2",
                    "created_by_member_id": membership["id"],
                },
            )
            separate_day = repository.create(
                CANDIDATE_EXAM_DAY,
                {"exam_round_id": separate_round["id"], "date": "2026-11-16", "is_active": 1},
            )

            repository.save_member_availability(
                {
                    "exam_round_id": 1,
                    "committee_member_id": 1,
                    "candidate_exam_day_id": 1,
                    "availability": "morning",
                }
            )
            shared = repository.list_filtered(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": shared_round["id"],
                    "committee_member_id": membership["id"],
                    "candidate_exam_day_id": shared_day["id"],
                },
            )
            separate = repository.list_filtered(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": separate_round["id"],
                    "committee_member_id": membership["id"],
                    "candidate_exam_day_id": separate_day["id"],
                },
            )

        self.assertEqual("morning", shared[0]["availability"])
        self.assertEqual([], separate)


if __name__ == "__main__":
    unittest.main()
