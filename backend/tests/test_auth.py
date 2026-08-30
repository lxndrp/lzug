from __future__ import annotations

import hashlib
import sqlite3
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from backend.auth import AuthenticationRepository
from backend.models import COMMITTEE
from backend.repositories import ResourceRepository
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class AuthenticationTests(unittest.TestCase):
    def test_session_material_is_opaque_and_context_resolves_from_account(self) -> None:
        with TempDatabase() as db_path:
            repository = AuthenticationRepository(db_path)
            account = repository.create_account(
                "New.User@Example.Invalid", person_id=4, is_operator=False
            )
            credentials = repository.create_session(account["id"])
            context = repository.authenticate(credentials.token)

            with sqlite3.connect(db_path) as connection:
                row = connection.execute(
                    "SELECT token_hash, csrf_token_hash FROM auth_session WHERE id = ?",
                    (credentials.session_id,),
                ).fetchone()

        self.assertIsNotNone(context)
        self.assertEqual(4, context.person_id)
        self.assertEqual(4, context.committee_member_id)
        self.assertNotEqual(credentials.token, row[0])
        self.assertNotEqual(credentials.csrf_token, row[1])
        self.assertEqual(hashlib.sha256(credentials.token.encode()).hexdigest(), row[0])

    def test_expiration_rotation_logout_and_account_revocation(self) -> None:
        with TempDatabase() as db_path:
            repository = AuthenticationRepository(db_path)
            account = repository.get_account(1)
            created_at = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
            credentials = repository.create_session(
                account["id"], now=created_at, ttl=timedelta(hours=1)
            )
            self.assertIsNone(
                repository.authenticate(credentials.token, now=created_at + timedelta(hours=1))
            )

            rotated = repository.rotate_session(credentials.token, now=created_at)
            self.assertIsNotNone(rotated)
            self.assertIsNone(repository.authenticate(credentials.token, now=created_at))
            self.assertIsNotNone(repository.authenticate(rotated.token, now=created_at))
            self.assertTrue(repository.revoke_session(rotated.token))
            self.assertIsNone(repository.authenticate(rotated.token, now=created_at))

            replacement = repository.create_session(account["id"])
            self.assertEqual(1, repository.revoke_account_sessions(account["id"]))
            self.assertIsNone(repository.authenticate(replacement.token))

    def test_protected_api_requires_session_but_health_is_public(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, error = api.request("GET", "/api/candidates", authenticated=False)
            assert_status(status, HTTPStatus.UNAUTHORIZED)
            self.assertEqual("Authentication required.", error["error"])

            status, health = api.request("GET", "/api/health", authenticated=False)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("ok", health["status"])
            self.assertNotIn("candidates", health)

    def test_invalid_expired_and_revoked_sessions_are_401(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            repository = AuthenticationRepository(db_path)
            expired = repository.create_session(
                1,
                now=datetime(2020, 1, 1, tzinfo=UTC),
                ttl=timedelta(hours=1),
            )
            status, _body = api.request("GET", "/api/candidates", credentials=expired)
            assert_status(status, HTTPStatus.UNAUTHORIZED)

            revoked = repository.create_session(1)
            repository.revoke_session(revoked.token)
            status, _body = api.request("GET", "/api/candidates", credentials=revoked)
            assert_status(status, HTTPStatus.UNAUTHORIZED)

            invalid = replace(api.credentials, token="invalid-session")
            status, _body = api.request("GET", "/api/candidates", credentials=invalid)
            assert_status(status, HTTPStatus.UNAUTHORIZED)

    def test_mutations_require_csrf_and_server_overwrites_actor(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            invalid_csrf = replace(api.credentials, csrf_token="invalid-csrf")
            status, _body = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "season": "summer",
                    "year": 2030,
                    "committee_id": 1,
                    "name": "Session actor",
                },
                credentials=invalid_csrf,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)

            status, round_data = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "season": "summer",
                    "year": 2030,
                    "committee_id": 1,
                    "name": "Session actor",
                    "created_by_member_id": 999999,
                },
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual(1, round_data["created_by_member_id"])

    def test_operator_identity_does_not_become_a_domain_actor(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            repository = AuthenticationRepository(db_path)
            account = repository.create_account("operator@example.invalid", is_operator=True)
            credentials = repository.create_session(account["id"])
            status, error = api.request("GET", "/api/candidates", credentials=credentials)

        assert_status(status, HTTPStatus.FORBIDDEN)
        self.assertEqual("Forbidden.", error["error"])

    def test_missing_committee_or_round_membership_is_forbidden(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            committee = ResourceRepository(db_path).create(
                COMMITTEE, {"name": "Unassigned committee", "occupation": "Test"}
            )

            status, error = api.request(
                "POST",
                "/api/exam-rounds",
                {
                    "exam_half_year_id": 1,
                    "committee_id": committee["id"],
                    "name": "Unauthorized round",
                    "created_by_member_id": 999999,
                },
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", error["error"])

            status, error = api.request(
                "PATCH",
                "/api/planning-settings/1",
                {"exam_round_id": 999999, "updated_by_member_id": 999999},
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            self.assertEqual("Forbidden.", error["error"])

    def test_cookie_contract_and_logout(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, headers, _body = api.request_raw("POST", "/api/session/logout")
            assert_status(status, HTTPStatus.NO_CONTENT)
            set_cookies = headers.get("set-cookie", "")
            self.assertIn("Max-Age=0", set_cookies)
            self.assertIn("SameSite=Strict", set_cookies)

            status, _body = api.request("GET", "/api/candidates")
            assert_status(status, HTTPStatus.UNAUTHORIZED)
