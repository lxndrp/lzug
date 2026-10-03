from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

from backend.application.repositories import ResourceRepository
from backend.composition import candidate_day_service
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.models import CANDIDATE_EXAM_DAY
from backend.planning.candidate_days import (
    CandidateDayRecord,
    CandidateDayService,
    CandidateDaySettings,
    GenerateCandidateDays,
)
from backend.tests.helpers import TempDatabase
from backend.tests.planning_support import planning_resource_service


class FakeHolidayProvider:
    def public_holidays(self, start_date: date, end_date: date, subdivision_code: str):
        return []


@dataclass(frozen=True)
class FakeCandidateDaySettings:
    calendar_week_from: str
    calendar_week_to: str
    exclude_public_holidays: int
    holiday_subdivision_code: str | None


@dataclass(frozen=True)
class FakeCandidateDayRecord:
    id: int
    round_id: int
    date: str
    is_active: int
    created_at: str
    updated_at: str


class FakeCandidateDayStore:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.settings = FakeCandidateDaySettings("2026-W23", "2026-W23", 0, None)
        self.rows: list[CandidateDayRecord] = []
        self.fail_after = fail_after

    @contextmanager
    def __call__(self) -> Iterator[FakeCandidateDayUnitOfWork]:
        staged_rows = list(self.rows)
        unit_of_work = FakeCandidateDayUnitOfWork(self, staged_rows)
        try:
            yield unit_of_work
        except BaseException:
            raise
        else:
            self.rows = staged_rows


class FakeCandidateDayUnitOfWork:
    def __init__(
        self,
        owner: FakeCandidateDayStore,
        staged_rows: list[CandidateDayRecord],
    ) -> None:
        self.owner = owner
        self.rows = staged_rows

    def planning_settings(self, round_id: int) -> CandidateDaySettings:
        del round_id
        return self.owner.settings

    def candidate_days(self, round_id: int) -> tuple[CandidateDayRecord, ...]:
        return tuple(row for row in self.rows if row.round_id == round_id)

    def create_candidate_day(self, round_id: int, day: date) -> CandidateDayRecord:
        if self.owner.fail_after is not None and len(self.rows) >= self.owner.fail_after:
            raise RuntimeError("simulated persistence failure")
        timestamp = "2026-06-01 00:00:00"
        record = FakeCandidateDayRecord(
            len(self.rows) + 1,
            round_id,
            day.isoformat(),
            1,
            timestamp,
            timestamp,
        )
        self.rows.append(record)
        return record


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

            service = candidate_day_service(db_path)
            first = service.generate(GenerateCandidateDays(1)).as_payload()
            second = service.generate(GenerateCandidateDays(1)).as_payload()
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

            result = candidate_day_service(db_path).generate(GenerateCandidateDays(1)).as_payload()

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

            result = candidate_day_service(db_path).generate(GenerateCandidateDays(1)).as_payload()

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
                candidate_day_service(db_path).generate(GenerateCandidateDays(1))

    def test_service_runs_against_a_simple_double_and_keeps_typed_results(self) -> None:
        store = FakeCandidateDayStore()
        service = CandidateDayService(store, FakeHolidayProvider())

        result = service.generate(GenerateCandidateDays(7))

        self.assertEqual(5, result.calculated_weekdays)
        self.assertEqual(5, len(result.created_days))
        self.assertEqual(5, len(store.rows))
        self.assertEqual(7, result.created_days[0].round_id)
        self.assertEqual(
            {
                "id": 1,
                "exam_round_id": 7,
                "date": "2026-06-01",
                "is_active": 1,
                "created_at": "2026-06-01 00:00:00",
                "updated_at": "2026-06-01 00:00:00",
            },
            result.as_payload()["created_days"][0],
        )

    def test_generation_rolls_back_all_created_days_when_the_port_fails(self) -> None:
        store = FakeCandidateDayStore(fail_after=2)
        service = CandidateDayService(store, FakeHolidayProvider())

        with self.assertRaisesRegex(RuntimeError, "simulated persistence failure"):
            service.generate(GenerateCandidateDays(1))

        self.assertEqual([], store.rows)

    def test_sqlite_unit_of_work_rolls_back_candidate_days_on_error(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            before = repository.list_filtered(CANDIDATE_EXAM_DAY, {"exam_round_id": 1})
            unit_of_work_factory = SQLiteCandidateDayUnitOfWorkFactory(db_path)

            with self.assertRaisesRegex(RuntimeError, "abort candidate-day command"):
                with unit_of_work_factory() as unit_of_work:
                    unit_of_work.create_candidate_day(1, date(2030, 1, 7))
                    raise RuntimeError("abort candidate-day command")

            after = repository.list_filtered(CANDIDATE_EXAM_DAY, {"exam_round_id": 1})

        self.assertEqual(before, after)

    def test_planning_service_module_has_no_infrastructure_imports(self) -> None:
        import ast
        from pathlib import Path

        source = Path(__file__).parents[1] / "src/backend/planning/candidate_days.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertFalse(
            any(
                name.startswith(
                    ("fastapi", "sqlalchemy", "backend.persistence", "backend.integrations")
                )
                for name in imported
            ),
            imported,
        )

    def _save_settings(
        self,
        repository: ResourceRepository,
        *,
        calendar_week_from: str,
        calendar_week_to: str,
        exclude_public_holidays: int,
        holiday_subdivision_code: str | None,
    ) -> None:
        planning_resource_service(repository.db_path).save_settings(
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
