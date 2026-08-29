from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.fastapi_app import MIGRATED_DOMAIN_RESOURCES
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
                    if key in {"created_at", "expires_at", "updated_at"}
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
    def adapter_pair(self, *, include_legacy_routes: bool = True):
        """Create both adapters from one seeded SQLite fixture.

        The demo seed stores creation timestamps.  Initializing two databases
        independently makes a read-only parity assertion depend on a boundary
        between wall-clock seconds, rather than on either adapter.
        """
        with TempDatabase() as legacy_path, TemporaryDirectory() as directory:
            fastapi_path = Path(directory) / legacy_path.name
            copy2(legacy_path, fastapi_path)
            with (
                LegacyAdapter(legacy_path) as legacy,
                FastAPIAdapter(
                    fastapi_path,
                    include_legacy_routes=include_legacy_routes,
                ) as fastapi,
            ):
                yield legacy, fastapi

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

            created = legacy.request(
                "POST",
                "/api/exam-half-years",
                {"season": "summer", "year": 2030, "status": "draft"},
            )
            fastapi_created = fastapi.request(
                "POST",
                "/api/exam-half-years",
                {"season": "summer", "year": 2030, "status": "draft"},
            )
            self.assert_parity(created, fastapi_created)
            half_year_id = created.json["id"]

            updated = legacy.request(
                "PATCH",
                f"/api/exam-half-years/{half_year_id}",
                {"status": "active"},
            )
            fastapi_updated = fastapi.request(
                "PATCH",
                f"/api/exam-half-years/{half_year_id}",
                {"status": "active"},
            )
            self.assert_parity(updated, fastapi_updated)

            self.assert_parity(
                legacy.request("DELETE", f"/api/exam-half-years/{half_year_id}"),
                fastapi.request("DELETE", f"/api/exam-half-years/{half_year_id}"),
            )


if __name__ == "__main__":
    unittest.main()
