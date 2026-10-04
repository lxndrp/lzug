from __future__ import annotations

import unittest
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType

from backend.planning.resources import (
    PlanningAvailabilityPropagationContext,
    PlanningAvailabilityPropagationFact,
    PlanningAvailabilityReferences,
    PlanningCandidateAssignmentContext,
    PlanningRecordValue,
    PlanningResourceService,
    PlanningRoomFacts,
    PlanningRoundCreationContext,
    PlanningSettingsReferences,
    PlanningValue,
)


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

    def test_round_candidate_delete_is_authorized_and_runs_in_write_uow(self) -> None:
        query_snapshot = object()
        events: list[str] = []

        class FakeUnitOfWork:
            def authorization_queries(self):
                events.append("queries")
                return query_snapshot

            def delete_round_candidate(self, round_candidate_id):
                events.append(f"delete:{round_candidate_id}")
                return True

            def round_candidate_is_in_use(self, round_candidate_id):
                events.append(f"in_use:{round_candidate_id}")
                return False

        @contextmanager
        def unit_of_work_factory(*, write=False):
            events.append(f"begin:{write}")
            yield FakeUnitOfWork()
            events.append("commit")

        def authorize(queries, resource, entity_id, payload):
            self.assertIs(query_snapshot, queries)
            self.assertEqual("round_candidate", resource)
            self.assertEqual(12, entity_id)
            self.assertEqual({}, payload)
            events.append("authorize")
            return payload

        self.assertTrue(
            PlanningResourceService(unit_of_work_factory, authorize).delete_round_candidate(12)
        )
        self.assertEqual(
            ["begin:True", "queries", "authorize", "in_use:12", "delete:12", "commit"],
            events,
        )

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
            def list_rounds(self, filters, visible_ids=None):
                self.assert_active()
                events.append(f"planning-read:{sorted(visible_ids or ())}")
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
            return iter((frozenset({12}),))

        result = PlanningResourceService(
            unit_of_work_factory, visible=visible
        ).list_visible_records("exam_round")

        self.assertEqual([record], list(result))
        self.assertEqual(
            [
                "begin:False",
                "authorization-queries",
                "visibility-read",
                "planning-read:[12]",
                "end",
            ],
            events,
        )

    def test_visible_item_is_authorized_before_loading_its_planning_record(self) -> None:
        events: list[str] = []
        active = False

        class FakeUnitOfWork:
            def authorization_queries(self):
                if not active:
                    raise AssertionError("Visibility escaped its unit of work")
                events.append("queries")
                return object()

            def get_candidate(self, candidate_id):
                events.append(f"load:{candidate_id}")
                raise AssertionError("Invisible Planning record was loaded")

        @contextmanager
        def unit_of_work_factory(*, write=False):
            nonlocal active
            active = True
            try:
                yield FakeUnitOfWork()
            finally:
                active = False

        def visible(_queries, resource, entity_id, filters):
            self.assertTrue(active)
            self.assertEqual(("candidate", 23, {}), (resource, entity_id, filters))
            events.append("visibility")
            return False

        record = PlanningResourceService(unit_of_work_factory, visible=visible).get_visible_record(
            "candidate", 23
        )

        self.assertIsNone(record)
        self.assertEqual(["queries", "visibility"], events)

    def test_round_summary_visibility_precedes_summary_read_in_one_unit_of_work(self) -> None:
        calls: list[str] = []
        summary = object()

        class FakeUnitOfWork:
            def get_round(self, round_id):
                calls.append(f"round:{round_id}")
                if round_id == 9:
                    return PlanningRecordValue({"id": 9, "committee_id": 4})
                return None

            def round_summary(self, round_id):
                calls.append(f"summary:{round_id}")
                return summary

        @contextmanager
        def unit_of_work_factory(*, write=False):
            calls.append("begin")
            try:
                yield FakeUnitOfWork()
            finally:
                calls.append("end")

        service = PlanningResourceService(unit_of_work_factory)

        self.assertIsNone(service.round_summary(9, frozenset({8})))
        self.assertIsNone(service.round_summary(999, frozenset({8})))
        self.assertIs(summary, service.round_summary(9, frozenset({4})))

        self.assertEqual(
            [
                "begin",
                "round:9",
                "end",
                "begin",
                "round:999",
                "end",
                "begin",
                "round:9",
                "summary:9",
                "end",
            ],
            calls,
        )

    def test_round_reassignment_policy_runs_before_the_port_write(self) -> None:
        existing = PlanningRecordValue(
            {
                "id": 4,
                "exam_half_year_id": 2,
                "committee_id": 3,
                "name": "Winter",
                "status": "draft",
            }
        )
        writes: list[dict[str, PlanningValue]] = []

        class FakeUnitOfWork:
            def get_round(self, round_id):
                return existing

            def update_round(self, round_id, values):
                writes.append(dict(values))
                return existing

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        service = PlanningResourceService(unit_of_work_factory)
        with self.assertRaisesRegex(ValueError, "cannot be reassigned"):
            service.update_round(4, {"committee_id": 5})

        self.assertEqual([], writes)

    def test_round_reference_policy_runs_with_detached_facts_before_write(self) -> None:
        writes: list[dict[str, PlanningValue]] = []

        class FakeUnitOfWork:
            def prepare_round_creation(self, values):
                return PlanningRoundCreationContext(9, True, True, True, True, 2)

            def create_round(self, plan):
                writes.append(plan)
                return PlanningRecordValue(
                    {**plan.values, "exam_half_year_id": plan.exam_half_year_id}
                )

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        with self.assertRaisesRegex(ValueError, "does not belong"):
            PlanningResourceService(unit_of_work_factory).create_round(
                {
                    "season": "winter",
                    "year": 2034,
                    "committee_id": 3,
                    "created_by_member_id": 4,
                    "name": "Winter 2034",
                }
            )

        self.assertEqual([], writes)

    def test_round_committee_admission_policy_runs_before_the_port_write(self) -> None:
        cases = (
            (
                PlanningRoundCreationContext(None, False, False, False, False, None),
                "Committee not found",
            ),
            (PlanningRoundCreationContext(None, False, True, False, True, 3), "not ready"),
            (PlanningRoundCreationContext(None, False, True, True, False, 3), "not ready"),
        )

        class FakeUnitOfWork:
            def __init__(self, round_context, created_rounds):
                self.round_context = round_context
                self.created_rounds = created_rounds

            def prepare_round_creation(self, values):
                return self.round_context

            def create_round(self, plan):
                self.created_rounds.append(plan)
                return PlanningRecordValue(
                    {**plan.values, "exam_half_year_id": plan.exam_half_year_id}
                )

        class FakeUnitOfWorkFactory:
            def __init__(self, round_context, created_rounds):
                self.round_context = round_context
                self.created_rounds = created_rounds

            @contextmanager
            def __call__(self, *, write=False):
                yield FakeUnitOfWork(self.round_context, self.created_rounds)

        for context, message in cases:
            with self.subTest(message=message):
                writes: list[object] = []
                unit_of_work_factory = FakeUnitOfWorkFactory(context, writes)

                with self.assertRaisesRegex(ValueError, message):
                    PlanningResourceService(unit_of_work_factory).create_round(
                        {
                            "season": "winter",
                            "year": 2034,
                            "committee_id": 3,
                            "created_by_member_id": 4,
                            "name": "Winter 2034",
                        }
                    )

                self.assertEqual([], writes)

    def test_round_creation_half_year_decision_runs_with_plain_port(self) -> None:
        plans = []
        contexts = [
            PlanningRoundCreationContext(None, False, True, True, True, 3),
            PlanningRoundCreationContext(12, True, True, True, True, 3),
        ]

        class FakeUnitOfWork:
            def prepare_round_creation(self, values):
                return contexts.pop(0)

            def create_round(self, plan):
                plans.append(plan)
                return PlanningRecordValue({**plan.values, "exam_half_year_id": 11})

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        service = PlanningResourceService(unit_of_work_factory)
        values = {
            "season": "winter",
            "year": 2036,
            "committee_id": 3,
            "created_by_member_id": 4,
            "name": "Winter 2036",
        }
        service.create_round(values)
        service.create_round(values)

        self.assertEqual(2, len(plans))
        self.assertTrue(plans[0].create_half_year)
        self.assertIsNone(plans[0].exam_half_year_id)
        self.assertEqual(("winter", 2036), (plans[0].season, plans[0].year))
        self.assertFalse(plans[1].create_half_year)
        self.assertEqual(12, plans[1].exam_half_year_id)

    def test_settings_domain_validation_runs_with_plain_port(self) -> None:
        class FakeUnitOfWork:
            def settings_references(self, round_id, updater_member_id, room_id):
                raise AssertionError("Pure subdivision validation must run first")

            def save_settings(self, values):
                raise AssertionError("Invalid settings must not be persisted")

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        service = PlanningResourceService(unit_of_work_factory)
        with self.assertRaisesRegex(ValueError, "Unknown German federal state"):
            service.save_settings(
                {
                    "exam_round_id": 1,
                    "updated_by_member_id": 2,
                    "exclude_public_holidays": 1,
                    "holiday_subdivision_code": "DE-XX",
                }
            )

    def test_room_suitability_is_decided_by_planning(self) -> None:
        references = PlanningSettingsReferences(
            round_committee_id=3,
            updater_committee_id=3,
            room=PlanningRoomFacts(
                room_active=False,
                venue_active=True,
                venue_scope="global",
                venue_committee_id=None,
                coordinate_status="confirmed",
                coordinates_required=True,
            ),
        )

        class FakeUnitOfWork:
            def settings_references(self, round_id, updater_member_id, room_id):
                return references

            def save_settings(self, values):
                raise AssertionError("An inactive room must not be persisted")

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        with self.assertRaisesRegex(ValueError, "Default room is not active"):
            PlanningResourceService(unit_of_work_factory).save_settings(
                {
                    "exam_round_id": 1,
                    "updated_by_member_id": 2,
                    "default_room_id": 8,
                }
            )

    def test_availability_normalization_runs_before_the_port_write(self) -> None:
        saved: list[dict[str, PlanningValue]] = []

        class FakeUnitOfWork:
            def availability_references(self, round_id, member_id, day_id):
                return PlanningAvailabilityReferences(3, 3, True, 1)

            def availability_propagation_context(self, round_id, member_id, day_id):
                return PlanningAvailabilityPropagationContext(4, 40, "2034-01-01", 8, ())

            def save_availability(self, values, propagation):
                saved.append(dict(values))
                return PlanningRecordValue(values)

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        PlanningResourceService(unit_of_work_factory).save_availability(
            {
                "exam_round_id": 1,
                "committee_member_id": 4,
                "candidate_exam_day_id": 7,
                "availability": "pending",
            }
        )

        self.assertEqual(None, saved[0]["responded_at"])

    def test_availability_propagation_policy_selects_targets_in_the_service(self) -> None:
        captured: list[tuple[dict[str, PlanningValue], tuple[object, ...]]] = []
        context = PlanningAvailabilityPropagationContext(
            source_member_id=1,
            source_person_id=10,
            source_date="2034-01-01",
            source_half_year_id=7,
            candidates=(
                PlanningAvailabilityPropagationFact(2, 10, 20, 102, "2034-01-01", 202, 20, 7, 55),
                PlanningAvailabilityPropagationFact(3, 10, 30, 103, "2034-01-01", 203, 99, 7, None),
                PlanningAvailabilityPropagationFact(4, 10, 40, 104, "2034-01-01", 204, 40, 8, None),
                PlanningAvailabilityPropagationFact(5, 11, 50, 105, "2034-01-01", 205, 50, 7, None),
                PlanningAvailabilityPropagationFact(1, 10, 10, 106, "2034-01-01", 206, 10, 7, None),
                PlanningAvailabilityPropagationFact(6, 10, 60, 107, "2034-01-02", 207, 60, 7, None),
            ),
        )

        class FakeUnitOfWork:
            def availability_references(self, round_id, member_id, day_id):
                return PlanningAvailabilityReferences(10, 10, True, round_id)

            def availability_propagation_context(self, round_id, member_id, day_id):
                self.assert_source((round_id, member_id, day_id))
                return context

            @staticmethod
            def assert_source(actual):
                if actual != (4, 1, 8):
                    raise AssertionError(f"unexpected source lookup: {actual}")

            def save_availability(self, values, propagation):
                captured.append((dict(values), propagation))
                return PlanningRecordValue(values)

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        PlanningResourceService(unit_of_work_factory).save_availability(
            {
                "exam_round_id": 4,
                "committee_member_id": 1,
                "candidate_exam_day_id": 8,
                "availability": "pending",
            }
        )

        values, propagation = captured[0]
        self.assertEqual(None, values["responded_at"])
        self.assertEqual(1, len(propagation))
        write = propagation[0]
        self.assertEqual(55, write.existing_availability_id)
        self.assertEqual(202, write.exam_round_id)
        self.assertEqual(2, write.committee_member_id)
        self.assertEqual(102, write.candidate_exam_day_id)
        self.assertEqual("pending", write.availability)
        self.assertIsNone(write.responded_at)

    def test_candidate_reassignment_reason_is_enforced_by_planning(self) -> None:
        writes: list[dict[str, PlanningValue]] = []

        class FakeUnitOfWork:
            def candidate_assignment_context(self, candidate_id, round_id):
                return PlanningCandidateAssignmentContext(True, True, 2, False)

            def assign_candidate_to_round(self, values, plan):
                writes.append(dict(values))
                return PlanningRecordValue(values)

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        with self.assertRaisesRegex(ValueError, "reason is required"):
            PlanningResourceService(unit_of_work_factory).assign_candidate_to_round(
                {"candidate_id": 1, "exam_round_id": 3}
            )

        self.assertEqual([], writes)

    def test_candidate_assignment_policy_passes_an_explicit_persistence_plan(self) -> None:
        captured: list[object] = []

        class FakeUnitOfWork:
            def candidate_assignment_context(self, candidate_id, round_id):
                return PlanningCandidateAssignmentContext(
                    True,
                    True,
                    2,
                    True,
                    exam_half_year_id=8,
                    active_assignment_id=11,
                    active_round_candidate_id=12,
                    target_round_candidate_id=13,
                )

            def assign_candidate_to_round(self, values, plan):
                captured.append(plan)
                return PlanningRecordValue(values)

        @contextmanager
        def unit_of_work_factory(*, write=False):
            yield FakeUnitOfWork()

        PlanningResourceService(unit_of_work_factory).assign_candidate_to_round(
            {
                "candidate_id": 5,
                "exam_round_id": 3,
                "assignment_change_reason": "committee transfer",
            }
        )

        plan = captured[0]
        self.assertEqual(11, plan.end_assignment_id)
        self.assertEqual(12, plan.deactivate_round_candidate_id)
        self.assertEqual(13, plan.target_round_candidate_id)
        self.assertFalse(plan.create_round_candidate)
        self.assertTrue(plan.create_active_assignment)
        self.assertEqual("committee transfer", plan.change_reason)


if __name__ == "__main__":
    unittest.main()
