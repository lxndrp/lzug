from __future__ import annotations

import unittest
from http import HTTPStatus

from backend.e2e_server import E2EHandler
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class TestE2EHandler(E2EHandler):
    def log_message(self, format: str, *args) -> None:
        pass


class E2EServerTests(unittest.TestCase):
    def test_reset_endpoint_restores_the_seeded_database(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _candidate = api.request(
                "PATCH",
                "/api/candidates/1",
                {"exam_number": "E2E-RESET-001"},
            )
            assert_status(status, HTTPStatus.OK)

            with ApiServer(db_path, TestE2EHandler) as e2e_api:
                status, response = e2e_api.request("POST", "/__e2e/reset")

            assert_status(status, HTTPStatus.OK)
            self.assertEqual({"status": "reset"}, response)

            status, candidates = api.request("GET", "/api/candidates")
            assert_status(status, HTTPStatus.OK)
            self.assertNotIn(
                "E2E-RESET-001",
                [candidate["ihk_exam_number"] for candidate in candidates["items"]],
            )
