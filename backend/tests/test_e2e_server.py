from __future__ import annotations

import unittest
from datetime import timedelta
from http import HTTPStatus

from fastapi.testclient import TestClient

from backend.auth import AuthenticationRepository
from backend.e2e_server import create_e2e_app
from backend.fastapi_app import FastAPIConfig
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class E2EServerTests(unittest.TestCase):
    def test_reset_endpoint_restores_the_seeded_database(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _candidate = api.request(
                "PATCH",
                "/api/candidates/1",
                {"exam_number": "E2E-RESET-001"},
            )
            assert_status(status, HTTPStatus.OK)

            config = FastAPIConfig(
                db_path=db_path,
                session_cookie_name="lzug_e2e_session",
                cookie_secure=False,
                https_only=False,
                session_ttl=timedelta(hours=1),
            )
            with TestClient(create_e2e_app(config)) as e2e_api:
                reset = e2e_api.post("/__e2e/reset")
                status, response = reset.status_code, reset.json()

            assert_status(status, HTTPStatus.OK)
            self.assertEqual({"status": "reset"}, response)

            api.credentials = AuthenticationRepository(db_path).create_session(1)
            status, candidates = api.request("GET", "/api/candidates")
            assert_status(status, HTTPStatus.OK)
            self.assertNotIn(
                "E2E-RESET-001",
                [candidate["ihk_exam_number"] for candidate in candidates["items"]],
            )
