"""Transport conversion preserves planning values and validation boundaries."""

from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from backend.application.planning_payloads import (
    confirmed_plan_change_from_payload,
    planning_proposal_from_payload,
)


class PlanningPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "round_id": 7,
            "revision": 3,
            "exam_days": [
                {
                    "candidate_exam_day_id": 11,
                    "room_id": 5,
                    "slots": [{"round_candidate_id": 13, "slot_type": "regular"}],
                    "assignments": [
                        {
                            "committee_member_id": 17,
                            "assignment_role": "examiner",
                            "day_part": "full_day",
                        }
                    ],
                }
            ],
        }

    def test_payload_conversion_is_database_free_and_does_not_mutate_input(self) -> None:
        original = deepcopy(self.payload)
        with patch(
            "backend.persistence.database.engine_for", side_effect=AssertionError("database access")
        ):
            proposal = planning_proposal_from_payload(7, self.payload)
            change = confirmed_plan_change_from_payload(
                7, {**self.payload, "reason": "Berichtigter Plan"}
            )
        self.assertEqual(original, self.payload)
        self.assertEqual(proposal, change.plan)
        self.assertEqual("Berichtigter Plan", change.reason)
        self.assertEqual((7, 3), (proposal.round_id, proposal.revision))
        self.assertEqual(5, proposal.days[0].room_id)
        self.assertEqual(13, proposal.days[0].slots[0].round_candidate_id)
        self.assertEqual(17, proposal.days[0].assignments[0].committee_member_id)
        self.assertIsNone(proposal.days[0].id)
        self.assertIsNone(proposal.days[0].slots[0].id)
        self.assertIsNone(proposal.days[0].assignments[0].id)

    def test_location_alias_requires_an_identical_integer_room(self) -> None:
        expected = planning_proposal_from_payload(7, self.payload)
        day = self.payload["exam_days"][0]
        day["location_id"] = 5
        self.assertEqual(expected, planning_proposal_from_payload(7, self.payload))
        del day["room_id"]
        self.assertEqual(expected, planning_proposal_from_payload(7, self.payload))
        day["room_id"] = 6
        with self.assertRaisesRegex(ValueError, "room_id and location_id must match"):
            planning_proposal_from_payload(7, self.payload)

    def test_identifiers_reject_booleans_strings_and_missing_required_values(self) -> None:
        paths = (
            ((), "round_id"),
            ((), "revision"),
            (("exam_days", 0), "candidate_exam_day_id"),
            (("exam_days", 0), "room_id"),
            (("exam_days", 0, "slots", 0), "round_candidate_id"),
            (("exam_days", 0, "assignments", 0), "committee_member_id"),
        )
        for path, field in paths:
            for invalid in (None, True, False, "7", 7.0):
                with self.subTest(field=field, invalid=invalid):
                    payload = deepcopy(self.payload)
                    target = payload
                    for key in path:
                        target = target[key]
                    target[field] = invalid
                    with self.assertRaisesRegex(ValueError, f"^{field} must be an integer$"):
                        planning_proposal_from_payload(7, payload)
        with self.assertRaisesRegex(ValueError, "round_id must match the request path"):
            planning_proposal_from_payload(8, self.payload)

    def test_nested_shape_errors_precede_later_revision_errors(self) -> None:
        cases = (
            (None, "exam_days must be an array"),
            ([None], "Each exam day must be an object"),
            ([{}], "Each exam day needs slots and assignments arrays"),
            (
                [{"slots": [None], "assignments": []}],
                "Each slot must be an object with a slot_type",
            ),
            ([{"slots": [], "assignments": [None]}], "Each assignment must be an object"),
            ([{"slots": [], "assignments": [{}]}], "Assignment role and day part must be strings"),
        )
        for days, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, f"^{message}$"):
                    planning_proposal_from_payload(7, {"round_id": 7, "exam_days": days})
        with self.assertRaisesRegex(ValueError, "reason must be a string"):
            confirmed_plan_change_from_payload(7, {})
