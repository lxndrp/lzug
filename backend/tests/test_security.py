from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from http import HTTPStatus
from unittest.mock import patch

from backend.observability import emit_event
from backend.security import RequestRateLimiter, RuntimeSecurityConfig
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler, assert_status


class LoggingHandler(TestLzugHandler):
    pass


class RuntimeSecurityConfigurationTests(unittest.TestCase):
    def test_defaults_are_fail_closed(self) -> None:
        config = RuntimeSecurityConfig.from_environment({})

        self.assertTrue(config.https_only)
        self.assertEqual(frozenset(), config.cors_allowed_origins)
        self.assertEqual(timedelta(hours=8), config.session_ttl)
        self.assertEqual(1024 * 1024, config.max_request_bytes)

    def test_explicit_origins_and_local_http_mode_are_validated(self) -> None:
        config = RuntimeSecurityConfig.from_environment(
            {
                "LZUG_HTTPS_ONLY": "false",
                "LZUG_CORS_ALLOWED_ORIGINS": "https://example.invalid,http://localhost:4200",
                "LZUG_SESSION_TTL_SECONDS": "600",
            }
        )

        self.assertFalse(config.https_only)
        self.assertEqual(600, int(config.session_ttl.total_seconds()))
        self.assertEqual(
            frozenset({"https://example.invalid", "http://localhost:4200"}),
            config.cors_allowed_origins,
        )

        for invalid in (
            "*",
            "https://example.invalid/",
            "https://user@example.invalid",
            "https://example.invalid:not-a-port",
            "https://[invalid",
            "https://example.invalid\r\nX-Injected: true",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "exact HTTP origins"):
                    RuntimeSecurityConfig.from_environment({"LZUG_CORS_ALLOWED_ORIGINS": invalid})

    def test_rate_limiter_has_a_deterministic_negative_case(self) -> None:
        limiter = RequestRateLimiter(2, timedelta(seconds=10))

        self.assertIsNone(limiter.check("client", now=100.0))
        self.assertIsNone(limiter.check("client", now=101.0))
        self.assertEqual(9, limiter.check("client", now=101.5))
        self.assertIsNone(limiter.check("client", now=111.0))


