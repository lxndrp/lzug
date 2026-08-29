from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path

from backend.auth import AuthenticationRepository
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler, assert_status
from demo.contract import RUNTIME_CONTRACT, canonical_digest, demo_identity
from demo.runtime_policy import DemoRuntimePolicy


class DemoTestHandler(TestLzugHandler):
    forced_session_ttl = timedelta(minutes=60)


class DemoRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        app_manifest = root / "app.json"
        seed_manifest = root / "seed.json"
        product = demo_identity("v0.1.1", "a" * 40).product
        schema = {"fingerprint": "b" * 64}
        seed_binding = {
            "manifest_version": 1,
            "runtime_contract": RUNTIME_CONTRACT,
            "product": product,
            "schema": schema,
        }
        self.seed_revision = canonical_digest(seed_binding)
        app_manifest.write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "runtime_contract": RUNTIME_CONTRACT,
                    "product": product,
                    "schema": schema,
                    "seed_revision": self.seed_revision,
                }
            ),
            encoding="utf-8",
        )
        seed_manifest.write_text(
            json.dumps(
                {
                    **seed_binding,
                    "seed_revision": self.seed_revision,
                }
            ),
            encoding="utf-8",
        )
        (root / "demo-runtime-status.json").write_text(
            json.dumps(
                {
                    "initialized": True,
                    "initialization_status": "ready",
                    "initialized_at": "2026-08-14T01:00:00+00:00",
                    "last_reset_at": "2026-08-14T01:00:00+00:00",
                    "seed_revision": self.seed_revision,
                }
            ),
            encoding="utf-8",
        )
        DemoTestHandler.runtime_policy = DemoRuntimePolicy(app_manifest, seed_manifest)
        DemoTestHandler.session_ttl = timedelta(minutes=60)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_public_status_and_role_sessions(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path, DemoTestHandler) as api:
            status, payload = api.request("GET", "/api/demo/status", authenticated=False)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("demo", payload["mode"])
            self.assertEqual(self.seed_revision, payload["seed_revision"])
            self.assertEqual("lzug-demo-health-ready-v1", payload["runtime_contract"])
            self.assertEqual("Europe/Berlin", payload["reset_timezone"])
            self.assertEqual("ready", payload["initialization_status"])
            self.assertEqual("2026-08-14T01:00:00+00:00", payload["initialized_at"])
            self.assertEqual("2026-08-14T01:00:00+00:00", payload["last_reset_at"])
            self.assertEqual("scheduled", payload["reset_status"])
            self.assertNotIn("snapshot_sha256", payload)

            status, created = api.request(
                "POST", "/api/demo/session", {"role": "examiner"}, authenticated=False
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("examiner", created["role"])
            self.assertEqual("Testperson Gamma", created["display_name"])

            status, error = api.request(
                "POST", "/api/demo/session", {"role": "operator"}, authenticated=False
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertEqual("Unknown demo role.", error["error"])

    def test_session_exposes_only_role_capabilities_and_local_auth_is_disabled(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path, DemoTestHandler) as api:
            examiner = AuthenticationRepository(db_path).create_session(2, ttl=timedelta(hours=1))
            status, session = api.request("GET", "/api/session", credentials=examiner)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("examiner", session["demo_role"])
            self.assertEqual(
                ["attendance:write-own", "availability:write-own"], session["capabilities"]
            )

            status, error = api.request(
                "POST",
                "/api/auth/login",
                {
                    "email": "testperson.alpha@example.invalid",
                    "password": "x",
                    "second_factor": "x",
                },
                authenticated=False,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", error["error"])

    def test_default_deny_blocks_unapproved_writes_for_both_roles(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path, DemoTestHandler) as api:
            chair = AuthenticationRepository(db_path).create_session(1)
            examiner = AuthenticationRepository(db_path).create_session(2)

            status, _body = api.request(
                "POST",
                "/api/candidates",
                {
                    "first_name": "Prüfling",
                    "last_name": "Neu",
                    "ihk_exam_number": "TEST-NEW",
                    "specialization": "application_development",
                    "training_company": "Testbetrieb",
                },
                credentials=chair,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)

            status, _body = api.request(
                "PATCH",
                "/api/planning-settings/1",
                {"exams_per_day": 5},
                credentials=examiner,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)

            status, _body = api.request("DELETE", "/api/candidates/1", credentials=chair)
            assert_status(status, HTTPStatus.FORBIDDEN)

    def test_approved_own_and_chair_writes_still_use_domain_authorization(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path, DemoTestHandler) as api:
            chair = AuthenticationRepository(db_path).create_session(1)
            examiner = AuthenticationRepository(db_path).create_session(2)

            status, rows = api.request(
                "GET", "/api/member-availabilities?committee_member_id=3", credentials=examiner
            )
            assert_status(status, HTTPStatus.OK)
            own = next(item for item in rows["items"] if item["committee_member_id"] == 3)
            status, updated = api.request(
                "PATCH",
                f"/api/member-availabilities/{own['id']}",
                {
                    "availability": "unavailable",
                    "candidate_exam_day_id": own["candidate_exam_day_id"],
                },
                credentials=examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("unavailable", updated["availability"])

            status, updated = api.request(
                "PATCH",
                "/api/planning-settings/1",
                {"exams_per_day": 5},
                credentials=chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(5, updated["exams_per_day"])


if __name__ == "__main__":
    unittest.main()
