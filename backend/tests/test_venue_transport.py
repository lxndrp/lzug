from __future__ import annotations

import unittest

from backend import hateoas
from backend.models import EXAM_DAY, PLANNING_SETTINGS
from backend.transport import RequestContext, planning_proposal_from_payload


class VenueTransportTests(unittest.TestCase):
    @staticmethod
    def _proposal_day(**overrides):
        day = {
            "id": 7,
            "candidate_exam_day_id": 3,
            "room_id": 11,
            "slots": [],
            "assignments": [],
        }
        day.update(overrides)
        return day

    def test_location_alias_requires_matching_room(self) -> None:
        proposal = planning_proposal_from_payload(
            1,
            {
                "round_id": 1,
                "revision": 2,
                "exam_days": [self._proposal_day(location_id=11)],
            },
        )
        self.assertEqual(11, proposal.days[0].room_id)

        with self.assertRaisesRegex(ValueError, "must match"):
            planning_proposal_from_payload(
                1,
                {
                    "round_id": 1,
                    "revision": 2,
                    "exam_days": [self._proposal_day(location_id=12)],
                },
            )

    def test_http_compatibility_aliases_do_not_replace_canonical_room_fields(self) -> None:
        context = object.__new__(RequestContext)
        payload = RequestContext.normalize_payload(context, {"default_location_id": 11})
        self.assertEqual({"default_room_id": 11}, payload)

        settings = hateoas.resource_item(
            "planning-settings", PLANNING_SETTINGS, {"id": 1, "default_room_id": 11}
        )
        day = hateoas.resource_item("exam-days", EXAM_DAY, {"id": 7, "room_id": 11})
        proposal = hateoas.editable_planning_proposal(
            {"round_id": 1, "revision": 2, "exam_days": [{"room_id": 11}]}
        )

        self.assertEqual(11, settings["default_room_id"])
        self.assertEqual(11, settings["default_location_id"])
        self.assertEqual(11, day["room_id"])
        self.assertEqual(11, day["location_id"])
        self.assertEqual(11, proposal["exam_days"][0]["room_id"])
        self.assertEqual(11, proposal["exam_days"][0]["location_id"])


if __name__ == "__main__":
    unittest.main()
