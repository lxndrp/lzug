from __future__ import annotations

import unittest
from http import HTTPStatus

from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class ApiTests(unittest.TestCase):
    def test_health_and_round_summary_are_served_from_seeded_database(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, health = api.request("GET", "/api/health")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("ok", health["status"])
            self.assertEqual("/api/health", health["_links"]["self"]["href"])

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Winter 2026/27", summary["round"]["name"])
            self.assertEqual(
                {"candidates": 12, "mep_count": 4, "required_exam_slots": 16},
                summary["counts"],
            )
            self.assertEqual(
                "/api/round-summary?round_id=1",
                summary["_links"]["self"]["href"],
            )

    def test_api_root_openapi_and_docs_are_served(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, root = api.request("GET", "/api")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/openapi.json", root["_links"]["openapi"]["href"])
            self.assertEqual("/api/candidates", root["_links"]["candidates"]["href"])

            status, spec = api.request("GET", "/api/openapi.json")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("3.1.0", spec["openapi"])
            self.assertIn("/api/candidates/{id}", spec["paths"])
            self.assertIn("/api/exam-rounds/{id}", spec["paths"])
            self.assertIn("/api/exam-rounds/{id}/confirm-plan", spec["paths"])
            self.assertIn("/api/candidate-exam-days/generate", spec["paths"])
            self.assertIn("/api/confirmed-plans", spec["paths"])
            self.assertIn("Candidates", spec["components"]["schemas"])
            self.assertEqual(
                {"$ref": "#/components/schemas/ExamHalfYears"},
                spec["components"]["schemas"]["SchedulingOverviewItem"]["properties"][
                    "exam_half_year"
                ],
            )

            status, headers, body = api.request_raw("GET", "/api/docs")
            assert_status(status, HTTPStatus.OK)
            self.assertIn("text/html", headers["content-type"])
            self.assertIn(b"/api/openapi.json", body)

    def test_confirmed_plan_calendar_excludes_proposals_and_includes_schedule_context(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, proposal = api.request("POST", "/api/planning-proposals", {"round_id": 1})
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("plan_proposed", proposal["status"])

            status, empty_calendar = api.request("GET", "/api/confirmed-plans")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([], empty_calendar["items"])

            status, _confirmed = api.request("POST", "/api/exam-rounds/1/confirm-plan")
            assert_status(status, HTTPStatus.OK)
            status, calendar = api.request("GET", "/api/confirmed-plans")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/confirmed-plans", calendar["_links"]["self"]["href"])
            plan = calendar["items"][0]
            self.assertEqual("PA Fachinformatiker Hamburg 1", plan["committee"]["name"])
            self.assertGreaterEqual(len(plan["days"]), 1)
            first_day = plan["days"][0]
            self.assertGreaterEqual(len(first_day["slots"]), 1)
            self.assertGreaterEqual(len(first_day["assignments"]), 1)
            self.assertIn("candidate", first_day["slots"][0])
            self.assertIn(first_day["slots"][0]["slot_type"], {"regular", "mep"})
            self.assertEqual("confirmed", first_day["assignments"][-1]["fallback_status"])

    def test_scheduling_overview_groups_active_rounds_and_excludes_finished_work(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            for year, name, round_status in (
                (2027, "Offene Runde", "draft"),
                (2028, "Bestätigte Runde", "plan_confirmed"),
                (2029, "Archivierte Runde", "completed"),
            ):
                status, half_year = api.request(
                    "POST",
                    "/api/exam-half-years",
                    {"season": "summer", "year": year, "status": "draft"},
                )
                assert_status(status, HTTPStatus.CREATED)
                status, _round = api.request(
                    "POST",
                    "/api/exam-rounds",
                    {
                        "exam_half_year_id": half_year["id"],
                        "committee_id": 1,
                        "name": name,
                        "status": round_status,
                        "created_by_member_id": 1,
                    },
                )
                assert_status(status, HTTPStatus.CREATED)

            status, open_round = api.request("GET", "/api/exam-rounds?status=draft")
            assert_status(status, HTTPStatus.OK)
            open_round_id = next(
                item["id"] for item in open_round["items"] if item["name"] == "Offene Runde"
            )
            status, _updated = api.request(
                "PATCH", f"/api/exam-rounds/{open_round_id}", {"status": "plan_proposed"}
            )
            assert_status(status, HTTPStatus.OK)

            status, overview = api.request("GET", "/api/scheduling-overview")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/scheduling-overview", overview["_links"]["self"]["href"])
            groups = {item["name"]: item for item in overview["items"]}
            self.assertEqual("coordination", groups["Offene Runde"]["status_group"])
            self.assertTrue(groups["Offene Runde"]["can_continue"])
            self.assertEqual("coordination", groups["Winter 2026/27"]["status_group"])
            self.assertEqual("confirmed", groups["Bestätigte Runde"]["status_group"])
            self.assertFalse(groups["Bestätigte Runde"]["can_continue"])
            self.assertNotIn("Archivierte Runde", groups)

    def test_collection_and_resource_responses_are_self_describing(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, candidates = api.request("GET", "/api/candidates")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/candidates", candidates["_links"]["self"]["href"])
            self.assertEqual("POST", candidates["_links"]["create"]["method"])
            self.assertEqual(12, len(candidates["items"]))
            first_candidate = candidates["items"][0]
            self.assertEqual(
                f"/api/candidates/{first_candidate['id']}",
                first_candidate["_links"]["self"]["href"],
            )

            status, candidate = api.request("GET", "/api/candidates/1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/candidates/1", candidate["_links"]["self"]["href"])
            self.assertEqual("PATCH", candidate["_links"]["update"]["method"])
            self.assertEqual("DELETE", candidate["_links"]["delete"]["method"])

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
                {
                    "training_company": "Neue Muster GmbH",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": False,
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Neue Muster GmbH", updated["training_company"])

            status, round_candidates = api.request("GET", "/api/round-candidates?round_id=1")
            assert_status(status, HTTPStatus.OK)
            round_candidate = next(
                item
                for item in round_candidates["items"]
                if item["candidate_id"] == candidate["id"]
            )
            self.assertEqual(3, round_candidate["attempt_number"])
            self.assertFalse(round_candidate["requires_mep"])

            status, body = api.request("DELETE", f"/api/candidates/{candidate['id']}")
            assert_status(status, HTTPStatus.NO_CONTENT)
            self.assertIsNone(body)

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(12, summary["counts"]["candidates"])
            self.assertEqual(4, summary["counts"]["mep_count"])

    def test_exam_round_metadata_can_be_updated_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, updated = api.request(
                "PATCH",
                "/api/exam-rounds/1",
                {
                    "name": "Sommer 2027",
                    "availability_deadline": "2027-04-15 18:00:00",
                    "availability_reminder_at": "2027-04-08 09:00:00",
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Sommer 2027", updated["name"])

            status, round_data = api.request("GET", "/api/exam-rounds/1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Sommer 2027", round_data["name"])

            status, error = api.request(
                "PATCH",
                "/api/exam-rounds/1",
                {
                    "availability_deadline": "2027-04-15 18:00:00",
                    "availability_reminder_at": "2027-04-16 09:00:00",
                },
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertEqual(
                "Availability reminder must be before the deadline",
                error["error"],
            )

    def test_exam_half_year_and_committee_round_can_be_created_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, half_year = api.request(
                "POST",
                "/api/exam-half-years",
                {"season": "summer", "year": 2027, "status": "draft"},
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("summer", half_year["season"])

            status, exam_round = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "exam_half_year_id": half_year["id"],
                    "committee_id": 1,
                    "name": "Sommer 2027 · PA Fachinformatiker Hamburg 1",
                    "created_by_member_id": 1,
                },
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual(half_year["id"], exam_round["exam_half_year_id"])

            status, error = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "exam_half_year_id": half_year["id"],
                    "committee_id": 1,
                    "name": "Doppelte Runde",
                    "created_by_member_id": 1,
                },
            )
            assert_status(status, HTTPStatus.CONFLICT)
            self.assertIn("UNIQUE", error["error"])

    def test_candidate_committee_change_is_visible_as_history_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, committee = api.request(
                "POST",
                "/api/committees",
                {"name": "PA Fachinformatiker Hamburg 2", "occupation": "Fachinformatiker/in"},
            )
            assert_status(status, HTTPStatus.CREATED)
            status, member = api.request(
                "POST",
                "/api/members",
                {
                    "person_id": 1,
                    "committee_id": committee["id"],
                    "member_status": "ordinary",
                    "committee_role": "chair",
                    "representing_side": "employer",
                    "is_active": True,
                },
            )
            assert_status(status, HTTPStatus.CREATED)
            status, target_round = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "exam_half_year_id": 1,
                    "committee_id": committee["id"],
                    "name": "Winter 2026/27 · PA Fachinformatiker Hamburg 2",
                    "created_by_member_id": member["id"],
                },
            )
            assert_status(status, HTTPStatus.CREATED)

            status, error = api.request(
                "PATCH",
                "/api/candidates/1",
                {"exam_round_id": target_round["id"], "attempt_number": 2},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("reason", error["error"])

            status, _candidate = api.request(
                "PATCH",
                "/api/candidates/1",
                {
                    "exam_round_id": target_round["id"],
                    "attempt_number": 2,
                    "requires_mep": True,
                    "assignment_change_reason": "Wechsel wegen Ausschusszuständigkeit",
                },
            )
            assert_status(status, HTTPStatus.OK)
            status, history = api.request(
                "GET",
                "/api/candidate-committee-assignments?candidate_id=1",
            )
            assert_status(status, HTTPStatus.OK)

        self.assertEqual(2, len(history["items"]))
        self.assertFalse(history["_links"].get("create"))
        historic = next(item for item in history["items"] if item["exam_round_id"] == 1)
        self.assertEqual("Wechsel wegen Ausschusszuständigkeit", historic["change_reason"])
        self.assertNotIn("update", historic["_links"])
        self.assertNotIn("delete", historic["_links"])

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

            status, body = api.request_raw(
                "POST",
                "/api/planning-proposals",
                {"round_id": "not-a-number"},
            )[:2]
            assert_status(status, HTTPStatus.BAD_REQUEST)

            status, body = api.request_raw(
                "POST",
                "/api/candidates",
                None,
            )[:2]
            assert_status(status, HTTPStatus.CONFLICT)

    def test_confirmation_without_proposal_returns_bad_request(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, body = api.request("POST", "/api/exam-rounds/1/confirm-plan", {})
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertEqual("No planning proposal found", body["error"])

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
                    "exclude_public_holidays": True,
                    "holiday_subdivision_code": "DE-NW",
                    "default_location_id": 2,
                    "updated_by_member_id": 1,
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(1, settings["id"])
            self.assertEqual(0, settings["lunch_break_enabled"])
            self.assertEqual(1, settings["exclude_public_holidays"])
            self.assertEqual("DE-NW", settings["holiday_subdivision_code"])

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
                    "exclude_public_holidays": True,
                    "holiday_subdivision_code": "DE-NW",
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

    def test_candidate_exam_days_can_be_generated_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, settings = api.request(
                "POST",
                "/api/planning-settings",
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W23",
                    "calendar_week_to": "2026-W23",
                    "exams_per_day": 6,
                    "max_exam_days_per_week": 3,
                    "lunch_break_enabled": True,
                    "exclude_public_holidays": True,
                    "holiday_subdivision_code": "DE-NW",
                    "default_location_id": 1,
                    "updated_by_member_id": 1,
                },
            )
            assert_status(status, HTTPStatus.OK)

            status, result = api.request(
                "POST",
                "/api/candidate-exam-days/generate",
                {"round_id": 1},
            )

            assert_status(status, HTTPStatus.OK)
            self.assertEqual(4, result["counts"]["created"])
            self.assertEqual("2026-06-04", result["excluded_holidays"][0]["date"])
            self.assertEqual(
                "/api/candidate-exam-days?round_id=1",
                result["_links"]["candidate-exam-days"]["href"],
            )

    def test_planning_proposal_can_be_generated_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, proposal = api.request(
                "POST",
                "/api/planning-proposals",
                {"round_id": 1},
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertTrue(proposal["validation"]["passed"])
            self.assertEqual(16, proposal["counts"]["planned_slots"])
            self.assertEqual(
                "/api/exam-days?round_id=1",
                proposal["_links"]["exam-days"]["href"],
            )

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("plan_proposed", summary["round"]["status"])

    def test_planning_proposal_can_be_confirmed_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _proposal = api.request(
                "POST",
                "/api/planning-proposals",
                {"round_id": 1},
            )
            assert_status(status, HTTPStatus.CREATED)

            status, confirmed = api.request(
                "POST",
                "/api/exam-rounds/1/confirm-plan",
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("plan_confirmed", confirmed["status"])
            self.assertEqual(16, confirmed["counts"]["confirmed_slots"])
            self.assertEqual(
                "/api/round-summary?round_id=1",
                confirmed["_links"]["round-summary"]["href"],
            )

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("plan_confirmed", summary["round"]["status"])


if __name__ == "__main__":
    unittest.main()
