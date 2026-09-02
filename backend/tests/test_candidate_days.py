from __future__ import annotations

import unittest

from backend.candidate_days import CandidateDayService
from backend.models import CANDIDATE_EXAM_DAY
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class CandidateDayServiceTests(unittest.TestCase):
    def test_generation_excludes_state_holidays_and_is_repeatable(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self._save_settings(
                repository,
                calendar_week_from="2026-W23",
                calendar_week_to="2026-W23",
                exclude_public_holidays=1,
                holiday_subdivision_code="DE-NW",
            )

            first = CandidateDayService(db_path).generate(1)
            second = CandidateDayService(db_path).generate(1)
            rows = repository.list_filtered(CANDIDATE_EXAM_DAY, {"exam_round_id": 1})

        self.assertEqual(4, first["counts"]["created"])
        self.assertEqual(
            [{"date": "2026-06-04", "name": "Fronleichnam"}],
            first["excluded_holidays"],
        )
        self.assertEqual(0, second["counts"]["created"])
        self.assertEqual(4, second["counts"]["existing"])
        self.assertEqual(9, len(rows))

    def test_generation_includes_holidays_when_exclusion_is_disabled(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self._save_settings(
                repository,
                calendar_week_from="2026-W23",
                calendar_week_to="2026-W23",
                exclude_public_holidays=0,
                holiday_subdivision_code=None,
            )

            result = CandidateDayService(db_path).generate(1)

        self.assertEqual(5, result["counts"]["created"])
        self.assertEqual([], result["excluded_holidays"])
        self.assertIn("2026-06-04", [row["date"] for row in result["created_days"]])

    def test_generation_preserves_a_manually_created_holiday(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self._save_settings(
                repository,
                calendar_week_from="2026-W23",
                calendar_week_to="2026-W23",
                exclude_public_holidays=1,
                holiday_subdivision_code="DE-NW",
            )
            repository.create(
                CANDIDATE_EXAM_DAY,
                {"exam_round_id": 1, "date": "2026-06-04", "is_active": 1},
            )

            result = CandidateDayService(db_path).generate(1)

        self.assertEqual(4, result["counts"]["created"])
        self.assertEqual(1, result["counts"]["existing"])
        self.assertEqual([], result["excluded_holidays"])
        self.assertIn("2026-06-04", result["skipped_existing"])

    def test_generation_rejects_invalid_calendar_week(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self._save_settings(
                repository,
                calendar_week_from="2026-W54",
                calendar_week_to="2026-W54",
                exclude_public_holidays=0,
                holiday_subdivision_code=None,
            )

            with self.assertRaisesRegex(ValueError, "Calendar week is invalid"):
                CandidateDayService(db_path).generate(1)

    def _save_settings(
        self,
        repository: ResourceRepository,
        *,
        calendar_week_from: str,
        calendar_week_to: str,
        exclude_public_holidays: int,
        holiday_subdivision_code: str | None,
    ) -> None:
        repository.save_planning_settings(
            {
                "exam_round_id": 1,
                "calendar_week_from": calendar_week_from,
                "calendar_week_to": calendar_week_to,
                "exams_per_day": 6,
                "max_exam_days_per_week": 3,
                "lunch_break_enabled": 1,
                "exclude_public_holidays": exclude_public_holidays,
                "holiday_subdivision_code": holiday_subdivision_code,
                "default_room_id": 1,
                "updated_by_member_id": 1,
            }
        )


if __name__ == "__main__":
    unittest.main()
