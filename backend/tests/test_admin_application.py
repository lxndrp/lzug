from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.application.admin import (
    EXIT_AUTHORIZATION,
    EXIT_CONFLICT,
    EXIT_OK,
    AdminActorContext,
    AdminApplication,
    AdminServices,
)
from backend.identity.admin_service import AdminOperationError
from backend.persistence.database import PersistencePaths


class AdminApplicationTests(unittest.TestCase):
    def services(
        self,
        *,
        diagnostics: Any = None,
        readiness: Any = None,
        operator_auth: Any = None,
    ) -> AdminServices:
        unused = SimpleNamespace()
        return AdminServices(
            diagnostics=diagnostics or (lambda command, _client: ({"command": command}, EXIT_OK)),
            readiness_probe=readiness or (lambda _path: {"ready": True}),
            operator_auth_factory=operator_auth or (lambda _path: unused),
            notification_factory=lambda _path: unused,
            committee_factory=lambda _path: unused,
            consequence_factory=lambda _path, _notifications: unused,
            artifact_factory=lambda _paths: unused,
            recipient_repository_factory=lambda _artifacts: unused,
            lifecycle_factory=lambda _paths: unused,
        )

    def application(self, services: AdminServices | None = None) -> AdminApplication:
        return AdminApplication(
            PersistencePaths(
                data_dir=Path("/srv/lzug"),
                database=Path("/srv/lzug/lzug.sqlite"),
                documents=Path("/srv/lzug/documents"),
                backups=Path("/srv/lzug/backups"),
            ),
            services or self.services(),
        )

    def test_core_returns_response_without_writing_global_output(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.application().handle(
                json.dumps({"version": 1, "command": "config", "arguments": {}}).encode(),
                AdminActorContext("verified-peer", True),
            )

        self.assertEqual("", output.getvalue())
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual(
            {"version": 1, "ok": True, "result": {"command": "config"}},
            result.response,
        )
        self.assertEqual(result.response, json.loads(result.encode()))

    def test_client_actor_claim_cannot_authorize_an_untrusted_server_context(self) -> None:
        calls: list[str] = []
        services = self.services(
            diagnostics=lambda command, _client: (calls.append(command) or {}, EXIT_OK)
        )
        request = {
            "version": 1,
            "command": "config",
            "arguments": {},
            "actor": {"technical_identity": "claimed-operator", "is_authorized": True},
        }

        rejected = self.application(services).execute(
            request, AdminActorContext("untrusted-peer", False)
        )
        self.assertEqual([], calls)

        accepted = self.application(services).execute(
            {**request, "actor": {"is_authorized": False}},
            AdminActorContext("verified-peer", True),
        )

        self.assertEqual(EXIT_AUTHORIZATION, rejected.exit_code)
        self.assertEqual("authorization_failed", rejected.response["error"]["class"])
        self.assertEqual(EXIT_OK, accepted.exit_code)
        self.assertEqual(["config"], calls)
        self.assertNotIn("claimed-operator", rejected.encode().decode())

    def test_persistence_path_and_account_service_are_injected(self) -> None:
        observed: list[tuple[str, Path]] = []

        class Accounts:
            def invite(self, email: str):
                self.email = email
                return SimpleNamespace(
                    account={"id": 7},
                    kind="invitation",
                    expires_at="2026-09-09T12:00:00+00:00",
                    token="one-time-token",
                )

        accounts = Accounts()
        services = self.services(
            readiness=lambda path: observed.append(("readiness", path)) or {"ready": True},
            operator_auth=lambda path: observed.append(("accounts", path)) or accounts,
        )
        result = self.application(services).execute(
            {
                "version": 1,
                "command": "invite",
                "arguments": {"email": "member@example.invalid"},
            },
            AdminActorContext("verified-peer", True),
        )

        expected = Path("/srv/lzug/lzug.sqlite")
        self.assertEqual([("readiness", expected), ("accounts", expected)], observed)
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual("one-time-token", result.response["result"]["token"])
        self.assertEqual("member@example.invalid", accounts.email)

    def test_existing_handler_error_class_and_exit_code_are_preserved(self) -> None:
        class Accounts:
            def invite(self, _email: str):
                raise AdminOperationError("account_exists", "An account already exists")

        result = self.application(self.services(operator_auth=lambda _path: Accounts())).execute(
            {
                "version": 1,
                "command": "invite",
                "arguments": {"email": "member@example.invalid"},
            },
            AdminActorContext("verified-peer", True),
        )

        self.assertEqual(EXIT_CONFLICT, result.exit_code)
        self.assertEqual("account_exists", result.response["error"]["class"])
        self.assertEqual("An account already exists", result.response["error"]["message"])


if __name__ == "__main__":
    unittest.main()
