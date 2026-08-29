from __future__ import annotations

import inspect
import os
import unittest
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.application import ApplicationServices
from backend.auth import AuthenticationRepository, SessionCredentials
from backend.fastapi_app import (
    MIGRATED_DOMAIN_RESOURCES,
    MIGRATED_PLANNING_RESOURCES,
    FastAPIConfig,
    create_app,
)
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler


class FastAPIApplicationTests(unittest.TestCase):
    def config(self, db_path: Path) -> FastAPIConfig:
        return FastAPIConfig(
            db_path=db_path,
            session_cookie_name=TestLzugHandler.session_cookie_name,
        )

    def fastapi_get(
        self,
        client: TestClient,
        path: str,
        credentials: SessionCredentials | None = None,
    ) -> tuple[int, dict]:
        headers = {}
        if credentials is not None:
            headers["Cookie"] = f"{TestLzugHandler.session_cookie_name}={credentials.token}"
        response = client.get(path, headers=headers)
        return response.status_code, response.json()

    def test_environment_configuration_uses_existing_database_and_cookie_contract(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "configured.sqlite"
            with patch.dict(
                os.environ,
                {
                    "LZUG_DATABASE_PATH": str(db_path),
                    "LZUG_HTTPS_ONLY": "false",
                },
                clear=True,
            ):
                local_config = FastAPIConfig.from_environment()
            self.assertEqual(db_path, local_config.db_path)
            self.assertEqual("lzug_session", local_config.session_cookie_name)

            with patch.dict(
                os.environ,
                {"LZUG_DATABASE_PATH": str(db_path), "LZUG_HTTPS_ONLY": "true"},
                clear=True,
            ):
                secure_config = FastAPIConfig.from_environment()
            self.assertEqual("__Host-lzug_session", secure_config.session_cookie_name)

    def test_health_and_readiness_match_existing_adapter(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "uninitialized.sqlite"
            with ApiServer(db_path) as existing:
                expected_health = existing.request("GET", "/api/health", authenticated=False)
                expected_readiness = existing.request("GET", "/api/ready", authenticated=False)
            with TestClient(create_app(self.config(db_path))) as client:
                self.assertEqual(expected_health, self.fastapi_get(client, "/api/health"))
                self.assertEqual(expected_readiness, self.fastapi_get(client, "/api/ready"))

        with TempDatabase() as db_path, ApiServer(db_path) as existing:
            expected_health = existing.request("GET", "/api/health", authenticated=False)
            expected_readiness = existing.request("GET", "/api/ready", authenticated=False)
            with TestClient(create_app(self.config(db_path))) as client:
                self.assertEqual(expected_health, self.fastapi_get(client, "/api/health"))
                self.assertEqual(expected_readiness, self.fastapi_get(client, "/api/ready"))

    def test_health_is_pure_liveness_and_ready_uses_injected_probe(self) -> None:
        readiness_probe = Mock(return_value={"ready": False})
        services = replace(ApplicationServices(), readiness_probe=readiness_probe)
        with (
            TempDatabase() as db_path,
            TestClient(create_app(self.config(db_path), services)) as client,
        ):
            status, health = self.fastapi_get(client, "/api/health")
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual("ok", health["status"])
            readiness_probe.assert_not_called()

            status, readiness = self.fastapi_get(client, "/api/ready")
            self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, status)
            self.assertEqual("unavailable", readiness["status"])
            readiness_probe.assert_called_once_with(db_path)

    def test_round_summary_matches_authentication_and_committee_contract(self) -> None:
        with TempDatabase() as db_path:
            authentication = AuthenticationRepository(db_path)
            chair = authentication.create_session(1)
            examiner = authentication.create_session(2)
            operator_account = authentication.create_account(
                "operator@example.invalid", is_operator=True
            )
            operator = authentication.create_session(operator_account["id"])

            with (
                ApiServer(db_path) as existing,
                TestClient(create_app(self.config(db_path))) as client,
            ):
                for credentials in (chair, examiner):
                    expected = existing.request(
                        "GET",
                        "/api/round-summary?round_id=1",
                        credentials=credentials,
                    )
                    self.assertEqual(
                        expected,
                        self.fastapi_get(
                            client,
                            "/api/round-summary?round_id=1",
                            credentials,
                        ),
                    )

                expected = existing.request(
                    "GET",
                    "/api/round-summary?round_id=1",
                    authenticated=False,
                )
                self.assertEqual(
                    expected,
                    self.fastapi_get(client, "/api/round-summary?round_id=1"),
                )

                expected = existing.request(
                    "GET",
                    "/api/round-summary?round_id=1",
                    credentials=operator,
                )
                self.assertEqual(
                    expected,
                    self.fastapi_get(
                        client,
                        "/api/round-summary?round_id=1",
                        operator,
                    ),
                )

                expected = existing.request(
                    "GET",
                    "/api/round-summary?round_id=invalid",
                    credentials=chair,
                )
                self.assertEqual(
                    expected,
                    self.fastapi_get(
                        client,
                        "/api/round-summary?round_id=invalid",
                        chair,
                    ),
                )

    def test_migration_routes_are_synchronous(self) -> None:
        with TempDatabase() as db_path:
            app = create_app(self.config(db_path))

        endpoints = {
            route.path: route.endpoint for route in app.routes if isinstance(route, APIRoute)
        }
        expected = {
            "/api",
            "/api/auth/invitation/activate",
            "/api/auth/invitation/prepare",
            "/api/auth/login",
            "/api/auth/recovery/complete",
            "/api/auth/recovery/prepare",
            "/api/docs",
            "/api/health",
            "/api/observability/frontend-errors",
            "/api/openapi.json",
            "/api/ready",
            "/api/round-summary",
            "/api/session",
            "/api/session/logout",
            "/api/session/rotate",
        }
        for resource_name in MIGRATED_DOMAIN_RESOURCES:
            expected.update({f"/api/{resource_name}", f"/api/{resource_name}/{{id}}"})
        for resource_name in MIGRATED_PLANNING_RESOURCES:
            expected.update({f"/api/{resource_name}", f"/api/{resource_name}/{{id}}"})
        expected.update(
            {
                "/api/candidate-committee-assignments",
                "/api/candidate-committee-assignments/{id}",
                "/api/scheduling-overview",
                "/api/confirmed-plans",
                "/api/confirmed-plan-days/{id}",
                "/api/planning-proposals",
                "/api/candidate-exam-days/generate",
                "/api/exam-rounds/{id}/planning-proposal",
                "/api/exam-rounds/{id}/confirm-plan",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
                "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
                "/api/notifications",
                "/api/notification-problems",
                "/api/notification-overview",
                "/api/notification-channels",
                "/api/calendar",
                "/api/calendar/feed",
                "/api/calendar/feed/{token}.ics",
                "/api/calendar/events",
                "/api/calendar/events/{id}.ics",
                "/api/push-subscriptions",
                "/api/push-subscriptions/{id}",
                "/api/notifications/{id}/push-confirmation",
                "/api/absence-reports",
                "/api/absence-reports/{id}",
                "/api/absence-reports/{report_id}/select-replacement",
                "/api/absence-reports/{report_id}/withdraw",
                "/api/absence-reports/{report_id}/reopen",
                "/api/absence-reports/{report_id}/cancel",
                "/api/replacement-responses/{response_id}",
                "/api/replacement-responses/{response_id}/respond",
            }
        )
        self.assertTrue(expected <= set(endpoints))
        self.assertTrue(
            all(not inspect.iscoroutinefunction(endpoint) for endpoint in endpoints.values())
        )

    def test_migrated_openapi_fragments_are_generated_from_fastapi_routes(self) -> None:
        """Ensure the documented API surface is generated by FastAPI."""
        with TempDatabase() as db_path:
            generated = create_app(self.config(db_path)).openapi()
        migrated = {
            "/api",
            "/api/auth/invitation/activate",
            "/api/auth/invitation/prepare",
            "/api/auth/login",
            "/api/auth/recovery/complete",
            "/api/auth/recovery/prepare",
            "/api/docs",
            "/api/health",
            "/api/observability/frontend-errors",
            "/api/openapi.json",
            "/api/ready",
            "/api/round-summary",
            "/api/session",
            "/api/session/logout",
            "/api/session/rotate",
        }
        for resource_name in MIGRATED_DOMAIN_RESOURCES:
            migrated.update({f"/api/{resource_name}", f"/api/{resource_name}/{{id}}"})
        for resource_name in MIGRATED_PLANNING_RESOURCES:
            migrated.update({f"/api/{resource_name}", f"/api/{resource_name}/{{id}}"})
        migrated.update(
            {
                "/api/candidate-committee-assignments",
                "/api/candidate-committee-assignments/{id}",
                "/api/scheduling-overview",
                "/api/confirmed-plans",
                "/api/confirmed-plan-days/{id}",
                "/api/planning-proposals",
                "/api/candidate-exam-days/generate",
                "/api/exam-rounds/{id}/planning-proposal",
                "/api/exam-rounds/{id}/confirm-plan",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
                "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
                "/api/notifications",
                "/api/notification-problems",
                "/api/notification-overview",
                "/api/notification-channels",
                "/api/calendar",
                "/api/calendar/feed",
                "/api/calendar/feed/{token}.ics",
                "/api/calendar/events",
                "/api/calendar/events/{id}.ics",
                "/api/push-subscriptions",
                "/api/push-subscriptions/{id}",
                "/api/notifications/{id}/push-confirmation",
                "/api/absence-reports",
                "/api/absence-reports/{id}",
                "/api/absence-reports/{report_id}/select-replacement",
                "/api/absence-reports/{report_id}/withdraw",
                "/api/absence-reports/{report_id}/reopen",
                "/api/absence-reports/{report_id}/cancel",
                "/api/replacement-responses/{response_id}",
                "/api/replacement-responses/{response_id}/respond",
            }
        )
        undocumented_runtime_paths = {
            "/api/docs",
            "/api/calendar/feed/{token}.ics",
            "/api/calendar/events/{id}.ics",
        }
        self.assertTrue(migrated - undocumented_runtime_paths <= set(generated["paths"]))
        self.assertEqual("3.1.0", generated["openapi"])
        self.assertEqual(
            [{"sessionCookie": [], "csrfHeader": []}],
            generated["paths"]["/api/candidates"]["post"]["security"],
        )


if __name__ == "__main__":
    unittest.main()
