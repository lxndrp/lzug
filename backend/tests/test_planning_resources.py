from __future__ import annotations

import unittest
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType

from backend.planning.resources import PlanningResourceService, PlanningValue


class PlanningResourcePortTests(unittest.TestCase):
    def test_service_uses_a_plain_test_double_and_returns_typed_values(self) -> None:
        @dataclass(frozen=True)
        class FakeRecord:
            values: Mapping[str, PlanningValue]

            def __post_init__(self):
                object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

            def as_payload(self):
                return dict(self.values)

        record = FakeRecord(
            {"id": 4, "first_name": "Ada", "specialization": "application_development"}
        )
        calls: list[str] = []

        class FakeUnitOfWork:
            def list_candidates(self, filters):
                calls.append(f"list:{dict(filters)}")
                return (record,)

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        result = PlanningResourceService(unit_of_work_factory).list_candidates({"is_active": 1})

        self.assertEqual(4, result[0].values["id"])
        self.assertEqual("Anwendungsentwicklung", result[0].values["specialization_label"])
        self.assertEqual(["list:{'is_active': 1}"], calls)
        self.assertEqual(
            "Ada",
            result[0].as_payload()["first_name"],
        )
        with self.assertRaises(TypeError):
            result[0].values["id"] = 5

    def test_authorization_runs_against_the_active_write_unit_of_work(self) -> None:
        query_snapshot = object()
        events: list[str] = []

        class FakeUnitOfWork:
            def authorization_queries(self):
                events.append("queries")
                return query_snapshot

            def create_candidate(self, values):
                events.append(f"write:{values['first_name']}")
                return object()

        @contextmanager
        def unit_of_work_factory(*, write=False):
            events.append(f"begin:{write}")
            yield FakeUnitOfWork()
            events.append("commit")

        def authorize(queries, resource, entity_id, payload):
            self.assertIs(query_snapshot, queries)
            self.assertEqual("candidate", resource)
            self.assertIsNone(entity_id)
            events.append("authorize")
            return {**payload, "first_name": "Authorized"}

        PlanningResourceService(unit_of_work_factory, authorize).create_candidate(
            {"first_name": "Untrusted"}
        )

        self.assertEqual(
            ["begin:True", "queries", "authorize", "write:Authorized", "commit"],
            events,
        )

    def test_authorization_failure_prevents_planning_write(self) -> None:
        events: list[str] = []

        class FakeUnitOfWork:
            def authorization_queries(self):
                events.append("queries")
                return object()

            def delete_candidate(self, candidate_id):
                events.append("write")
                return True

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        def deny(*args):
            raise PermissionError("forbidden")

        with self.assertRaisesRegex(PermissionError, "forbidden"):
            PlanningResourceService(unit_of_work_factory, deny).delete_candidate(7)

        self.assertEqual(["queries"], events)

    def test_visible_read_uses_one_unit_of_work_for_record_and_visibility(self) -> None:
        class PlanningRecordStub:
            def __init__(self, values):
                self.values = MappingProxyType(dict(values))

            def as_payload(self):
                return dict(self.values)

        record = PlanningRecordStub({"id": 12, "name": "Sommer 2027"})
        query_snapshot = object()
        events: list[str] = []
        active = False

        class FakeUnitOfWork:
            def list_rounds(self, filters):
                self.assert_active()
                events.append("planning-read")
                return (record,)

            def authorization_queries(self):
                self.assert_active()
                events.append("authorization-queries")
                return query_snapshot

            @staticmethod
            def assert_active():
                if not active:
                    raise AssertionError("Planning read escaped its unit of work")

        @contextmanager
        def unit_of_work_factory(*, write=False):
            nonlocal active
            events.append(f"begin:{write}")
            active = True
            try:
                yield FakeUnitOfWork()
            finally:
                active = False
                events.append("end")

        def visible(queries, resource, entity_id, filters):
            self.assertTrue(active)
            self.assertIs(query_snapshot, queries)
            self.assertEqual("exam_round", resource)
            self.assertIsNone(entity_id)
            events.append("visibility-read")
            return frozenset({12})

        result = PlanningResourceService(
            unit_of_work_factory, visible=visible
        ).list_visible_records("exam_round")

        self.assertEqual([record], list(result))
        self.assertEqual(
            ["begin:False", "planning-read", "authorization-queries", "visibility-read", "end"],
            events,
        )


if __name__ == "__main__":
    unittest.main()
