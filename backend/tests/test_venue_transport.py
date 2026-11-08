from __future__ import annotations

import unittest

from starlette.datastructures import QueryParams

from backend import http_hateoas as hateoas
from backend.api_contracts import PlanningSettingsRequest
from backend.application.resource_access import ResourceKind
from backend.http_resources import REST_RESOURCES
from backend.http_transport import RequestContext, planning_proposal_from_payload


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
        payload = PlanningSettingsRequest(default_location_id=11).model_dump(exclude_unset=True)
        self.assertEqual({"default_room_id": 11}, payload)

        with self.assertRaisesRegex(ValueError, "must match"):
            PlanningSettingsRequest(default_location_id=11, default_room_id=12)

        settings = hateoas.resource_item(
            "planning-settings",
            REST_RESOURCES["planning-settings"],
            {"id": 1, "exam_round_id": 2, "default_room_id": 11},
        )
        day = hateoas.resource_item(
            "exam-days",
            REST_RESOURCES["exam-days"],
            {"id": 7, "exam_round_id": 2, "room_id": 11},
        )
        proposal = hateoas.editable_planning_proposal(
            {"round_id": 1, "revision": 2, "exam_days": [{"room_id": 11}]}
        )

        self.assertEqual(11, settings["default_room_id"])
        self.assertEqual(11, settings["default_location_id"])
        self.assertEqual("/api/exam-rounds/2", settings["_links"]["exam_round"]["href"])
        self.assertEqual(11, day["room_id"])
        self.assertEqual(11, day["location_id"])
        self.assertEqual("/api/exam-rounds/2", day["_links"]["exam_round"]["href"])
        self.assertEqual("/api/exam-rooms/11", day["_links"]["room"]["href"])
        self.assertEqual(11, proposal["exam_days"][0]["room_id"])
        self.assertEqual(11, proposal["exam_days"][0]["location_id"])

    def test_resource_filters_use_explicit_http_metadata(self) -> None:
        resource = REST_RESOURCES["planning-settings"]
        context = object.__new__(RequestContext)

        filters = context.resource_filters(
            resource, QueryParams("round_id=7&unknown=9&calendar_week_from=12")
        )

        self.assertIs(ResourceKind.PLANNING_SETTINGS, resource.kind)
        self.assertEqual({"exam_round_id": 7, "calendar_week_from": "12"}, filters)


if __name__ == "__main__":
    unittest.main()
