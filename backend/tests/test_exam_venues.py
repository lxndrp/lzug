from __future__ import annotations

import unittest

from sqlalchemy import func, select

from backend.database import session_scope
from backend.exam_venues import (
    ExamVenueConflictError,
    ExamVenueError,
    ExamVenueInUseError,
    ExamVenueService,
    room_is_usable_for_committee,
)
from backend.models import ExamVenueAuditEvent
from backend.tests.helpers import TempDatabase


class ExamVenueServiceTests(unittest.TestCase):
    @staticmethod
    def _venue_payload(**overrides):
        payload = {
            "scope": "committee",
            "committee_id": 1,
            "name": "Prüfungszentrum Nord",
            "street": "Hafenstraße 1",
            "postal_code": "20095",
            "city": "Hamburg",
            "country": "Deutschland",
            "accessibility_status": "confirmed",
            "is_accessible": True,
            "coordinate_status": "missing",
            "is_active": False,
        }
        payload.update(overrides)
        return payload

    def _create_active_venue_and_room(self, service: ExamVenueService):
        venue = service.create_venue(self._venue_payload(), actor_member_id=1)
        room = service.create_room(
            venue["id"],
            {"name": "A-101", "capacity": 24, "is_active": True},
            actor_member_id=1,
        )
        venue = service.update_venue(
            venue["id"],
            {"expected_revision": venue["revision"], "is_active": True},
            actor_member_id=1,
        )
        assert venue is not None
        return venue, room

    def test_active_venue_needs_a_confirmed_accessibility_and_active_room(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            with self.assertRaisesRegex(ExamVenueError, "created inactive"):
                service.create_venue(self._venue_payload(is_active=True), actor_member_id=1)

            venue = service.create_venue(self._venue_payload(), actor_member_id=1)
            with self.assertRaisesRegex(ExamVenueError, "active room"):
                service.update_venue(
                    venue["id"],
                    {"expected_revision": venue["revision"], "is_active": True},
                    actor_member_id=1,
                )

            room = service.create_room(
                venue["id"], {"name": "A-101", "is_active": True}, actor_member_id=1
            )
            activated = service.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "is_active": True},
                actor_member_id=1,
            )

        self.assertEqual(1, activated["is_active"])
        self.assertEqual(room["id"], activated["rooms"][0]["id"])

    def test_venue_names_are_unique_within_a_scope_and_room_names_within_a_venue(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            first = service.create_venue(self._venue_payload(), actor_member_id=1)
            with self.assertRaisesRegex(ExamVenueConflictError, "Venue name"):
                service.create_venue(self._venue_payload(street="Hafenstraße 2"), actor_member_id=1)
            global_venue = service.create_venue(
                self._venue_payload(scope="global", committee_id=None), actor_member_id=1
            )
            service.create_room(
                first["id"], {"name": "A-101", "is_active": True}, actor_member_id=1
            )
            with self.assertRaisesRegex(ExamVenueConflictError, "Room name"):
                service.create_room(
                    first["id"], {"name": "  a-101  ", "is_active": True}, actor_member_id=1
                )

        self.assertNotEqual(first["id"], global_venue["id"])

    def test_contact_associations_are_optional_scoped_and_audited(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue, room = self._create_active_venue_and_room(service)
            other_venue = service.create_venue(
                self._venue_payload(name="Prüfungszentrum Süd", street="Elbstraße 3"),
                actor_member_id=1,
            )
            other_room = service.create_room(
                other_venue["id"], {"name": "B-201", "is_active": True}, actor_member_id=1
            )
            contact = service.create_contact(
                venue["id"],
                {"label": "Hausdienst", "phone": "+49 40 123456"},
                actor_member_id=1,
            )
            contact = service.update_contact(
                contact["id"],
                {"expected_revision": contact["revision"], "room_ids": [room["id"]]},
                actor_member_id=1,
            )
            assert contact is not None
            with self.assertRaisesRegex(ExamVenueError, "own venue"):
                service.update_contact(
                    contact["id"],
                    {
                        "expected_revision": contact["revision"],
                        "room_ids": [other_room["id"]],
                    },
                    actor_member_id=1,
                )
            with session_scope(db_path) as session:
                audit_count = session.scalar(select(func.count()).select_from(ExamVenueAuditEvent))

        self.assertEqual([room["id"]], contact["room_ids"])
        self.assertGreaterEqual(audit_count or 0, 5)

    def test_revisions_and_in_use_restrictions_prevent_lost_or_destructive_updates(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue, _room = self._create_active_venue_and_room(service)
            updated = service.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "travel_directions": "Eingang Ost"},
                actor_member_id=1,
            )
            assert updated is not None
            with self.assertRaisesRegex(ExamVenueConflictError, "stale"):
                service.update_venue(
                    venue["id"],
                    {"expected_revision": venue["revision"], "entrance": "Alt"},
                    actor_member_id=1,
                )
            with self.assertRaises(ExamVenueInUseError):
                service.delete_room(1, expected_revision=1, actor_member_id=1)

        self.assertEqual(venue["revision"] + 1, updated["revision"])

    def test_global_active_rooms_are_usable_for_any_committee(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue = service.create_venue(
                self._venue_payload(scope="global", committee_id=None, name="Zentraler Ort"),
                actor_member_id=1,
            )
            room = service.create_room(
                venue["id"], {"name": "Großer Saal", "is_active": True}, actor_member_id=1
            )
            activated = service.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "is_active": True},
                actor_member_id=1,
            )
            assert activated is not None
            with session_scope(db_path) as session:
                usable = room_is_usable_for_committee(session, room["id"], committee_id=1)

        self.assertTrue(usable)


if __name__ == "__main__":
    unittest.main()
