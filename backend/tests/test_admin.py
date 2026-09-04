from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing, redirect_stdout
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from backend.admin import EXIT_OK, EXIT_TOKEN_INVALID, _execute, _run_command, run
from backend.admin_service import AdminOperationError, IssuedAuthToken, OperatorAuthService
from backend.auth import AuthenticationRepository
from backend.tests.helpers import TempDatabase


class _RecordingDependency:
    db_path = "/data/lzug.sqlite"

    def __init__(self, *, failing: bool = False, issues_tokens: bool = False) -> None:
        self.failing = failing
        self.issues_tokens = issues_tokens
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        def handler(*_args: object, **_kwargs: object):
            self.calls.append(name)
            if self.failing:
                raise AdminOperationError("persistence_error", f"{name} failed")
            if self.issues_tokens and name in {"bootstrap", "invite", "recover"}:
                return SimpleNamespace(
                    account={"id": 7},
                    kind="invitation",
                    expires_at="2026-09-02T12:00:00+00:00",
                    token="test-token",
                )
            if name == "disable":
                return {"id": 7}, 1
            return {"handler": name}

        return handler


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
            with closing(sqlite3.connect(db_path)) as connection, connection:
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
            created_at = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
            bootstrap = service.bootstrap("operator@example.invalid", now=created_at)
            invitation = service.invite("member@example.invalid", now=created_at)
            recovery = service.recover(account_id=bootstrap.account["id"], now=created_at)

            self.assertEqual(
                timedelta(hours=24),
                datetime.fromisoformat(invitation.expires_at) - created_at,
            )
            self.assertEqual(
                timedelta(minutes=30),
                datetime.fromisoformat(recovery.expires_at) - created_at,
            )
            expired_at = datetime.fromisoformat(recovery.expires_at) + timedelta(seconds=1)
            with self.assertRaisesRegex(AdminOperationError, "invalid, expired"):
                service.consume(recovery.token, "recovery", now=expired_at)
            self.assertEqual(
                invitation.account["id"],
                service.consume(invitation.token, "invitation", now=expired_at)["id"],
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

    def test_committee_protocol_issues_invitation_once_and_replay_is_secret_free(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            request = {
                "version": 1,
                "command": "committee-bootstrap",
                "arguments": {
                    "idempotency_key": "bootstrap-001",
                    "committee": {
                        "name": "Prüfungsausschuss Nord",
                        "ihk": "IHK Teststadt",
                        "occupation": "Fachinformatiker/in",
                    },
                    "chair": {
                        "mode": "new",
                        "first_name": "Erste",
                        "last_name": "Vorsitzende",
                        "email": "chair@example.invalid",
                        "member_status": "ordinary",
                        "representing_side": "employer",
                    },
                },
            }

            first_output = io.BytesIO()
            first_stdout = io.TextIOWrapper(first_output, encoding="utf-8")
            with redirect_stdout(first_stdout):
                first_code = run(json.dumps(request).encode(), service=service)
            first_stdout.flush()
            first = json.loads(first_output.getvalue())
            token = first["result"]["invitations"][0]["token"]

            replay_output = io.BytesIO()
            replay_stdout = io.TextIOWrapper(replay_output, encoding="utf-8")
            with redirect_stdout(replay_stdout):
                replay_code = run(json.dumps(request).encode(), service=service)
            replay_stdout.flush()
            replay = json.loads(replay_output.getvalue())

            self.assertEqual(EXIT_OK, first_code)
            self.assertEqual(EXIT_OK, replay_code)
            self.assertTrue(replay["result"]["replayed"])
            self.assertEqual([], replay["result"]["invitations"])
            self.assertNotIn(token, replay_output.getvalue().decode())

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

    def test_notification_protocol_exposes_only_synthetic_diagnostics(self) -> None:
        class Notifications:
            def synthetic_test(self, member_id: int, channel: str):
                self.called = (member_id, channel)
                return {
                    "notification_id": 17,
                    "deliveries": [
                        {
                            "channel": channel,
                            "status": "technically_confirmed",
                            "attempt_count": 1,
                            "error_code": None,
                        }
                    ],
                }

        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            notifications = Notifications()
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            with redirect_stdout(stdout):
                code = run(
                    json.dumps(
                        {
                            "version": 1,
                            "command": "test-notification",
                            "arguments": {"member_id": 7, "channel": "web_push"},
                        }
                    ).encode(),
                    service=service,
                    notifications=notifications,
                )
            stdout.flush()
            response = json.loads(output.getvalue())

        self.assertEqual(EXIT_OK, code)
        self.assertEqual((7, "web_push"), notifications.called)
        self.assertNotIn("message", json.dumps(response))
        self.assertEqual("technically_confirmed", response["result"]["deliveries"][0]["status"])

    def test_operator_can_retry_plan_consequences_without_receiving_content(self) -> None:
        class Consequences:
            def retry_revision(self, revision_id: int):
                self.called = revision_id
                return {
                    "revision_id": revision_id,
                    "derivation_status": "succeeded",
                    "processed": 2,
                    "problems": 0,
                    "pending": 0,
                    "superseded": 1,
                }

            def operator_status(self, revision_id: int):
                self.status_called = revision_id
                return {
                    "revision_id": revision_id,
                    "technical_items": [
                        {
                            "id": 23,
                            "status": "permanently_failed",
                            "attempt_count": 4,
                            "error_code": "calendar_processing_failed",
                            "updated_at": "2026-08-30T12:00:00+00:00",
                        }
                    ],
                }

        with TempDatabase(with_seed=False) as db_path:
            service = OperatorAuthService(db_path)
            consequences = Consequences()
            output = io.BytesIO()
            stdout = io.TextIOWrapper(output, encoding="utf-8")
            with redirect_stdout(stdout):
                code = run(
                    json.dumps(
                        {
                            "version": 1,
                            "command": "retry-plan-consequences",
                            "arguments": {"revision_id": 17},
                        }
                    ).encode(),
                    service=service,
                    consequences=consequences,
                )
            stdout.flush()
            response = json.loads(output.getvalue())

        self.assertEqual(EXIT_OK, code)
        self.assertEqual(17, consequences.called)
        self.assertNotIn("details", json.dumps(response))
        self.assertEqual(2, response["result"]["processed"])

        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps(
                    {
                        "version": 1,
                        "command": "plan-consequences-status",
                        "arguments": {"revision_id": 17},
                    }
                ).encode(),
                service=service,
                consequences=consequences,
            )
        stdout.flush()
        response = json.loads(output.getvalue())

        self.assertEqual(EXIT_OK, code)
        self.assertEqual(17, consequences.status_called)
        self.assertNotIn("details", json.dumps(response))
        self.assertEqual(
            "calendar_processing_failed",
            response["result"]["technical_items"][0]["error_code"],
        )


class AdminCommandHandlerTests(unittest.TestCase):
    _COMMANDS = {
        "bootstrap": {"email": "operator@example.invalid"},
        "invite": {"email": "member@example.invalid"},
        "disable": {"account_id": 7},
        "recover": {"account_id": 7},
        "consume-invitation": {"token": "test-token"},
        "consume-recovery": {"token": "test-token"},
        "process-notifications": {},
        "test-notification": {"member_id": 7, "channel": "email"},
        "committee-bootstrap": {"idempotency_key": "bootstrap-001"},
        "committee-complete": {"idempotency_key": "complete-001"},
        "committee-reinvite": {"idempotency_key": "reinvite-001"},
        "committee-deactivate": {"idempotency_key": "deactivate-001"},
        "committee-reactivate": {"idempotency_key": "reactivate-001"},
        "retry-plan-consequences": {"revision_id": 7},
        "plan-consequences-status": {"revision_id": 7},
        "upgrade": {
            "target": {"version": "0.7.0"},
            "backup": {"verified": True},
            "confirm_irreversible": True,
        },
        "rollback": {"target": {"version": "0.6.0"}},
    }

    _EXPECTED_HANDLER = {
        "bootstrap": "bootstrap",
        "invite": "invite",
        "disable": "disable",
        "recover": "recover",
        "consume-invitation": "consume",
        "consume-recovery": "consume",
        "process-notifications": "process_due_events",
        "test-notification": "synthetic_test",
        "committee-bootstrap": "bootstrap",
        "committee-complete": "complete",
        "committee-reinvite": "reinvite",
        "committee-deactivate": "deactivate",
        "committee-reactivate": "reactivate",
        "retry-plan-consequences": "retry_revision",
        "plan-consequences-status": "operator_status",
        "upgrade": "upgrade",
        "rollback": "rollback",
    }

    def execute(
        self, command: str, *, failing: bool = False
    ) -> tuple[dict[str, object], tuple[_RecordingDependency, ...]]:
        service = _RecordingDependency(failing=failing, issues_tokens=True)
        notifications = _RecordingDependency(failing=failing)
        committee = _RecordingDependency(failing=failing)
        consequences = _RecordingDependency(failing=failing)
        artifacts = _RecordingDependency(failing=failing)
        lifecycle = _RecordingDependency(failing=failing)
        result = _execute(
            command,
            self._COMMANDS[command],
            service,
            notifications,
            committee,
            consequences,
            artifacts,
            lifecycle,
        )
        return result, (service, notifications, committee, consequences, artifacts, lifecycle)

    def test_each_backend_command_dispatches_to_its_handler(self) -> None:
        for command, expected_handler in self._EXPECTED_HANDLER.items():
            with self.subTest(command=command):
                result, dependencies = self.execute(command)

                self.assertTrue(
                    any(expected_handler in dependency.calls for dependency in dependencies)
                )
                if command in {"bootstrap", "invite", "recover"}:
                    self.assertEqual("test-token", result["token"])
                else:
                    self.assertIsInstance(result, dict)

    def test_each_backend_command_preserves_handler_errors(self) -> None:
        for command in self._EXPECTED_HANDLER:
            with self.subTest(command=command):
                with self.assertRaisesRegex(AdminOperationError, "failed"):
                    self.execute(command, failing=True)

    def test_each_diagnostic_command_has_success_and_error_evidence(self) -> None:
        commands = {
            "config": {},
            "doctor": {"client": {"identity": "development", "revision": "unknown"}},
            "status": {"client": {"identity": "development", "revision": "unknown"}},
        }
        for command, arguments in commands.items():
            with self.subTest(command=command, outcome="success"):
                with patch("backend.admin.run_diagnostics", return_value=({"command": command}, 0)):
                    result, exit_code = _run_command(
                        command, arguments, None, None, None, None, None, None
                    )
                self.assertEqual(EXIT_OK, exit_code)
                self.assertEqual(command, result["command"])

            with self.subTest(command=command, outcome="error"):
                with patch(
                    "backend.admin.run_diagnostics",
                    side_effect=AdminOperationError("invalid_request", "diagnostic failed"),
                ):
                    with self.assertRaisesRegex(AdminOperationError, "diagnostic failed"):
                        _run_command(command, arguments, None, None, None, None, None, None)
