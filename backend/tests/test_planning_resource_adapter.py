from __future__ import annotations

import unittest
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.persistence.database import session_scope
from backend.persistence.models import CANDIDATE, CANDIDATE_EXAM_DAY
from backend.persistence.planning_resources import SQLitePlanningResourceUnitOfWorkFactory
from backend.persistence.store import Store
from backend.planning.resources import (
    PlanningAvailabilityPropagationWrite,
    PlanningResourceService,
)
from backend.tests.helpers import TempDatabase


class PlanningResourceAdapterTests(unittest.TestCase):
    def test_visible_candidate_ids_bound_the_sqlite_list_query(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            planning = PlanningResourceService(factory)
            first = planning.create_candidate(
                {
                    "first_name": "Visible",
                    "last_name": "Candidate",
                    "ihk_exam_number": "PORT-VISIBLE-1",
                    "specialization": "system_integration",
                    "training_company": "Port-Test",
                }
            )
            planning.create_candidate(
                {
                    "first_name": "Hidden",
                    "last_name": "Candidate",
                    "ihk_exam_number": "PORT-HIDDEN-1",
                    "specialization": "system_integration",
                    "training_company": "Port-Test",
                }
            )
            conditions = []
            original_where = Store.where

            def capture_where(store, resource, *predicates, **filters):
                if resource is CANDIDATE:
                    conditions.extend(predicates)
                return original_where(store, resource, *predicates, **filters)

            scoped_service = PlanningResourceService(
                factory,
                visible=lambda *_args: frozenset({int(first.values["id"])}),
            )
            with patch.object(Store, "where", capture_where):
                visible = scoped_service.list_visible_records("candidate")

        self.assertEqual([first.values["id"]], [record.values["id"] for record in visible])
        self.assertTrue(conditions)
        self.assertTrue(
            any(
                " IN (" in str(condition.compile(compile_kwargs={"literal_binds": True}))
                for condition in conditions
            )
        )

    def test_half_year_is_created_only_as_part_of_round_command(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            planning = PlanningResourceService(factory)
            self.assertFalse(hasattr(planning, "create_half_year"))
            with factory() as unit_of_work:
                self.assertFalse(hasattr(unit_of_work, "create_half_year"))
            created_round = planning.create_round(
                {
                    "season": "winter",
                    "year": 2031,
                    "committee_id": 1,
                    "name": "Winter 2031",
                    "created_by_member_id": 1,
                }
            )
            half_years = [row for row in planning.list_half_years() if row.values["year"] == 2031]

        self.assertEqual(
            1,
            sum(row.values["season"] == "winter" for row in half_years),
        )
        self.assertEqual(half_years[0].values["id"], created_round.values["exam_half_year_id"])

    def test_concurrent_duplicate_round_writes_serialize_half_year_creation(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            planning = PlanningResourceService(factory)
            start = Barrier(2)

            def create_duplicate() -> str:
                start.wait()
                try:
                    planning.create_round(
                        {
                            "season": "winter",
                            "year": 2032,
                            "committee_id": 1,
                            "name": "Winter 2032",
                            "created_by_member_id": 1,
                        }
                    )
                except IntegrityError:
                    return "duplicate"
                return "created"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: create_duplicate(), range(2)))

            half_years = [row for row in planning.list_half_years() if row.values["year"] == 2032]

        self.assertCountEqual(["created", "duplicate"], outcomes)
        self.assertEqual(1, len(half_years))

    def test_read_unit_of_work_does_not_reserve_sqlite_writer_intent(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            with factory() as unit_of_work:
                unit_of_work.list_rounds({})
                with session_scope(db_path, begin_immediate=True):
                    pass

    def test_read_unit_of_work_pins_snapshot_across_concurrent_commit(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            planning = PlanningResourceService(factory)
            round_record = planning.create_round(
                {
                    "season": "summer",
                    "year": 2033,
                    "committee_id": 1,
                    "name": "Summer 2033",
                    "created_by_member_id": 1,
                }
            )
            half_year_id = round_record.values["exam_half_year_id"]

            with factory() as unit_of_work:
                self.assertIsNotNone(unit_of_work.get_round(round_record.values["id"]))
                with session_scope(db_path, begin_immediate=True) as writer:
                    writer.execute(
                        text("UPDATE exam_half_year SET status = 'archived' WHERE id = :id"),
                        {"id": half_year_id},
                    )
                half_year = unit_of_work.get_half_year(half_year_id)

            self.assertIsNotNone(half_year)
            assert half_year is not None
            self.assertEqual("active", half_year.values["status"])
            current_half_year = planning.get_half_year(half_year_id)
            self.assertIsNotNone(current_half_year)
            assert current_half_year is not None
            self.assertEqual("archived", current_half_year.values["status"])

    def test_sqlite_command_rolls_back_candidate_created_before_invalid_assignment(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            before = PlanningResourceService(factory).list_candidates()

            with self.assertRaisesRegex(ValueError, "Exam round not found"):
                PlanningResourceService(factory).create_candidate(
                    {
                        "first_name": "Rollback",
                        "last_name": "Candidate",
                        "ihk_exam_number": "PORT-ROLLBACK-1",
                        "specialization": "system_integration",
                        "training_company": "Port-Test",
                        "exam_round_id": 999999,
                    }
                )

            after = PlanningResourceService(factory).list_candidates()

        self.assertEqual(before, after)

    def test_sqlite_availability_source_rolls_back_when_propagation_write_fails(self) -> None:
        with TempDatabase() as db_path:
            factory = SQLitePlanningResourceUnitOfWorkFactory(db_path)
            planning = PlanningResourceService(factory)
            exam_round = planning.create_round(
                {
                    "season": "winter",
                    "year": 2035,
                    "committee_id": 1,
                    "name": "Winter 2035",
                    "created_by_member_id": 1,
                }
            )
            with session_scope(db_path) as session:
                day = Store(session).create(
                    CANDIDATE_EXAM_DAY,
                    {
                        "exam_round_id": exam_round.values["id"],
                        "date": "2035-01-10",
                        "is_active": 1,
                    },
                )

            source = {
                "exam_round_id": exam_round.values["id"],
                "committee_member_id": 1,
                "candidate_exam_day_id": day["id"],
                "availability": "pending",
                "responded_at": None,
            }
            invalid_target = PlanningAvailabilityPropagationWrite(
                existing_availability_id=None,
                exam_round_id=999999,
                committee_member_id=1,
                candidate_exam_day_id=day["id"],
                availability="pending",
                responded_at=None,
            )

            with self.assertRaises(IntegrityError):
                with factory(write=True) as unit_of_work:
                    unit_of_work.save_availability(source, (invalid_target,))

            self.assertEqual(
                (),
                planning.list_availabilities({"exam_round_id": exam_round.values["id"]}),
            )

    def test_sqlite_snapshot_is_detached_and_has_typed_sections(self) -> None:
        with TempDatabase() as db_path:
            snapshot = PlanningResourceService(
                SQLitePlanningResourceUnitOfWorkFactory(db_path)
            ).planning_snapshot(1)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertIsInstance(snapshot.exam_round.values, Mapping)
        self.assertIsInstance(snapshot.half_year.values, Mapping)
        self.assertTrue(all(isinstance(row.values, Mapping) for row in snapshot.candidates))
        self.assertFalse(hasattr(snapshot.exam_round, "model"))


if __name__ == "__main__":
    unittest.main()
