"""Verify the service owns venue policy on a SQLite-free fake unit of work."""

from __future__ import annotations

import subprocess
import sys
import unittest
from textwrap import dedent


class PlanningVenueServiceIsolationTests(unittest.TestCase):
    def test_fake_uow_runs_service_policy_without_loading_sqlalchemy(self) -> None:
        script = dedent("""
import sys
from contextlib import contextmanager
from backend.planning.exam_venues import ExamVenueService
from backend.planning_ports import (
    ExamVenueError, VenueActorFacts, VenueCommandFacts, VenueCommandResult
)

class FakeVenueUnitOfWork:
    def __init__(self, command):
        self.command = command
        self.committed_plans = []
    def facts(self):
        command = self.command
        def actor_for(committee_id):
            if command.actor_member_id is None:
                return None
            return VenueActorFacts(
                member_id=command.actor_member_id,
                person_id=command.actor_person_id or 1,
                committee_id=committee_id,
                committee_role="chair",
                is_active=True,
            )
        if command.kind.name in {"CREATE_CONTACT", "UPDATE_CONTACT"}:
            return VenueCommandFacts(
                actor=actor_for(9), venue_id=4, venue_committee_id=9,
                venue_scope="committee", room_venue_ids={3: 99}
            )
        if command.kind.name == "CREATE_VENUE":
            candidates = ()
            if command.values.get("name") == "Nord":
                candidates = ({"scope": "global", "committee_id": None,
                    "normalized_name": "nord", "street": "", "postal_code": "",
                    "city": "", "country": "Deutschland"},)
            committee_id = command.values.get("committee_id", 9)
            return VenueCommandFacts(
                actor=actor_for(committee_id), duplicate_candidates=candidates
            )
        if command.kind.name == "UPDATE_VENUE":
            return VenueCommandFacts(
                actor=actor_for(9), venue_committee_id=9, venue_scope="committee",
                current={"scope": "committee", "committee_id": 9, "name": "Alt",
                    "street": "", "postal_code": "", "city": "", "country": "Deutschland",
                    "site_name": "", "entrance": "", "travel_directions": "",
                    "is_accessible": None, "accessibility_status": "needs_clarification",
                    "accessibility_notes": "", "latitude": None, "longitude": None,
                    "coordinate_status": "missing", "coordinate_source": None, "is_active": False},
                has_future_confirmed_assignments=True,
            )
        if command.kind.name == "UPDATE_ROOM":
            return VenueCommandFacts(
                actor=actor_for(9), venue_committee_id=9, venue_scope="committee",
                current={"name": "A-101", "building": None, "wing": None, "floor": None,
                    "room_number": None, "access_notes": None, "capacity": None, "is_active": True},
                venue_active=True, room_active=True, has_another_active_room=True,
                has_future_confirmed_assignments=True,
            )
        return VenueCommandFacts(
            actor=actor_for(9), venue_id=4, venue_committee_id=9,
            venue_scope="committee", venue_active=True
        )
    def commit(self, plan):
        self.committed_plans.append(plan)
        return VenueCommandResult(dict(plan.values))

class FakeRepository:
    def __init__(self):
        self.committed_plans = []
    @contextmanager
    def write_uow(self, command):
        uow = FakeVenueUnitOfWork(command)
        yield uow
        self.committed_plans.extend(uow.committed_plans)
    def query(self, query):
        raise AssertionError("unexpected query")

repository = FakeRepository()
service = ExamVenueService(repository)
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
created = service.create_venue(
    {"scope": "committee", "committee_id": 9, "name": "Birk"}, actor_member_id=9
)
assert created["normalized_name"] == "birk"
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
assert len(repository.committed_plans) == 1
assert repository.committed_plans[0].values["name"] == "Birk"
assert "sqlalchemy" not in sys.modules
""")
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
