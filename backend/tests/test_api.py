from __future__ import annotations

import sqlite3
import unittest
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError

from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler, assert_status


class StaticTestHandler(TestLzugHandler):
    static_dir: Path | None = None


class ApiTests(unittest.TestCase):
    def test_static_files_and_spa_fallback_do_not_hide_api_or_assets(self) -> None:
        with TemporaryDirectory() as directory, TempDatabase() as db_path:
            static_dir = Path(directory) / "static"
            static_dir.mkdir()
            (static_dir / "index.html").write_text("<app-root>shell</app-root>", encoding="utf-8")
            (static_dir / "main.123.js").write_text("console.log('ok')", encoding="utf-8")
            (static_dir / "archive.unknown").write_bytes(b"opaque")
            with (
                patch.object(StaticTestHandler, "static_dir", static_dir),
                ApiServer(db_path, StaticTestHandler) as api,
            ):
                status, headers, body = api.request_raw("GET", "/dashboard")
                assert_status(status, HTTPStatus.OK)
                self.assertEqual("text/html", headers["content-type"].split(";")[0])
                self.assertIn(b"<app-root>shell</app-root>", body)

                status, headers, body = api.request_raw("GET", "/main.123.js")
                assert_status(status, HTTPStatus.OK)
                self.assertEqual("text/javascript", headers["content-type"])
                self.assertEqual(b"console.log('ok')", body)

                status, headers, body = api.request_raw("GET", "/archive.unknown")
                assert_status(status, HTTPStatus.OK)
                self.assertEqual("application/octet-stream", headers["content-type"])
                self.assertEqual(b"opaque", body)

                status, _headers, body = api.request_raw("GET", "/assets/missing.svg")
                assert_status(status, HTTPStatus.NOT_FOUND)
                self.assertIn(b"Not found", body)

                status, _headers, body = api.request_raw("GET", "/api/health")
                assert_status(status, HTTPStatus.OK)
                self.assertIn(b'"status": "ok"', body)

                status, _headers, body = api.request_raw("GET", "/%2e%2e/index.html")
                assert_status(status, HTTPStatus.NOT_FOUND)
                self.assertIn(b"Not found", body)

    def test_static_asset_index_excludes_symlinks_outside_the_root(self) -> None:
        with TemporaryDirectory() as directory, TempDatabase() as db_path:
            root = Path(directory)
            static_dir = root / "static"
            static_dir.mkdir()
            (static_dir / "index.html").write_text("shell", encoding="utf-8")
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            try:
                (static_dir / "escape.txt").symlink_to(outside)
            except OSError as error:
                self.skipTest(f"Symlinks are unavailable: {error}")

            with (
                patch.object(StaticTestHandler, "static_dir", static_dir),
                ApiServer(db_path, StaticTestHandler) as api,
            ):
                status, _headers, body = api.request_raw("GET", "/escape.txt")

            assert_status(status, HTTPStatus.NOT_FOUND)
            self.assertNotIn(b"secret", body)

    def test_database_errors_use_public_messages(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            with patch(
                "backend.app.ResourceRepository.candidate_list",
                side_effect=SQLAlchemyError("private database details"),
            ):
                status, body = api.request("GET", "/api/candidates")

        assert_status(status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual("Database operation failed.", body["error"])

    def test_health_reports_uninitialized_database_as_not_ready(self) -> None:
        with TemporaryDirectory() as directory:
            with ApiServer(Path(directory) / "uninitialized.sqlite") as api:
                status, health = api.request("GET", "/api/health")

        assert_status(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual("unavailable", health["status"])
        self.assertEqual({"status", "_links"}, set(health))

    def test_health_reports_required_migration_without_exposing_data(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with sqlite3.connect(db_path) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP TABLE auth_recovery_code")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_secret_encrypted")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_last_step")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_enabled")
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration " "WHERE name IN (?, ?, ?)",
                    (
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                        "011_add_local_password_totp_auth.sql",
                    ),
                )
                connection.commit()

            with ApiServer(db_path) as api:
                status, health = api.request("GET", "/api/health")

        assert_status(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual("unavailable", health["status"])
        self.assertEqual({"status", "_links"}, set(health))

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
            self.assertIn("/api/exam-rounds/{id}/request-availabilities", spec["paths"])
            self.assertIn("/api/candidate-exam-days/generate", spec["paths"])
            self.assertIn("/api/confirmed-plans", spec["paths"])
            self.assertIn("/api/confirmed-plan-days/{id}", spec["paths"])
            self.assertIn("/api/session", spec["paths"])
            self.assertIn("/api/session/rotate", spec["paths"])
            self.assertIn("/api/session/logout", spec["paths"])
            for auth_path in (
                "/api/auth/login",
                "/api/auth/invitation/prepare",
                "/api/auth/invitation/activate",
                "/api/auth/recovery/prepare",
                "/api/auth/recovery/complete",
            ):
                self.assertIn(auth_path, spec["paths"])
                self.assertNotIn("security", spec["paths"][auth_path]["post"])
            self.assertIn(
                "totp_secret",
                spec["components"]["schemas"]["RecoveryPreparation"]["properties"],
            )
            self.assertEqual(
                ["status", "_links"],
                spec["components"]["schemas"]["Health"]["required"],
            )
            self.assertEqual({"sessionCookie": []}, spec["paths"]["/api"]["get"]["security"][0])
            self.assertEqual(
                {"sessionCookie": []},
                spec["paths"]["/api/openapi.json"]["get"]["security"][0],
            )
            self.assertEqual(
                {"sessionCookie": [], "csrfHeader": []},
                spec["paths"]["/api/candidates"]["post"]["security"][0],
            )
            self.assertIn("401", spec["paths"]["/api/candidates"]["get"]["responses"])
            self.assertIn("403", spec["paths"]["/api/candidates"]["post"]["responses"])
            self.assertNotIn("security", spec["paths"]["/api/health"]["get"])
            self.assertEqual(
                ["completed", "cancelled", "needs_follow_up"],
                spec["components"]["schemas"]["ExamSlotStatusWrite"]["properties"]["status"][
                    "enum"
                ],
            )
            self.assertIn("Candidates", spec["components"]["schemas"])
            self.assertEqual(
                {"$ref": "#/components/schemas/ExamHalfYears"},
                spec["components"]["schemas"]["SchedulingOverviewItem"]["properties"][
                    "exam_half_year"
                ],
            )
            self.assertEqual(
                {"$ref": "#/components/schemas/ExamHalfYears"},
                spec["components"]["schemas"]["ConfirmedPlanDayView"]["properties"]["plan"][
                    "properties"
                ]["exam_half_year"],
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

            proposed_day_id = proposal["exam_days"][0]["id"]
            status, _proposed_day = api.request(
                "GET", f"/api/confirmed-plan-days/{proposed_day_id}"
            )
            assert_status(status, HTTPStatus.NOT_FOUND)

            status, empty_calendar = api.request("GET", "/api/confirmed-plans")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([], empty_calendar["items"])

            status, _confirmed = api.request("POST", "/api/exam-rounds/1/confirm-plan")
            assert_status(status, HTTPStatus.OK)
            status, calendar = api.request("GET", "/api/confirmed-plans")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("/api/confirmed-plans", calendar["_links"]["self"]["href"])
            plan = calendar["items"][0]
            self.assertEqual("Prüfungsausschuss Teststadt 1", plan["committee"]["name"])
            self.assertGreaterEqual(len(plan["days"]), 1)
            first_day = plan["days"][0]
            self.assertGreaterEqual(len(first_day["slots"]), 1)
            self.assertGreaterEqual(len(first_day["assignments"]), 1)
            self.assertIn("candidate", first_day["slots"][0])
            self.assertIn(first_day["slots"][0]["slot_type"], {"regular", "mep"})
            self.assertEqual("confirmed", first_day["assignments"][-1]["fallback_status"])

            status, day_view = api.request("GET", f"/api/confirmed-plan-days/{first_day['id']}")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(plan["id"], day_view["plan"]["id"])
            self.assertEqual(first_day["id"], day_view["day"]["id"])
            self.assertEqual(plan["name"], day_view["plan"]["name"])

            status, _missing_day = api.request("GET", "/api/confirmed-plan-days/999999")
            assert_status(status, HTTPStatus.NOT_FOUND)

    def test_exam_day_attendance_and_start_rules_are_persistent_and_idempotent(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _proposal = api.request("POST", "/api/planning-proposals", {"round_id": 1})
            assert_status(status, HTTPStatus.CREATED)
            status, _confirmed = api.request("POST", "/api/exam-rounds/1/confirm-plan", {})
            assert_status(status, HTTPStatus.OK)
            status, calendar = api.request("GET", "/api/confirmed-plans")
            assert_status(status, HTTPStatus.OK)
            day = calendar["items"][0]["days"][0]
            slot = day["slots"][0]
            morning_assignments = [
                assignment
                for assignment in day["assignments"]
                if assignment["assignment_role"] == "examiner"
                and assignment["day_part"] == "morning"
            ]

            status, error = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/attendance",
                {"status": "late"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Ankunftszeit", error["error"])

            status, updated = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/attendance",
                {"status": "late", "arrived_at": "2026-11-16T08:24:00+01:00"},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("late", updated["day"]["slots"][0]["candidate_attendance"]["status"])

            status, updated = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/attendance",
                {"status": "present", "arrived_at": None},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                {"status": "present", "arrived_at": None},
                updated["day"]["slots"][0]["candidate_attendance"],
            )

            status, blocked = api.request(
                "POST",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/start",
                {"actual_started_at": "2026-11-16T08:31:00+01:00"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("reguläre Prüfer", blocked["error"])

            for assignment in morning_assignments:
                status, _updated = api.request(
                    "PATCH",
                    f"/api/confirmed-plan-days/{day['id']}/assignments/{assignment['id']}/attendance",
                    {"status": "present", "arrived_at": "2026-11-16T08:10:00+01:00"},
                )
                assert_status(status, HTTPStatus.OK)

            status, started = api.request(
                "POST",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/start",
                {"actual_started_at": "2026-11-16T08:31:00+01:00"},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                "2026-11-16T08:31:00+01:00", started["day"]["slots"][0]["actual_started_at"]
            )
            self.assertEqual("running", started["day"]["slots"][0]["execution_status"])
            self.assertEqual(
                "2026-11-16T08:31:00+01:00", started["day"]["slots"][0]["status_changed_at"]
            )

            status, repeated = api.request(
                "POST",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/start",
                {},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                "2026-11-16T08:31:00+01:00", repeated["day"]["slots"][0]["actual_started_at"]
            )

            status, started_cancel_error = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "cancelled", "reason": "Darf nach dem Start nicht ausfallen"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("gestarteter", started_cancel_error["error"])

            status, follow_up = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "needs_follow_up"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Begründung", follow_up["error"])

            status, follow_up = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "needs_follow_up", "reason": "Nachweis der Prüfungsleistung fehlt"},
            )
            assert_status(status, HTTPStatus.OK)
            follow_up_slot = follow_up["day"]["slots"][0]
            self.assertEqual("needs_follow_up", follow_up_slot["execution_status"])
            self.assertEqual("Nachweis der Prüfungsleistung fehlt", follow_up_slot["status_reason"])
            self.assertIsNone(follow_up_slot["actual_completed_at"])

            status, completed = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "completed"},
            )
            assert_status(status, HTTPStatus.OK)
            completed_slot = completed["day"]["slots"][0]
            self.assertEqual("completed", completed_slot["execution_status"])
            self.assertIsNotNone(completed_slot["actual_completed_at"])
            self.assertEqual("Nachweis der Prüfungsleistung fehlt", completed_slot["status_reason"])

            status, terminal_error = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "needs_follow_up", "reason": "Darf nicht wieder geöffnet werden"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("nicht erlaubt", terminal_error["error"])

            cancelled_slot = day["slots"][1]
            status, missing_reason = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{cancelled_slot['id']}/status",
                {"status": "cancelled"},
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("Begründung", missing_reason["error"])

            status, cancelled = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{cancelled_slot['id']}/status",
                {"status": "cancelled", "reason": "Prüfling kurzfristig erkrankt"},
            )
            assert_status(status, HTTPStatus.OK)
            cancelled_view = next(
                item for item in cancelled["day"]["slots"] if item["id"] == cancelled_slot["id"]
            )
            self.assertEqual("cancelled", cancelled_view["execution_status"])
            self.assertEqual("Prüfling kurzfristig erkrankt", cancelled_view["status_reason"])

            status, reloaded_statuses = api.request("GET", f"/api/confirmed-plan-days/{day['id']}")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(1, reloaded_statuses["day"]["status_summary"]["completed"])
            self.assertEqual(1, reloaded_statuses["day"]["status_summary"]["cancelled"])
            reloaded_slot = next(
                item for item in reloaded_statuses["day"]["slots"] if item["id"] == slot["id"]
            )
            self.assertIsNotNone(reloaded_slot["actual_completed_at"])
            self.assertIsNotNone(reloaded_slot["status_changed_at"])

            status, reloaded = api.request("GET", f"/api/confirmed-plan-days/{day['id']}")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                "present", reloaded["day"]["slots"][0]["candidate_attendance"]["status"]
            )
            reloaded_morning = next(
                assignment
                for assignment in reloaded["day"]["assignments"]
                if assignment["id"] == morning_assignments[0]["id"]
            )
            self.assertEqual("present", reloaded_morning["attendance"]["status"])

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
            self.assertEqual("planning", groups["Offene Runde"]["status_group"])
            self.assertTrue(groups["Offene Runde"]["can_continue"])
            self.assertEqual("coordination", groups["Winter 2026/27"]["status_group"])
            self.assertEqual("confirmed", groups["Bestätigte Runde"]["status_group"])
            self.assertFalse(groups["Bestätigte Runde"]["can_continue"])
            self.assertNotIn("Archivierte Runde", groups)

    def test_prepared_draft_can_request_availabilities(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _draft = api.request("PATCH", "/api/exam-rounds/1", {"status": "draft"})
            assert_status(status, HTTPStatus.OK)

            status, requested = api.request("POST", "/api/exam-rounds/1/request-availabilities", {})

            assert_status(status, HTTPStatus.OK)
            self.assertEqual("availability_requested", requested["status"])

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
                    "first_name": "Prüfling",
                    "last_name": "API",
                    "ihk_exam_number": "TEST-2026-9999",
                    "specialization": "application_development",
                    "training_company": "Testbetrieb API",
                    "exam_round_id": 1,
                    "attempt_number": 2,
                    "requires_mep": True,
                },
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("Prüfling", candidate["first_name"])

            status, summary = api.request("GET", "/api/round-summary?round_id=1")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(13, summary["counts"]["candidates"])
            self.assertEqual(5, summary["counts"]["mep_count"])

            status, updated = api.request(
                "PATCH",
                f"/api/candidates/{candidate['id']}",
                {
                    "training_company": "Testbetrieb API Neu",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": False,
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Testbetrieb API Neu", updated["training_company"])

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
                    "name": "Sommer 2027 · Prüfungsausschuss Teststadt 1",
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
            self.assertEqual("Database constraint violated.", error["error"])

    def test_candidate_committee_change_is_visible_as_history_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            from backend.models import COMMITTEE
            from backend.repositories import ResourceRepository

            ResourceRepository(db_path).create(
                COMMITTEE,
                {
                    "name": "Prüfungsausschuss Teststadt 2",
                    "occupation": "Fachinformatiker/in",
                },
            )
            status, history = api.request(
                "GET",
                "/api/candidate-committee-assignments?candidate_id=1",
            )
            assert_status(status, HTTPStatus.OK)

        self.assertEqual(1, len(history["items"]))
        self.assertFalse(history["_links"].get("create"))
        historic = next(item for item in history["items"] if item["exam_round_id"] == 1)
        self.assertIsNone(historic["change_reason"])
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
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", body["error"])

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
            assert_status(status, HTTPStatus.FORBIDDEN)

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

            status, _member = api.request(
                "PATCH",
                "/api/members/2",
                {"committee_role": "deputy_chair", "is_active": True},
            )
            assert_status(status, HTTPStatus.OK)

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
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(5, body["max_exam_days_per_week"])
            self.assertEqual(1, body["updated_by_member_id"])

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
