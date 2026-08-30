from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.admin import run
from backend.admin_service import OperatorAuthService
from backend.build_metadata import BuildMetadata
from backend.diagnostics import EXIT_DIAGNOSTIC_ERROR, EXIT_DIAGNOSTIC_WARNING
from backend.tests.helpers import TempDatabase


class OperatorDiagnosticsTests(unittest.TestCase):
    revision = "a" * 40
    metadata = BuildMetadata.create(revision)
    client = {"identity": metadata.identity, "revision": revision}

    def _environment(self, db_path: Path) -> dict[str, str]:
        return {
            "LZUG_DATA_DIR": str(db_path.parent),
            "LZUG_DATABASE_PATH": str(db_path),
            "LZUG_HEALTHCHECK_URL": "http://127.0.0.1:8000/api/health",
        }

    def _prepare_paths(self, db_path: Path) -> None:
        (db_path.parent / "documents").mkdir(exist_ok=True)
        (db_path.parent / "backups").mkdir(exist_ok=True)

    def _invoke(self, command: str, arguments: dict[str, object]) -> tuple[int, str]:
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps({"version": 1, "command": command, "arguments": arguments}).encode()
            )
        stdout.flush()
        return code, output.getvalue().decode()

    def test_healthy_status_config_and_doctor_have_stable_success_contracts(self) -> None:
        with TempDatabase(with_seed=True) as db_path:
            self._prepare_paths(db_path)
            with (
                patch.dict(os.environ, self._environment(db_path), clear=True),
                patch("backend.diagnostics.build_metadata", return_value=self.metadata),
                patch("backend.diagnostics.public_health_ready", return_value=True),
            ):
                status_code, status_output = self._invoke("status", {"client": self.client})
                config_code, config_output = self._invoke("config", {})
                doctor_code, doctor_output = self._invoke("doctor", {"client": self.client})

        self.assertEqual(0, status_code)
        self.assertEqual(0, config_code)
        self.assertEqual(0, doctor_code)
        for command, output in (
            ("status", status_output),
            ("config", config_output),
            ("doctor", doctor_output),
        ):
            response = json.loads(output)
            self.assertTrue(response["ok"])
            self.assertEqual(command, response["result"]["command"])
            self.assertEqual("ok", response["result"]["status"])
            self.assertTrue(response["result"]["checks"])
            self.assertEqual(output, output.rstrip("\n") + "\n")

    def test_missing_runtime_and_incompatible_schema_are_diagnostic_errors(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            self._prepare_paths(db_path)
            environment = self._environment(db_path)
            with (
                patch.dict(os.environ, environment, clear=True),
                patch("backend.diagnostics.build_metadata", side_effect=OSError),
                patch("backend.diagnostics.public_health_ready", return_value=True),
            ):
                runtime_code, runtime_output = self._invoke("status", {"client": self.client})
            with (
                patch.dict(os.environ, environment, clear=True),
                patch("backend.diagnostics.build_metadata", return_value=self.metadata),
                patch(
                    "backend.diagnostics.database_readiness",
                    return_value={
                        "ready": False,
                        "reason": "migration_error",
                        "migration": {
                            "current": None,
                            "target": "023_add_exam_round_lifecycle.sql",
                        },
                    },
                ),
                patch("backend.diagnostics.public_health_ready", return_value=True),
            ):
                schema_code, schema_output = self._invoke("status", {"client": self.client})

        self.assertEqual(EXIT_DIAGNOSTIC_ERROR, runtime_code)
        self.assertIn('"code":"runtime_unavailable"', runtime_output)
        self.assertEqual(EXIT_DIAGNOSTIC_ERROR, schema_code)
        self.assertIn('"code":"schema_incompatible"', schema_output)

    def test_data_rights_are_errors_and_low_space_is_a_warning(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            self._prepare_paths(db_path)
            environment = self._environment(db_path)
            with (
                patch.dict(os.environ, environment, clear=True),
                patch("backend.diagnostics.build_metadata", return_value=self.metadata),
                patch("backend.diagnostics.public_health_ready", return_value=True),
                patch("backend.diagnostics._probe_directory", return_value=False),
            ):
                rights_code, rights_output = self._invoke("doctor", {"client": self.client})
            with (
                patch.dict(os.environ, environment, clear=True),
                patch("backend.diagnostics.build_metadata", return_value=self.metadata),
                patch("backend.diagnostics.public_health_ready", return_value=True),
                patch(
                    "backend.diagnostics.shutil.disk_usage",
                    return_value=SimpleNamespace(free=1),
                ),
            ):
                space_code, space_output = self._invoke("doctor", {"client": self.client})

        self.assertEqual(EXIT_DIAGNOSTIC_ERROR, rights_code)
        self.assertIn('"code":"data_not_writable"', rights_output)
        self.assertEqual(EXIT_DIAGNOSTIC_WARNING, space_code)
        self.assertIn('"status":"warning"', space_output)
        self.assertIn('"code":"free_space_low"', space_output)

    def test_configuration_errors_are_concrete_without_reflecting_values(self) -> None:
        secret_marker = "diagnostic-secret-marker"
        domain_marker = "diagnostic-person@example.invalid"
        with TempDatabase(with_seed=False) as db_path:
            self._prepare_paths(db_path)
            issued = OperatorAuthService(db_path).invite(domain_marker)
            environment = self._environment(db_path) | {
                "LZUG_SESSION_TTL_SECONDS": secret_marker,
                "LZUG_SMTP_PASSWORD": secret_marker,
            }
            with patch.dict(os.environ, environment, clear=True):
                code, output = self._invoke("config", {})

        self.assertEqual(EXIT_DIAGNOSTIC_ERROR, code)
        response = json.loads(output)
        http_check = next(
            item for item in response["result"]["checks"] if item["id"] == "http_configuration"
        )
        self.assertEqual("configuration_invalid", http_check["code"])
        self.assertIn("LZUG_SESSION_TTL_SECONDS", http_check["message"])
        self.assertNotIn(secret_marker, output)
        self.assertNotIn(domain_marker, output)
        self.assertNotIn(issued.token, output)

    def test_status_rejects_non_loopback_health_url_without_requesting_it(self) -> None:
        secret_marker = "diagnostic-health-secret.example.invalid"
        with TempDatabase(with_seed=False) as db_path:
            environment = self._environment(db_path) | {
                "LZUG_HEALTHCHECK_URL": f"https://{secret_marker}/api/health"
            }
            with (
                patch.dict(os.environ, environment, clear=True),
                patch("backend.diagnostics.build_metadata", return_value=self.metadata),
                patch("backend.diagnostics.public_health_ready") as public_health_ready,
            ):
                code, output = self._invoke("status", {"client": self.client})

        self.assertEqual(EXIT_DIAGNOSTIC_ERROR, code)
        self.assertIn('"code":"configuration_invalid"', output)
        self.assertNotIn(secret_marker, output)
        public_health_ready.assert_not_called()

    def test_diagnostic_protocol_rejects_extra_or_secret_shaped_arguments(self) -> None:
        code, output = self._invoke(
            "doctor", {"client": self.client, "database": "/data/lzug.sqlite"}
        )

        self.assertEqual(20, code)
        self.assertFalse(json.loads(output)["ok"])
        self.assertNotIn("/data/lzug.sqlite", output)

        marker = "secret-client-identity"
        code, output = self._invoke(
            "status", {"client": {"identity": marker, "revision": self.revision}}
        )

        self.assertEqual(20, code)
        self.assertFalse(json.loads(output)["ok"])
        self.assertNotIn(marker, output)
