from __future__ import annotations

import unittest
from http import HTTPStatus

from tests.helpers import ApiServer, TempDatabase, assert_status


class ApiTests(unittest.TestCase):
    def test_health_and_round_summary_are_served_from_seeded_database(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, health = api.request("GET", "/api/health")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual({"status": "ok"}, health)

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Winter 2026/27", summary["round"]["name"])
            self.assertEqual(
                {"candidates": 12, "mep_count": 4, "required_exam_slots": 16},
                summary["counts"],
            )

    def test_candidate_crud_over_http_updates_round_counts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, candidate = api.request(
                "POST",
                "/api/candidates",
                {
                    "first_name": "Erika",
                    "last_name": "Muster",
                    "ihk_exam_number": "FI-2026-9999",
                    "specialization": "application_development",
                    "training_company": "Muster GmbH",
                    "exam_round_id": 1,
                    "attempt_number": 2,
                    "requires_mep": True,
                },
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("Erika", candidate["first_name"])

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(13, summary["counts"]["candidates"])
            self.assertEqual(5, summary["counts"]["mep_count"])

            status, updated = api.request(
                "PATCH",
                f"/api/candidates/{candidate['id']}",
                {"training_company": "Neue Muster GmbH"},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Neue Muster GmbH", updated["training_company"])

            status, body = api.request("DELETE", f"/api/candidates/{candidate['id']}")
            assert_status(status, HTTPStatus.NO_CONTENT)
            self.assertIsNone(body)

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(12, summary["counts"]["candidates"])
            self.assertEqual(4, summary["counts"]["mep_count"])

    def test_invalid_payload_and_unknown_resources_return_client_errors(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, body = api.request("GET", "/api/does-not-exist")
            assert_status(status, HTTPStatus.NOT_FOUND)
            self.assertEqual("Not found", body["error"])

            status, body = api.request(
                "POST",
                "/api/candidates",
                {"first_name": "Ohne Pflichtfelder"},
            )
            assert_status(status, HTTPStatus.CONFLICT)
            self.assertIn("NOT NULL", body["error"])

    def test_planning_settings_and_availabilities_are_writable(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, settings = api.request(
                "POST",
                "/api/planning-settings",
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W47",
                    "calendar_week_to": "2026-W50",
                    "exams_per_day": 5,
                    "max_exam_days_per_week": 4,
                    "lunch_break_enabled": False,
                    "default_location_id": 2,
                    "updated_by_member_id": 1,
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(1, settings["id"])
            self.assertEqual(0, settings["lunch_break_enabled"])

            status, body = api.request(
                "POST",
                "/api/planning-settings",
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W47",
                    "calendar_week_to": "2026-W50",
                    "exams_per_day": 5,
                    "max_exam_days_per_week": 5,
                    "lunch_break_enabled": False,
                    "default_location_id": 2,
                    "updated_by_member_id": 2,
                },
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Only the committee chair", body["error"])

            status, availability = api.request(
                "POST",
                "/api/member-availabilities",
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": 1,
                    "availability": "morning",
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(21, availability["id"])
            self.assertIsNotNone(availability["responded_at"])

            status, availability = api.request(
                "PATCH",
                "/api/member-availabilities/21",
                {"availability": "pending"},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIsNone(availability["responded_at"])


if __name__ == "__main__":
    unittest.main()
