"""Verify the service owns venue policy on a SQLite-free fake unit of work."""

from __future__ import annotations

import subprocess
import sys
import unittest


class PlanningVenueServiceIsolationTests(unittest.TestCase):
    def test_fake_uow_runs_service_policy_without_loading_sqlalchemy(self) -> None:
        script = """
import sys
from backend.planning.exam_venues import ExamVenueService
from backend.planning_ports import ExamVenueError, VenueCommandFacts, VenueCommandResult

class FakeVenueUnitOfWork:
    plan_calls = 0
    def execute(self, command, planner):
        self.plan_calls += 1
        facts = VenueCommandFacts()
        if command.kind.name.endswith("CONTACT"):
            facts = VenueCommandFacts(venue_id=4, room_venue_ids={3: 99})
        elif command.kind.name == "CREATE_VENUE":
            facts = VenueCommandFacts(
                duplicate_candidates=(
                    {
                        "scope": "global",
                        "committee_id": None,
                        "normalized_name": "nord",
                        "street": "",
                        "postal_code": "",
                        "city": "",
                        "country": "Deutschland",
                    },
                )
            )
        elif command.kind.name == "UPDATE_VENUE":
            current, _ = planner.policy.venue_values(
                {
                    "scope": "committee",
                    "committee_id": 9,
                    "name": "Alt",
                    "is_accessible": None,
                    "accessibility_status": "needs_clarification",
                    "is_active": False,
                }
            )
            facts = VenueCommandFacts(current=current, has_future_confirmed_assignments=True)
        elif command.kind.name == "UPDATE_ROOM":
            current, _ = planner.policy.room_values({"name": "A-101"})
            facts = VenueCommandFacts(current=current, has_future_confirmed_assignments=True)
        plan = planner.plan(command, facts)
        return VenueCommandResult(dict(plan.values))
    def query(self, query, planner):
        raise AssertionError("unexpected query")

uow = FakeVenueUnitOfWork()
service = ExamVenueService(uow)
try:
    service.create_venue(
        {"scope": "global", "committee_id": 9, "name": "Ungültig"},
        actor_member_id=9,
    )
except ExamVenueError as error:
    assert "scope and committee" in str(error)
else:
    raise AssertionError("invalid venue scope was accepted")
try:
    service.create_room(4, {"name": "A-101", "capacity": 0}, actor_member_id=9)
except ExamVenueError as error:
    assert "capacity must be positive" in str(error)
else:
    raise AssertionError("invalid room capacity was accepted")
try:
    service.create_contact(4, {"label": "Hausdienst"}, actor_member_id=9)
except ExamVenueError as error:
    assert "needs phone, email" in str(error)
else:
    raise AssertionError("contact without contact information was accepted")
try:
    service.create_contact(
        4, {"label": "Hausdienst", "email": "haus@example.test", "room_ids": [3]},
        actor_member_id=9,
    )
except ExamVenueError as error:
    assert "own venue" in str(error)
else:
    raise AssertionError("cross-venue contact association was accepted")
try:
    service.create_venue(
        {
            "scope": "committee", "committee_id": 9, "name": "Nord",
            "accessibility_status": "needs_clarification", "is_accessible": None,
            "duplicates_reviewed": True,
        },
        actor_member_id=9,
    )
except ExamVenueError as error:
    assert "needs a reason" in str(error)
else:
    raise AssertionError("unreasoned global duplicate was accepted")
try:
    service.update_venue(7, {"expected_revision": 1, "name": "Neu"}, actor_member_id=9)
except ExamVenueError as error:
    assert "Future confirmed appointments" in str(error)
else:
    raise AssertionError("unconfirmed venue impact was accepted")
try:
    service.update_room(3, {"expected_revision": 1, "name": "B-201"}, actor_member_id=9)
except ExamVenueError as error:
    assert "Future confirmed appointments" in str(error)
else:
    raise AssertionError("unconfirmed room impact was accepted")
assert uow.plan_calls == 7
assert "sqlalchemy" not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
