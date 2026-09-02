from __future__ import annotations

import unittest
from http import HTTPStatus

from backend.auth import AuthenticationRepository
from backend.contract import validate_response
from backend.tests.helpers import ApiServer, TempDatabase


class ExamVenueHttpTests(unittest.TestCase):
    @staticmethod
    def venue_payload(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "scope": "committee",
            "committee_id": 1,
            "name": "Prüfungszentrum HTTP",
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

    def request(
        self,
        api: ApiServer,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        **kwargs: object,
    ) -> tuple[int, object]:
        status, response = api.request(method, path, payload, **kwargs)
        if api.client is None:
            raise AssertionError("API client is not active")
        validate_response(api.client.app.openapi(), method, path, status, response)
        return status, response

    def test_venue_room_contact_lifecycle_uses_revisioned_aggregate_routes(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, venue = self.request(api, "POST", "/api/exam-venues", self.venue_payload())
            self.assertEqual(HTTPStatus.CREATED, status)
            self.assertIsInstance(venue, dict)

            status, room = self.request(
                api,
                "POST",
                f"/api/exam-venues/{venue['id']}/rooms",
                {"name": "A-101", "capacity": 24, "is_active": True},
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            self.assertIsInstance(room, dict)

            status, contact = self.request(
                api,
                "POST",
                f"/api/exam-venues/{venue['id']}/contacts",
                {
                    "label": "Hausdienst",
                    "phone": "+49 40 123456",
                    "room_ids": [room["id"]],
                },
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            self.assertIsInstance(contact, dict)
            self.assertEqual([room["id"]], contact["room_ids"])

            status, activated = self.request(
                api,
                "PATCH",
                f"/api/exam-venues/{venue['id']}",
                {"expected_revision": venue["revision"], "is_active": True},
            )
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIsInstance(activated, dict)
            self.assertEqual(1, activated["is_active"])
            self.assertEqual(room["id"], activated["rooms"][0]["id"])
            self.assertEqual(contact["id"], activated["contacts"][0]["id"])

            status, location = self.request(api, "GET", f"/api/locations/{room['id']}")
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIsInstance(location, dict)
            self.assertEqual(venue["id"], location["venue_id"])
            self.assertEqual(room["id"], location["id"])

            status, conflict = self.request(
                api,
                "PATCH",
                f"/api/exam-rooms/{room['id']}",
                {"expected_revision": room["revision"] + 1, "name": "A-102"},
            )
            self.assertEqual(HTTPStatus.CONFLICT, status)
            self.assertIsInstance(conflict, dict)
            self.assertEqual("exam_venue_conflict", conflict["error"]["code"])

    def test_scope_boundary_and_legacy_writes_are_rejected(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, global_error = self.request(
                api,
                "POST",
                "/api/exam-venues",
                self.venue_payload(scope="global", committee_id=None, name="Globales Zentrum"),
            )
            self.assertEqual(HTTPStatus.FORBIDDEN, status)
            self.assertIsInstance(global_error, dict)

            member = AuthenticationRepository(db_path).create_session(2)
            status, management_error = self.request(
                api,
                "POST",
                "/api/exam-venues",
                self.venue_payload(),
                credentials=member,
            )
            self.assertEqual(HTTPStatus.FORBIDDEN, status)
            self.assertIsInstance(management_error, dict)

            status, deprecated_error = self.request(
                api,
                "POST",
                "/api/locations",
                {"name": "Alter Ort"},
            )
            self.assertEqual(HTTPStatus.GONE, status)
            self.assertIsInstance(deprecated_error, dict)

    def test_operator_decides_pending_promotion_without_gaining_committee_access(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, hidden_venue = self.request(
                api,
                "POST",
                "/api/exam-venues",
                self.venue_payload(name="Nur im Ausschuss"),
            )
            self.assertEqual(HTTPStatus.CREATED, status)

            status, venue = self.request(
                api,
                "POST",
                "/api/exam-venues",
                self.venue_payload(name="Global geeignet", street="Anderer Weg 7"),
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _room = self.request(
                api,
                "POST",
                f"/api/exam-venues/{venue['id']}/rooms",
                {"name": "Saal", "capacity": 20, "is_active": True},
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, venue = self.request(
                api,
                "PATCH",
                f"/api/exam-venues/{venue['id']}",
                {"expected_revision": venue["revision"], "is_active": True},
            )
            self.assertEqual(HTTPStatus.OK, status)
            status, request = self.request(
                api,
                "POST",
                f"/api/exam-venues/{venue['id']}/promotion-requests",
                {
                    "expected_revision": venue["revision"],
                    "reason": "Für mehrere Ausschüsse geeignet",
                },
            )
            self.assertEqual(HTTPStatus.CREATED, status)

            auth = AuthenticationRepository(db_path)
            operator = auth.create_account("operator@example.invalid", is_operator=True)
            operator_session = auth.create_session(operator["id"])
            status, visible = self.request(
                api,
                "GET",
                "/api/exam-venues",
                credentials=operator_session,
            )
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual([venue["id"]], [item["id"] for item in visible["items"]])
            self.assertNotIn(hidden_venue["id"], [item["id"] for item in visible["items"]])

            status, promoted = self.request(
                api,
                "POST",
                f"/api/exam-venue-promotion-requests/{venue['id']}/decision",
                {
                    "expected_revision": venue["revision"],
                    "decision": "approve",
                    "reason": "Qualität geprüft",
                },
                credentials=operator_session,
            )
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(venue["id"], promoted["id"])
            self.assertEqual("global", promoted["scope"])
            self.assertIsNone(promoted["committee_id"])

    def test_round_summary_keeps_the_legacy_default_location_reference(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, summary = self.request(api, "GET", "/api/round-summary?round_id=1")

        self.assertEqual(HTTPStatus.OK, status)
        self.assertIsInstance(summary, dict)
        self.assertEqual(1, summary["settings"]["default_room_id"])
        self.assertEqual(1, summary["settings"]["default_location_id"])


if __name__ == "__main__":
    unittest.main()
