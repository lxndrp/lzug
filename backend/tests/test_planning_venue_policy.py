"""Pure Planning venue-policy tests over detached values."""

from __future__ import annotations

import unittest

from backend.planning.exam_venues import ExamVenuePolicy
from backend.planning_ports import ExamVenueError


class ExamVenuePolicyTests(unittest.TestCase):
    def test_venue_values_validate_scope_accessibility_and_detached_coordinates(self) -> None:
        payload = {
            "scope": "committee",
            "committee_id": 4,
            "name": "  Nord  ",
            "street": "Testweg 1",
            "postal_code": "20095",
            "city": "Hamburg",
            "country": "DE",
            "is_accessible": True,
            "accessibility_status": "confirmed",
            "latitude": 53.55,
            "longitude": 9.99,
            "coordinate_status": "confirmed",
            "coordinate_source": "manual",
            "is_active": False,
        }

        values, reason = ExamVenuePolicy.venue_values(payload)

        self.assertIsNone(reason)
        self.assertEqual("Nord", values["name"])
        self.assertEqual("nord", values["normalized_name"])
        self.assertEqual(4, values["committee_id"])
        self.assertEqual(53.55, values["latitude"])

    def test_scope_and_accessibility_must_be_consistent(self) -> None:
        with self.assertRaisesRegex(ExamVenueError, "scope and committee"):
            ExamVenuePolicy.venue_values({"scope": "global", "committee_id": 4, "name": "Nord"})

        with self.assertRaisesRegex(ExamVenueError, "exactly one yes/no"):
            ExamVenuePolicy.venue_values(
                {
                    "scope": "committee",
                    "committee_id": 4,
                    "accessibility_status": "confirmed",
                    "is_accessible": None,
                }
            )

    def test_activation_policy_uses_detached_room_fact(self) -> None:
        values, _ = ExamVenuePolicy.venue_values(
            {
                "scope": "committee",
                "committee_id": 4,
                "name": "Nord",
                "street": "Testweg 1",
                "postal_code": "20095",
                "city": "Hamburg",
                "country": "DE",
                "is_accessible": True,
                "accessibility_status": "confirmed",
                "is_active": True,
            }
        )

        with self.assertRaisesRegex(ExamVenueError, "active room"):
            ExamVenuePolicy.assert_venue_can_be_active(values, has_active_room=False)
        ExamVenuePolicy.assert_venue_can_be_active(values, has_active_room=True)

    def test_room_deactivation_policy_uses_detached_aggregate_facts(self) -> None:
        with self.assertRaisesRegex(ExamVenueError, "active room"):
            ExamVenuePolicy.assert_room_can_be_deactivated(
                venue_active=True,
                room_active=True,
                has_another_active_room=False,
            )

        ExamVenuePolicy.assert_room_can_be_deactivated(
            venue_active=True,
            room_active=True,
            has_another_active_room=True,
        )
        ExamVenuePolicy.assert_room_can_be_deactivated(
            venue_active=False,
            room_active=True,
            has_another_active_room=False,
        )

    def test_address_change_marks_detached_coordinates_for_review(self) -> None:
        values = {
            "street": "Neu",
            "postal_code": "20095",
            "city": "Hamburg",
            "country": "DE",
            "latitude": 53.55,
            "coordinate_status": "confirmed",
        }

        ExamVenuePolicy.coordinate_status_after_address_change(
            values,
            {"street": "Alt", "postal_code": "20095", "city": "Hamburg", "country": "DE"},
            {"street"},
        )

        self.assertEqual("needs_review", values["coordinate_status"])


if __name__ == "__main__":
    unittest.main()
