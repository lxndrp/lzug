from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy.exc import SQLAlchemyError

from backend.fastapi_app import MIGRATED_DOMAIN_RESOURCES, MIGRATED_PLANNING_RESOURCES
from backend.tests.helpers import (
    AdapterResponse,
    FastAPIAdapter,
    LegacyAdapter,
    TempDatabase,
    TestLzugHandler,
)


class HttpContractParityTests(unittest.TestCase):
    def assert_parity(self, left: AdapterResponse, right: AdapterResponse) -> None:
        self.assertEqual(left.status, right.status)
        if left.headers.get("content-type", "").startswith("application/json"):
            self.assertEqual(self.canonical_json(left.json), self.canonical_json(right.json))
        else:
            self.assertEqual(left.body, right.body)
        for header in (
            "cache-control",
            "content-type",
            "x-content-type-options",
            "x-frame-options",
            "referrer-policy",
            "permissions-policy",
            "cross-origin-opener-policy",
            "cross-origin-resource-policy",
            "x-permitted-cross-domain-policies",
            "content-security-policy",
            "strict-transport-security",
            "access-control-allow-origin",
            "access-control-allow-credentials",
            "vary",
            "access-control-allow-methods",
            "access-control-allow-headers",
            "access-control-max-age",
        ):
            self.assertEqual(left.headers.get(header), right.headers.get(header), header)

    def canonical_json(self, value):
        if isinstance(value, dict):
            return {
                key: (
                    "<timestamp>"
                    if key
                    in {
                        "activated_at",
                        "created_at",
                        "expires_at",
                        "feed_url",
                        "revoked_at",
                        "updated_at",
                    }
                    else self.canonical_json(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.canonical_json(item) for item in value]
        return value

    def test_contract_assertion_rejects_an_intentionally_changed_adapter_response(self) -> None:
        baseline = AdapterResponse(
            200,
            {"content-type": "application/json; charset=utf-8"},
            b'{"status":"ok"}',
        )
        changed = AdapterResponse(
            200,
            {"content-type": "application/json; charset=utf-8"},
            b'{"status":"changed"}',
        )

        with self.assertRaises(AssertionError):
            self.assert_parity(baseline, changed)

    @contextmanager
    def adapter_pair_from_fixture(self, fixture_path: Path, *, include_legacy_routes: bool = True):
        """Copy one completed SQLite fixture for each adapter under comparison."""
        with (
            TemporaryDirectory() as legacy_directory,
            TemporaryDirectory() as fastapi_directory,
        ):
            legacy_path = Path(legacy_directory) / fixture_path.name
            fastapi_path = Path(fastapi_directory) / fixture_path.name
            copy2(fixture_path, legacy_path)
            copy2(fixture_path, fastapi_path)
            with (
                LegacyAdapter(legacy_path) as legacy,
                FastAPIAdapter(
                    fastapi_path,
                    include_legacy_routes=include_legacy_routes,
                ) as fastapi,
            ):
                yield legacy, fastapi

    @contextmanager
    def adapter_pair(self, *, include_legacy_routes: bool = True):
        """Create both adapters from one seeded SQLite fixture.

        The demo seed stores creation timestamps.  Initializing two databases
        independently makes a read-only parity assertion depend on a boundary
        between wall-clock seconds, rather than on either adapter.
        """
        with TempDatabase() as fixture_path:
            with self.adapter_pair_from_fixture(
                fixture_path, include_legacy_routes=include_legacy_routes
            ) as adapters:
                yield adapters

    @contextmanager
    def confirmed_plan_adapter_pair(self):
        """Prepare dynamic confirmation timestamps once before splitting the fixture."""
        with TempDatabase() as fixture_path:
            with LegacyAdapter(fixture_path) as fixture:
                self.assertEqual(
                    201,
                    fixture.request("POST", "/api/planning-proposals", {"round_id": 1}).status,
                )
                self.assertEqual(
                    200, fixture.request("POST", "/api/exam-rounds/1/confirm-plan", {}).status
                )
            with self.adapter_pair_from_fixture(
                fixture_path, include_legacy_routes=False
            ) as adapters:
                yield adapters

    def test_shared_adapter_interface_covers_reads_writes_auth_and_errors(self) -> None:
        with self.subTest("representative cases"):
            with self.adapter_pair() as (legacy, fastapi):
                cases = (
                    ("health", "GET", "/api/health", None, False, None, {}),
                    ("readiness", "GET", "/api/ready", None, False, None, {}),
                    ("round summary", "GET", "/api/round-summary?round_id=1", None, True, None, {}),
                    ("unauthenticated", "GET", "/api/candidates", None, False, None, {}),
                    (
                        "invalid query",
                        "GET",
                        "/api/round-summary?round_id=invalid",
                        None,
                        True,
                        None,
                        {},
                    ),
                    (
                        "write",
                        "POST",
                        "/api/exam-half-years",
                        {"season": "summer", "year": 2030, "status": "draft"},
                        True,
                        None,
                        {},
                    ),
                )
                for name, method, path, payload, authenticated, credentials, headers in cases:
                    with self.subTest(name=name):
                        self.assert_parity(
                            legacy.request(
                                method,
                                path,
                                payload,
                                authenticated=authenticated,
                                credentials=credentials,
                                request_headers=headers,
                            ),
                            fastapi.request(
                                method,
                                path,
                                payload,
                                authenticated=authenticated,
                                credentials=credentials,
                                request_headers=headers,
                            ),
                        )

    def test_security_session_and_csrf_contracts_are_shared(self) -> None:
        allowed_origin = "https://app.example.invalid"
        with patch.object(TestLzugHandler, "cors_allowed_origins", frozenset({allowed_origin})):
            with self.adapter_pair() as (legacy, fastapi):
                for headers in (
                    {"Origin": allowed_origin},
                    {"Origin": "https://blocked.example.invalid"},
                    {"Origin": "https://app.example.invalid/"},
                    {"Origin": "https://user@app.example.invalid"},
                ):
                    with self.subTest(headers=headers):
                        self.assert_parity(
                            legacy.request(
                                "GET",
                                "/api/health",
                                authenticated=False,
                                request_headers=headers,
                            ),
                            fastapi.request(
                                "GET",
                                "/api/health",
                                authenticated=False,
                                request_headers=headers,
                            ),
                        )

                self.assert_parity(
                    legacy.request(
                        "OPTIONS",
                        "/api/auth/login",
                        authenticated=False,
                        request_headers={"Origin": allowed_origin},
                    ),
                    fastapi.request(
                        "OPTIONS",
                        "/api/auth/login",
                        authenticated=False,
                        request_headers={"Origin": allowed_origin},
                    ),
                )

                invalid_credentials = replace(
                    legacy.credentials,
                    csrf_token="invalid-csrf",
                )
                invalid_fastapi_credentials = replace(
                    fastapi.credentials,
                    csrf_token="invalid-csrf",
                )
                self.assert_parity(
                    legacy.request(
                        "POST",
                        "/api/exam-half-years",
                        {"season": "summer", "year": 2031, "status": "draft"},
                        credentials=invalid_credentials,
                    ),
                    fastapi.request(
                        "POST",
                        "/api/exam-half-years",
                        {"season": "summer", "year": 2031, "status": "draft"},
                        credentials=invalid_fastapi_credentials,
                    ),
                )

                legacy_session = legacy.request("POST", "/api/session/rotate")
                fastapi_session = fastapi.request("POST", "/api/session/rotate")
                self.assert_parity(
                    AdapterResponse(
                        legacy_session.status,
                        {
                            key: value
                            for key, value in legacy_session.headers.items()
                            if key != "set-cookie"
                        },
                        legacy_session.body,
                    ),
                    AdapterResponse(
                        fastapi_session.status,
                        {
                            key: value
                            for key, value in fastapi_session.headers.items()
                            if key != "set-cookie"
                        },
                        fastapi_session.body,
                    ),
                )
                self.assertIn("Max-Age=28800", legacy_session.headers.get("set-cookie", ""))
                self.assertIn("Max-Age=28800", fastapi_session.headers.get("set-cookie", ""))

    def test_body_size_content_type_and_error_contracts_are_shared(self) -> None:
        payload = {
            "email": "rate-limit@example.invalid",
            "password": "incorrect-password",
            "second_factor": "123456",
        }
        with patch.object(TestLzugHandler, "max_request_bytes", 32):
            with self.adapter_pair() as (legacy, fastapi):
                with self.subTest("body size"):
                    self.assert_parity(
                        legacy.request("POST", "/api/auth/login", payload, authenticated=False),
                        fastapi.request("POST", "/api/auth/login", payload, authenticated=False),
                    )

        with patch.object(TestLzugHandler, "max_request_bytes", 1024):
            with self.adapter_pair() as (legacy, fastapi):
                with self.subTest("content type"):
                    self.assert_parity(
                        legacy.request(
                            "POST",
                            "/api/auth/login",
                            payload,
                            authenticated=False,
                            request_headers={"Content-Type": "text/plain"},
                        ),
                        fastapi.request(
                            "POST",
                            "/api/auth/login",
                            payload,
                            authenticated=False,
                            request_headers={"Content-Type": "text/plain"},
                        ),
                    )
                with self.subTest("malformed JSON"):
                    self.assert_parity(
                        legacy.request(
                            "POST",
                            "/api/auth/login",
                            authenticated=False,
                            request_headers={"Content-Type": "application/json"},
                            raw_body=b"{malformed",
                        ),
                        fastapi.request(
                            "POST",
                            "/api/auth/login",
                            authenticated=False,
                            request_headers={"Content-Type": "application/json"},
                            raw_body=b"{malformed",
                        ),
                    )

                with self.subTest("transfer encoding"):
                    self.assert_parity(
                        legacy.request(
                            "POST",
                            "/api/auth/login",
                            authenticated=False,
                            request_headers={
                                "Content-Type": "application/json",
                                "Transfer-Encoding": "chunked",
                            },
                            raw_body=b"{}",
                        ),
                        fastapi.request(
                            "POST",
                            "/api/auth/login",
                            authenticated=False,
                            request_headers={
                                "Content-Type": "application/json",
                                "Transfer-Encoding": "chunked",
                            },
                            raw_body=b"{}",
                        ),
                    )

    def test_static_openapi_and_spa_contracts_are_structurally_compared(self) -> None:
        with TemporaryDirectory() as directory:
            static_dir = Path(directory)
            (static_dir / "index.html").write_text("<app-root>shell</app-root>", encoding="utf-8")
            (static_dir / "main.123.js").write_text("console.log('ok')", encoding="utf-8")
            with patch.object(TestLzugHandler, "static_dir", static_dir):
                with self.adapter_pair() as (legacy, fastapi):
                    for path in ("/dashboard", "/main.123.js"):
                        with self.subTest(path=path):
                            self.assert_parity(
                                legacy.request("GET", path, authenticated=False),
                                fastapi.request("GET", path, authenticated=False),
                            )

                    legacy_openapi = legacy.request("GET", "/api/openapi.json")
                    fastapi_openapi = fastapi.request("GET", "/api/openapi.json")
                    self.assert_parity(legacy_openapi, fastapi_openapi)
                    self.assertEqual(
                        json.loads(legacy_openapi.body),
                        json.loads(fastapi_openapi.body),
                    )

    def test_migrated_routes_do_not_depend_on_the_legacy_fallback(self) -> None:
        """Exercise #474 routes with the FastAPI catch-all deliberately absent."""
        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
            cases = (
                ("GET", "/api", None, True, None, {}),
                ("GET", "/api/openapi.json", None, True, None, {}),
                ("GET", "/api/docs", None, True, None, {}),
                ("GET", "/api/session", None, True, None, {}),
                (
                    "POST",
                    "/api/auth/login",
                    {"email": "unknown@example.invalid", "password": "wrong"},
                    False,
                    None,
                    {},
                ),
                ("POST", "/api/auth/invitation/prepare", {"token": "invalid"}, False, None, {}),
                ("POST", "/api/auth/recovery/prepare", {"token": "invalid"}, False, None, {}),
                ("POST", "/api/session/rotate", None, True, None, {}),
                (
                    "POST",
                    "/api/observability/frontend-errors",
                    {"kind": "http", "status": 503},
                    False,
                    None,
                    {
                        "Host": "127.0.0.1",
                        "Origin": "http://127.0.0.1",
                        "Sec-Fetch-Site": "same-origin",
                    },
                ),
            )
            for method, path, payload, authenticated, credentials, headers in cases:
                with self.subTest(method=method, path=path):
                    self.assert_parity(
                        legacy.request(
                            method,
                            path,
                            payload,
                            authenticated=authenticated,
                            credentials=credentials,
                            request_headers=headers,
                        ),
                        fastapi.request(
                            method,
                            path,
                            payload,
                            authenticated=authenticated,
                            credentials=credentials,
                            request_headers=headers,
                        ),
                    )

    def test_domain_routes_do_not_depend_on_the_legacy_fallback(self) -> None:
        """Exercise the #475 domain inventory with the catch-all deliberately absent."""
        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
            for resource_name in MIGRATED_DOMAIN_RESOURCES:
                path = f"/api/{resource_name}"
                if resource_name == "round-candidates":
                    path += "?round_id=1"
                with self.subTest(method="GET", path=path):
                    self.assert_parity(
                        legacy.request("GET", path),
                        fastapi.request("GET", path),
                    )

            for path in (
                "/api/candidate-committee-assignments?candidate_id=1",
                "/api/candidate-committee-assignments/1",
            ):
                with self.subTest(method="GET", path=path):
                    self.assert_parity(
                        legacy.request("GET", path),
                        fastapi.request("GET", path),
                    )

            for method, path, payload in (
                (
                    "POST",
                    "/api/exam-half-years",
                    {"season": "summer", "year": 2030, "status": "draft"},
                ),
                ("PATCH", "/api/exam-half-years/1", {"status": "active"}),
                ("DELETE", "/api/exam-half-years/1", None),
            ):
                self.assert_parity(
                    legacy.request(method, path, payload),
                    fastapi.request(method, path, payload),
                )

    def test_planning_routes_do_not_depend_on_the_legacy_fallback(self) -> None:
        """Keep #476's aggregate, revision, execution, and demo paths dual-adapter safe."""
        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):

            def request(method, path, payload=None):
                legacy_response = legacy.request(method, path, payload)
                fastapi_response = fastapi.request(method, path, payload)
                self.assert_parity(legacy_response, fastapi_response)
                return legacy_response

            for path in (
                "/api/scheduling-overview",
                "/api/confirmed-plans",
                "/api/confirmed-plan-days/999999",
                *(f"/api/{resource_name}" for resource_name in MIGRATED_PLANNING_RESOURCES),
            ):
                with self.subTest(method="GET", path=path):
                    request("GET", path)

            generated = request("POST", "/api/planning-proposals", {"round_id": 1})
            self.assertEqual(201, generated.status)
            proposal = request("GET", "/api/exam-rounds/1/planning-proposal").json
            stale = deepcopy(proposal)
            saved = request("PUT", "/api/exam-rounds/1/planning-proposal", proposal)
            self.assertEqual(200, saved.status)
            request("PUT", "/api/exam-rounds/1/planning-proposal", stale)

            invalid = deepcopy(saved.json)
            invalid["exam_days"][0]["slots"][0]["round_candidate_id"] = invalid["exam_days"][0][
                "slots"
            ][1]["round_candidate_id"]
            request("PUT", "/api/exam-rounds/1/planning-proposal", invalid)

            request("POST", "/api/exam-rounds/1/confirm-plan", {})

        with self.confirmed_plan_adapter_pair() as (legacy, fastapi):

            def request(method, path, payload=None):
                legacy_response = legacy.request(method, path, payload)
                fastapi_response = fastapi.request(method, path, payload)
                self.assert_parity(legacy_response, fastapi_response)
                return legacy_response

            calendar = request("GET", "/api/confirmed-plans").json
            day = calendar["items"][0]["days"][0]
            slot = day["slots"][0]
            request("GET", f"/api/confirmed-plan-days/{day['id']}")
            request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/attendance",
                {"status": "late"},
            )
            request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/attendance",
                {"status": "present", "arrived_at": "2026-11-16T08:24:00+01:00"},
            )
            for assignment in (
                item
                for item in day["assignments"]
                if item["assignment_role"] == "examiner" and item["day_part"] == "morning"
            ):
                request(
                    "PATCH",
                    f"/api/confirmed-plan-days/{day['id']}/assignments/{assignment['id']}/attendance",
                    {"status": "present", "arrived_at": "2026-11-16T08:10:00+01:00"},
                )
            request(
                "POST",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/start",
                {"actual_started_at": "2026-11-16T08:31:00+01:00"},
            )
            request(
                "PATCH",
                f"/api/confirmed-plan-days/{day['id']}/slots/{slot['id']}/status",
                {"status": "needs_follow_up"},
            )

    def test_integration_routes_do_not_depend_on_the_legacy_fallback(self) -> None:
        """Keep #477's notification, calendar, and absence routes dual-adapter safe."""
        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
            for method, path, payload in (
                ("GET", "/api/notifications", None),
                ("GET", "/api/notification-problems", None),
                ("GET", "/api/notification-overview", None),
                ("GET", "/api/notification-channels", None),
                ("GET", "/api/calendar", None),
                ("GET", "/api/calendar/feed", None),
                ("GET", "/api/calendar/events", None),
                ("GET", "/api/calendar/events/999999.ics", None),
                ("POST", "/api/calendar/feed", {}),
                ("DELETE", "/api/calendar/feed", None),
                ("POST", "/api/push-subscriptions", {"endpoint": "https://push.example.invalid"}),
                ("DELETE", "/api/push-subscriptions/999999", None),
                ("POST", "/api/notifications/999999/push-confirmation", None),
                ("GET", "/api/absence-reports", None),
                ("GET", "/api/absence-reports/999999", None),
                ("POST", "/api/absence-reports", {}),
                ("POST", "/api/absence-reports/999999/select-replacement", {}),
                ("POST", "/api/absence-reports/999999/withdraw", None),
                ("POST", "/api/absence-reports/999999/reopen", {}),
                ("POST", "/api/absence-reports/999999/cancel", {}),
                ("PATCH", "/api/replacement-responses/999999", {}),
                ("POST", "/api/replacement-responses/999999/respond", {}),
            ):
                with self.subTest(method=method, path=path):
                    self.assert_parity(
                        legacy.request(method, path, payload),
                        fastapi.request(method, path, payload),
                    )

        with self.confirmed_plan_adapter_pair() as (legacy, fastapi):
            legacy_activation = legacy.request("POST", "/api/calendar/feed", {})
            fastapi_activation = fastapi.request("POST", "/api/calendar/feed", {})
            self.assertEqual(201, legacy_activation.status)
            self.assert_parity(legacy_activation, fastapi_activation)
            legacy_feed_path = legacy_activation.json["feed_url"].replace(
                "https://app.example.invalid", ""
            )
            fastapi_feed_path = fastapi_activation.json["feed_url"].replace(
                "https://app.example.invalid", ""
            )
            with patch("backend.calendar._now", return_value=datetime(2026, 1, 1, tzinfo=UTC)):
                self.assert_parity(
                    legacy.request("GET", legacy_feed_path, authenticated=False),
                    fastapi.request("GET", fastapi_feed_path, authenticated=False),
                )

    def test_candidate_day_generation_and_planning_failures_keep_adapter_parity(self) -> None:
        """Cover the candidate-day action plus large-body and database failure boundaries."""
        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
            settings = {
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
            }
            self.assert_parity(
                legacy.request("POST", "/api/planning-settings", settings),
                fastapi.request("POST", "/api/planning-settings", settings),
            )
            self.assert_parity(
                legacy.request("POST", "/api/candidate-exam-days/generate", {"round_id": 1}),
                fastapi.request("POST", "/api/candidate-exam-days/generate", {"round_id": 1}),
            )

        with patch.object(TestLzugHandler, "max_request_bytes", 32):
            with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
                payload = {"round_id": 1, "padding": "x" * 100}
                self.assert_parity(
                    legacy.request("POST", "/api/planning-proposals", payload),
                    fastapi.request("POST", "/api/planning-proposals", payload),
                )

        with self.adapter_pair(include_legacy_routes=False) as (legacy, fastapi):
            with patch(
                "backend.repositories.ResourceRepository.confirmed_plans",
                side_effect=SQLAlchemyError("private database details"),
            ):
                self.assert_parity(
                    legacy.request("GET", "/api/confirmed-plans"),
                    fastapi.request("GET", "/api/confirmed-plans"),
                )


if __name__ == "__main__":
    unittest.main()