class HttpSecurityTests(unittest.TestCase):
    def test_unhandled_server_errors_emit_no_exception_or_client_details(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            emit_event("backend_error", severity="error", category="unhandled_request", status=500)

        event = json.loads(output.getvalue())
        self.assertEqual("backend_error", event["event"])
        self.assertEqual("unhandled_request", event["category"])
        self.assertNotIn("192.0.2.1", output.getvalue())

    def test_operational_signals_and_required_auth_flows_are_public_boundaries(
        self,
    ) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, health = api.request("GET", "/api/health", authenticated=False)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("ok", health["status"])
            self.assertNotIn("candidate", str(health).lower())

            status, readiness = api.request("GET", "/api/ready", authenticated=False)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("ready", readiness["status"])

            for path in ("/api", "/api/openapi.json", "/api/docs", "/api/candidates"):
                with self.subTest(path=path):
                    status, error = api.request("GET", path, authenticated=False)
                    assert_status(status, HTTPStatus.UNAUTHORIZED)
                    self.assertEqual("Authentication required.", error["error"])

    def test_security_headers_and_exact_cors_allowlist_are_applied(self) -> None:
        allowed_origin = "https://app.example.invalid"
        with (
            patch.object(TestLzugHandler, "cors_allowed_origins", frozenset({allowed_origin})),
            TempDatabase() as db_path,
            ApiServer(db_path) as api,
        ):
            status, headers, _body = api.request_raw(
                "GET",
                "/api/health",
                authenticated=False,
                request_headers={"Origin": allowed_origin},
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(allowed_origin, headers["access-control-allow-origin"])
            self.assertEqual("true", headers["access-control-allow-credentials"])
            self.assertEqual("DENY", headers["x-frame-options"])
            self.assertEqual("nosniff", headers["x-content-type-options"])
            self.assertEqual("no-referrer", headers["referrer-policy"])
            self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
            self.assertIn("max-age=31536000", headers["strict-transport-security"])

            status, headers, _body = api.request_raw(
                "OPTIONS",
                "/api/auth/login",
                authenticated=False,
                request_headers={"Origin": allowed_origin},
            )
            assert_status(status, HTTPStatus.NO_CONTENT)
            self.assertIn("X-CSRF-Token", headers["access-control-allow-headers"])

            status, error = api.request(
                "GET",
                "/api/health",
                authenticated=False,
                request_headers={"Origin": "https://blocked.example.invalid"},
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Cross-origin request is not allowed.", error["error"])

    def test_same_origin_normalizes_default_ports_and_rejects_malformed_hosts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, headers, _body = api.request_raw(
                "GET",
                "/api/health",
                authenticated=False,
                request_headers={
                    "Host": "app.example.invalid:443",
                    "Origin": "https://app.example.invalid",
                },
            )
            assert_status(status, HTTPStatus.OK)
            self.assertNotIn("access-control-allow-origin", headers)

            for malformed_host in ("app.example.invalid:not-a-port", "[invalid"):
                with self.subTest(malformed_host=malformed_host):
                    status, error = api.request(
                        "GET",
                        "/api/health",
                        authenticated=False,
                        request_headers={
                            "Host": malformed_host,
                            "Origin": "https://app.example.invalid",
                        },
                    )
                    assert_status(status, HTTPStatus.FORBIDDEN)
                    self.assertEqual("Cross-origin request is not allowed.", error["error"])

    def test_json_body_type_size_and_public_auth_rate_limit_are_enforced(self) -> None:
        payload = {
            "email": "rate-limit@example.invalid",
            "password": "incorrect-password",
            "second_factor": "123456",
        }
        limiter = RequestRateLimiter(1, timedelta(minutes=1))
        with (
            patch.object(TestLzugHandler, "max_request_bytes", 32),
            patch.object(TestLzugHandler, "auth_rate_limiter", limiter),
            TempDatabase() as db_path,
            ApiServer(db_path) as api,
        ):
            status, error = api.request("POST", "/api/auth/login", payload, authenticated=False)
            assert_status(status, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            self.assertIn("exceeds 32 bytes", error["error"])

        limiter = RequestRateLimiter(1, timedelta(minutes=1))
        with (
            patch.object(TestLzugHandler, "max_request_bytes", 1024),
            patch.object(TestLzugHandler, "auth_rate_limiter", limiter),
            TempDatabase() as db_path,
            ApiServer(db_path) as api,
        ):
            status, error = api.request(
                "POST",
                "/api/auth/login",
                payload,
                authenticated=False,
                request_headers={"Content-Type": "text/plain"},
            )
            assert_status(status, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            self.assertEqual("Content-Type must be application/json.", error["error"])

            status, _error = api.request("POST", "/api/auth/login", payload, authenticated=False)
            assert_status(status, HTTPStatus.TOO_MANY_REQUESTS)

    def test_session_cookie_lifetime_matches_the_server_session(self) -> None:
        with (
            patch.object(TestLzugHandler, "session_ttl", timedelta(minutes=10)),
            TempDatabase() as db_path,
            ApiServer(db_path) as api,
        ):
            status, headers, _body = api.request_raw("POST", "/api/session/rotate")

        assert_status(status, HTTPStatus.OK)
        self.assertIn("Max-Age=600", headers["set-cookie"])
        self.assertIn("SameSite=Strict", headers["set-cookie"])
        self.assertIn("Secure", headers["set-cookie"])

    def test_access_log_omits_client_query_cookie_and_request_body(self) -> None:
        secret_marker = "do-not-log-this-token"
        output = io.StringIO()
        with (
            TempDatabase() as db_path,
            redirect_stdout(output),
            ApiServer(db_path, LoggingHandler) as api,
        ):
            status, _headers, _body = api.request_raw(
                "GET",
                f"/api/health?token={secret_marker}",
                authenticated=False,
                request_headers={"Cookie": f"session={secret_marker}"},
            )

        assert_status(status, HTTPStatus.OK)
        logged = output.getvalue()
        entries = [json.loads(line) for line in logged.splitlines()]
        self.assertIn(
            {
                "bytes": 0,
                "deployment_digest": "unknown",
                "event": "http_request",
                "method": "GET",
                "path": "/api/health",
                "status": 200,
            },
            entries,
        )
        self.assertNotIn(secret_marker, logged)
        self.assertNotIn("127.0.0.1", logged)

    def test_frontend_error_signal_rejects_details_and_logs_only_classification(self) -> None:
        output = io.StringIO()
        with (
            TempDatabase() as db_path,
            redirect_stdout(output),
            ApiServer(db_path, LoggingHandler) as api,
        ):
            status, _headers, body = api.request_raw(
                "POST",
                "/api/observability/frontend-errors",
                {"kind": "http", "status": 503},
                authenticated=False,
                request_headers={
                    "Origin": "http://127.0.0.1",
                    "Sec-Fetch-Site": "same-origin",
                },
            )
            assert_status(status, HTTPStatus.ACCEPTED)
            self.assertEqual(b"{}", body.replace(b"\n", b"").replace(b" ", b""))

            rejected, response = api.request(
                "POST",
                "/api/observability/frontend-errors",
                {"kind": "runtime", "message": "person@example.invalid secret"},
                authenticated=False,
                request_headers={
                    "Origin": "http://127.0.0.1",
                    "Sec-Fetch-Site": "same-origin",
                },
            )

        assert_status(rejected, HTTPStatus.BAD_REQUEST)
        self.assertEqual("Invalid frontend error fields", response["error"])
        logged = output.getvalue()
        self.assertIn('"event":"frontend_error"', logged)
        self.assertIn('"kind":"http"', logged)
        self.assertNotIn("person@example.invalid", logged)
        self.assertNotIn("secret", logged)

    def test_frontend_error_signal_is_not_an_unbound_public_log_sink(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            for headers in (
                {},
                {"Origin": "http://127.0.0.1"},
                {
                    "Origin": "https://attacker.example.invalid",
                    "Sec-Fetch-Site": "cross-site",
                },
            ):
                with self.subTest(headers=headers):
                    status, error = api.request(
                        "POST",
                        "/api/observability/frontend-errors",
                        {"kind": "runtime"},
                        authenticated=False,
                        request_headers=headers,
                    )
                    assert_status(status, HTTPStatus.FORBIDDEN)
                    self.assertIn(
                        error["error"],
                        {"Forbidden.", "Cross-origin request is not allowed."},
                    )


if __name__ == "__main__":
    unittest.main()
