from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

from backend.admin import EXIT_OK, EXIT_TOKEN_INVALID, run
from backend.admin_service import AdminOperationError, IssuedAuthToken, OperatorAuthService
from backend.auth import AuthenticationRepository
from backend.tests.helpers import TempDatabase


class AdminAuthenticationTests(unittest.TestCase):
    def test_bootstrap_is_once_only_and_token_is_hashed_and_single_use(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            created_at = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
            issued = service.bootstrap("Operator@Example.Invalid", now=created_at)

            self.assertTrue(issued.account["is_operator"])
            self.assertIsNone(issued.account["person_id"])
            self.assertEqual(
                created_at + timedelta(hours=24), datetime.fromisoformat(issued.expires_at)
            )
            with sqlite3.connect(db_path) as connection:
                token_hash = connection.execute(
                    "SELECT token_hash FROM auth_token WHERE id = 1"
                ).fetchone()[0]
            self.assertEqual(hashlib.sha256(issued.token.encode()).hexdigest(), token_hash)
            self.assertNotEqual(issued.token, token_hash)

            consumed = service.consume(issued.token, "invitation", now=created_at)
            self.assertEqual(issued.account["id"], consumed["id"])
            with self.assertRaisesRegex(AdminOperationError, "invalid, expired"):
                service.consume(issued.token, "invitation", now=created_at)
            with self.assertRaisesRegex(AdminOperationError, "without accounts"):
                service.bootstrap("second@example.invalid", now=created_at)

    def test_concurrent_bootstrap_can_create_only_one_operator(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            outcomes: list[object] = []

            def bootstrap() -> None:
                try:
                    outcomes.append(service.bootstrap("operator@example.invalid"))
                except AdminOperationError as error:
                    outcomes.append(error.code)

            from threading import Thread

            threads = [Thread(target=bootstrap) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual(2, len(outcomes))
            self.assertEqual(1, sum(isinstance(outcome, IssuedAuthToken) for outcome in outcomes))
            self.assertEqual(1, sum(outcome == "bootstrap_not_empty" for outcome in outcomes))

    def test_invitation_and_recovery_have_distinct_expiry_and_one_use_contracts(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            bootstrap = service.bootstrap("operator@example.invalid")
            invitation = service.invite("member@example.invalid")
            recovery = service.recover(account_id=bootstrap.account["id"])

            invitation_created = datetime.fromisoformat(invitation.account["created_at"]).replace(
                tzinfo=UTC
            )
            recovery_created = datetime.fromisoformat(recovery.account["created_at"]).replace(
                tzinfo=UTC
            )
            self.assertEqual(
                timedelta(hours=24),
                datetime.fromisoformat(invitation.expires_at) - invitation_created,
            )
            self.assertEqual(
                timedelta(minutes=30),
                datetime.fromisoformat(recovery.expires_at) - recovery_created,
            )
            expired_at = datetime.fromisoformat(recovery.expires_at) + timedelta(seconds=1)
            with self.assertRaisesRegex(AdminOperationError, "invalid, expired"):
                service.consume(recovery.token, "recovery", now=expired_at)
            self.assertEqual(
                invitation.account["id"], service.consume(invitation.token, "invitation")["id"]
            )

    def test_disable_revokes_sessions_and_operator_has_no_domain_actor(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            issued = service.bootstrap("operator@example.invalid")
            credentials = AuthenticationRepository(db_path).create_session(issued.account["id"])

            account, revoked = service.disable(issued.account["id"])

            self.assertFalse(account["is_active"])
            self.assertEqual(1, revoked)
            self.assertIsNone(AuthenticationRepository(db_path).authenticate(credentials.token))
            self.assertIsNone(account["person_id"])
            self.assertTrue(account["is_operator"])

    def test_protocol_is_versioned_and_never_reflects_invalid_secret_input(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            secret = "not-a-real-token"
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            with redirect_stdout(stdout):
                code = run(
                    json.dumps(
                        {
                            "version": 999,
                            "command": "consume-invitation",
                            "arguments": {"token": secret},
                        }
                    ).encode(),
                    service=service,
                )
            stdout.flush()
            response = output.getvalue().decode()

            self.assertEqual(20, code)
            self.assertNotIn(secret, response)
            self.assertEqual(1, json.loads(response)["version"])

    def test_protocol_success_exposes_a_token_only_for_an_issue_response(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            with redirect_stdout(stdout):
                code = run(
                    json.dumps(
                        {
                            "version": 1,
                            "command": "bootstrap",
                            "arguments": {"email": "operator@example.invalid"},
                        }
                    ).encode(),
                    service=service,
                )
            stdout.flush()
            response = json.loads(output.getvalue().decode())

            self.assertEqual(EXIT_OK, code)
            self.assertTrue(response["ok"])
            self.assertIn("token", response["result"])
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            with redirect_stdout(stdout):
                code = run(
                    json.dumps(
                        {
                            "version": 1,
                            "command": "consume-invitation",
                            "arguments": {"token": "other"},
                        }
                    ).encode(),
                    service=service,
                )
            stdout.flush()
            self.assertEqual(EXIT_TOKEN_INVALID, code)
            self.assertNotIn("other", output.getvalue().decode())

    def test_module_process_uses_the_versioned_protocol_and_no_stderr_secret(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            environment = os.environ.copy()
            environment["LZUG_DATABASE_PATH"] = str(db_path)
            process = subprocess.run(
                [sys.executable, "-m", "backend.admin", "--protocol", "1"],
                input=json.dumps(
                    {
                        "version": 1,
                        "command": "bootstrap",
                        "arguments": {"email": "operator@example.invalid"},
                    }
                ).encode(),
                capture_output=True,
                env=environment,
                check=False,
            )

            self.assertEqual(0, process.returncode)
            self.assertEqual(b"", process.stderr)
            response = json.loads(process.stdout)
            self.assertTrue(response["ok"])
            self.assertTrue(response["result"]["token"])
