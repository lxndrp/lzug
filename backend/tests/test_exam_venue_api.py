from __future__ import annotations

import unittest

from backend.authorization import AuthorizationScope
from backend.exam_venue_api import ExamVenueApi
from backend.exam_venues import ExamVenueService
from backend.tests.helpers import TempDatabase


def scope(*, management: bool) -> AuthorizationScope:
    return AuthorizationScope(
        person_id=1,
        person_ids=frozenset({1}),
        committee_ids=frozenset({1}),
        member_ids=frozenset({1}),
        management_committee_ids=frozenset({1}) if management else frozenset(),
        member_by_committee={1: 1},
    )


class ExamVenueApiTests(unittest.TestCase):
    @staticmethod
    def _payload(**overrides):
        payload = {
            "scope": "committee",
            "committee_id": 1,
            "name": "Prüfungszentrum API",
            "street": "Testweg 1",
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

    def test_committee_management_boundary_and_legacy_read_projection(self) -> None:
        with TempDatabase() as db_path:
            api = ExamVenueApi(db_path)
            venue = api.create_venue(self._payload(), scope(management=True))
            room = api.create_room(
                venue["id"], {"name": "A-101", "is_active": True}, scope(management=True)
            )
            assert room is not None
            activated = api.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "is_active": True},
                scope(management=True),
            )
            assert activated is not None

            legacy = api.get_legacy_location(room["id"], scope(management=False))
            with self.assertRaises(PermissionError):
                api.create_room(
                    venue["id"], {"name": "A-102", "is_active": True}, scope(management=False)
                )
            with self.assertRaises(PermissionError):
                api.create_venue(
                    self._payload(scope="global", committee_id=None, name="Globaler Ort"),
                    scope(management=True),
                )

        self.assertEqual(
            {
                "id": room["id"],
                "venue_id": venue["id"],
                "committee_id": 1,
                "name": "Prüfungszentrum API",
                "street": "Testweg 1",
                "postal_code": "20095",
                "city": "Hamburg",
                "room": "A-101",
                "is_active": 1,
                "created_at": room["created_at"],
                "updated_at": room["updated_at"],
            },
            legacy,
        )

    def test_scope_changes_are_reserved_for_the_promotion_workflow(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue = service.create_venue(self._payload(), actor_member_id=1)
            api = ExamVenueApi(db_path)

            with self.assertRaises(PermissionError):
                api.update_venue(
                    venue["id"],
                    {
                        "expected_revision": venue["revision"],
                        "scope": "global",
                        "committee_id": None,
                    },
                    scope(management=True),
                )


if __name__ == "__main__":
    unittest.main()
