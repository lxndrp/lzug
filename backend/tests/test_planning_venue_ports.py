"""Planning venue service contract tests using port doubles."""

from __future__ import annotations

import unittest

from backend.composition import exam_venue_service
from backend.persistence.database import session_scope
from backend.persistence.models import ExamVenueAuditEvent
from backend.planning.exam_venues import ExamVenueService
from backend.planning_ports import (
    ExamVenueError,
    GeocodeCandidate,
    VenueChange,
    VenueCommand,
    VenueCommandKind,
    VenueCommandResult,
    VenueQuery,
    VenueQueryKind,
    VenueQueryResult,
    VenueRoomAvailability,
    room_is_usable_for_committee,
)
from backend.tests.helpers import TempDatabase


class _VenueRepositoryDouble:
    def __init__(self) -> None:
        self.commands: list[VenueCommand] = []
        self.queries: list[VenueQuery] = []

    def execute(self, command: VenueCommand) -> VenueCommandResult:
        self.commands.append(command)
        return VenueCommandResult(
            {"id": command.entity_id or 7, "name": str((command.values or {}).get("name", ""))},
            VenueChange(
                11,
                command.entity_id or 7,
                "venue",
                command.entity_id or 7,
                2,
                frozenset({"name"}),
            ),
        )

    def query(self, query: VenueQuery) -> VenueQueryResult:
        self.queries.append(query)
        return VenueQueryResult([{"id": 7, "name": "Nord"}])


class _GeocoderDouble:
    def __init__(self) -> None:
        self.addresses: list[str] = []

    def geocode(self, address: str) -> GeocodeCandidate:
        self.addresses.append(address)
        return GeocodeCandidate(53.55, 9.99, "test")


class PlanningVenuePortTests(unittest.TestCase):
    def test_service_issues_typed_queries_and_commands_without_sqlite(self) -> None:
        repository = _VenueRepositoryDouble()
        service = ExamVenueService(repository)

        rows = service.list_venues()
        created = service.create_venue({"name": "Nord"}, actor_member_id=4)

        self.assertEqual([{"id": 7, "name": "Nord"}], rows)
        self.assertEqual({"id": 7, "name": "Nord"}, created)
        self.assertEqual(VenueQueryKind.LIST_VENUES, repository.queries[0].kind)
        self.assertEqual(VenueCommandKind.CREATE_VENUE, repository.commands[0].kind)
        self.assertEqual(4, repository.commands[0].actor_member_id)

    def test_explicit_execute_returns_committed_change_basis(self) -> None:
        repository = _VenueRepositoryDouble()
        service = ExamVenueService(repository)

        result = service.execute(
            VenueCommand(VenueCommandKind.UPDATE_VENUE, entity_id=7, expected_revision=1)
        )

        self.assertEqual(11, result.change.audit_id)
        self.assertEqual(frozenset({"name"}), result.change.changed_fields)

    def test_geocoding_uses_a_provider_free_planning_port(self) -> None:
        repository = _VenueRepositoryDouble()
        geocoder = _GeocoderDouble()
        service = ExamVenueService(repository, geocoder=geocoder)

        candidate = service.geocode("Testweg 1, Hamburg")

        self.assertEqual(["Testweg 1, Hamburg"], geocoder.addresses)
        self.assertEqual(
            (53.55, 9.99, "test"),
            (candidate.latitude, candidate.longitude, candidate.source),
        )

    def test_room_eligibility_uses_detached_values_and_explicit_provider_policy(self) -> None:
        room = VenueRoomAvailability(
            room_active=True,
            venue_active=True,
            venue_scope="committee",
            committee_id=4,
            coordinate_status="missing",
        )

        self.assertTrue(room_is_usable_for_committee(room, 4))
        self.assertFalse(
            room_is_usable_for_committee(
                room,
                4,
                require_confirmed_coordinates=True,
            )
        )
        self.assertFalse(room_is_usable_for_committee(None, 4))

    def test_sqlite_command_commits_venue_and_audit_before_returning_change(self) -> None:
        with TempDatabase() as db_path:
            service = exam_venue_service(db_path)
            venue = service.create_venue(
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Port-Testort",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "DE",
                    "is_accessible": None,
                    "accessibility_status": "needs_clarification",
                    "coordinate_status": "missing",
                    "is_active": False,
                },
                actor_member_id=1,
            )

            result = service.execute(
                VenueCommand(
                    VenueCommandKind.UPDATE_VENUE,
                    entity_id=venue["id"],
                    values={"name": "Port-Testort Neu"},
                    actor_member_id=1,
                    expected_revision=venue["revision"],
                )
            )

            self.assertEqual("Port-Testort Neu", result.value["name"])
            self.assertIsNotNone(result.change)
            assert result.change is not None
            self.assertEqual(venue["id"], result.change.venue_id)
            with session_scope(db_path) as session:
                audit = session.get(ExamVenueAuditEvent, result.change.audit_id)
                self.assertIsNotNone(audit)
                self.assertEqual(result.change.revision, audit.entity_revision)

    def test_venue_policy_rejection_keeps_mutation_and_audit_atomic(self) -> None:
        with TempDatabase() as db_path:
            service = exam_venue_service(db_path)
            venue = service.create_venue(
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Inaktiver Policy-Testort",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "DE",
                    "is_accessible": True,
                    "accessibility_status": "confirmed",
                    "is_active": False,
                },
                actor_member_id=1,
            )
            with session_scope(db_path) as session:
                before_audits = session.query(ExamVenueAuditEvent).count()

            with self.assertRaisesRegex(ExamVenueError, "active room"):
                service.update_venue(
                    venue["id"],
                    {"expected_revision": venue["revision"], "is_active": True},
                    actor_member_id=1,
                )

            with session_scope(db_path) as session:
                after_audits = session.query(ExamVenueAuditEvent).count()
            stored = service.get_venue(venue["id"])

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(0, stored["is_active"])
        self.assertEqual(venue["revision"], stored["revision"])
        self.assertEqual(before_audits, after_audits)


if __name__ == "__main__":
    unittest.main()
