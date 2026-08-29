from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path

from backend.application import ForbiddenRequestError
from backend.auth import AuthContext, AuthenticationRepository
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler, assert_status
from demo.contract import RUNTIME_CONTRACT, canonical_digest, demo_identity
from demo.runtime_policy import (
    DEMO_MATRIX_VERSION,
    DEMO_MUTATION_MATRIX,
    DEMO_READ_MATRIX,
    DEMO_ROLES,
    ROLE_CAPABILITIES,
    DemoRuntimePolicy,
)


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
            self.assertEqual(DEMO_MATRIX_VERSION, payload["demo_matrix_version"])
            self.assertNotIn("snapshot_sha256", payload)

            status, created = api.request(
                "POST", "/api/demo/session", {"role": "examiner"}, authenticated=False
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("examiner", created["role"])
            self.assertEqual("Testperson Gamma", created["display_name"])

            status, created = api.request(
                "POST", "/api/demo/session", {"role": "deputy"}, authenticated=False
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual("deputy", created["role"])
            self.assertEqual("Testperson Beta", created["display_name"])

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
                [
                    "absence:read-own",
                    "attendance:write-own",
                    "availability:write-own",
                    "calendar:read-own",
                    "exam-day-closure:export",
                    "exam-day-closure:read",
                    "exam-half-years:read",
                    "exam-protocol:export",
                    "exam-protocol:read",
                    "exam-protocol:request-correction",
                    "exam-protocol:respond",
                    "exam-protocol:submit",
                    "exam-protocol:write",
                    "exam-result:assess-own",
                    "exam-result:confirm-record",
                    "exam-result:export",
                    "exam-result:read",
                    "notifications:read-own",
                ],
                session["capabilities"],
            )
            self.assertEqual(DEMO_MATRIX_VERSION, session["demo_matrix_version"])

            deputy = AuthenticationRepository(db_path).create_session(3, ttl=timedelta(hours=1))
            status, deputy_session = api.request("GET", "/api/session", credentials=deputy)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("deputy", deputy_session["demo_role"])
            self.assertTrue(
                {
                    "exam-result:assess-own",
                    "exam-result:disclose",
                    "exam-result:external-record",
                    "exam-result:external-confirm",
                    "exam-result:determine-component",
                    "exam-result:determine",
                    "exam-result:confirm-record",
                    "exam-result:coordinate-correction",
                    "exam-result:communicate",
                    "exam-day-closure:close",
                    "exam-day-closure:preview-reopening",
                    "exam-day-closure:reopen",
                }.issubset(deputy_session["capabilities"])
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

            denied_requests = (
                ("POST", "/api/candidate-exam-days", {"date": "2026-12-01"}),
                ("PATCH", "/api/candidate-exam-days/1", {"is_active": 0}),
                ("POST", "/api/exam-half-years", {"season": "summer", "year": 2027}),
                ("PATCH", "/api/exam-half-years/1", {"status": "completed"}),
                ("POST", "/api/exam-rounds", {"exam_half_year_id": 1, "committee_id": 1}),
                ("POST", "/api/push-subscriptions", {"endpoint": "https://example.invalid"}),
                ("POST", "/api/calendar/feed", {"rotate": False}),
                ("DELETE", "/api/calendar/feed", None),
                ("POST", "/api/absence-reports", {"exam_day_assignment_id": 1}),
                ("PATCH", "/api/replacement-responses/1", {"response": "available"}),
            )
            for credentials in (chair, examiner):
                for method, path, payload in denied_requests:
                    with self.subTest(account_id=credentials.account_id, method=method, path=path):
                        status, _body = api.request(method, path, payload, credentials=credentials)
                        assert_status(status, HTTPStatus.FORBIDDEN)

            status, _body = api.request(
                "PATCH",
                "/api/planning-settings/1",
                {"exams_per_day": 5},
                credentials=examiner,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)

    def test_matrix_contracts_align_visibility_capabilities_and_allowlist(self) -> None:
        names = [contract.name for contract in (*DEMO_READ_MATRIX, *DEMO_MUTATION_MATRIX)]
        self.assertEqual(len(names), len(set(names)))

        contexts = {
            role: AuthContext(
                session_id=index,
                account_id=identity["account_id"],
                person_id=identity["person_id"],
                is_operator=False,
                committee_member_id=identity["person_id"],
            )
            for index, (role, identity) in enumerate(DEMO_ROLES.items(), start=1)
        }
        policy = DemoTestHandler.runtime_policy

        for contract in DEMO_READ_MATRIX:
            with self.subTest(contract=contract.name):
                self.assertTrue(contract.allowed)
                self.assertTrue(contract.visible)
                self.assertTrue(contract.domain_authorization)
                for role in contract.roles:
                    self.assertIn(contract.capability, ROLE_CAPABILITIES[role])

        for contract in DEMO_MUTATION_MATRIX:
            sample_parts = [
                "1" if part.startswith("{") else part
                for part in contract.path_pattern.strip("/").split("/")
            ]
            with self.subTest(contract=contract.name):
                self.assertTrue(contract.ui_action)
                self.assertTrue(contract.domain_authorization)
                self.assertEqual(contract.allowed, contract.visible)
                for role in contract.roles:
                    context = contexts[role]
                    if contract.allowed:
                        self.assertIn(contract.capability, ROLE_CAPABILITIES[role])
                        policy.authorize_mutation(
                            object(), contract.method, sample_parts, context  # type: ignore[arg-type]
                        )
                        with self.assertRaises(ForbiddenRequestError):
                            policy.authorize_mutation(
                                object(), "DELETE", sample_parts, context  # type: ignore[arg-type]
                            )
                    else:
                        self.assertNotIn(contract.capability, ROLE_CAPABILITIES[role])
                        with self.assertRaises(ForbiddenRequestError):
                            policy.authorize_mutation(
                                object(), contract.method, sample_parts, context  # type: ignore[arg-type]
                            )

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
