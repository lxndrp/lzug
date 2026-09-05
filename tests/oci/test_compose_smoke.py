from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

FAKE_DOCKER = r"""#!/usr/bin/env sh
set -eu

printf '%s\n' "$*" >>"$FAKE_ENGINE_LOG"

case "$*" in
    info)
        ;;
    compose*" ps -q lzug")
        echo "fake-container"
        ;;
    compose*" ps --all --format json")
        printf '[{"Health":"%s","State":"%s"}]\n' \
            "${FAKE_DOCKER_HEALTH:-starting}" "${FAKE_DOCKER_STATE:-exited}"
        ;;
    compose*" ps --all")
        echo "fake-container running (${FAKE_DOCKER_HEALTH:-starting})"
        ;;
    compose*" port lzug "*)
        echo "127.0.0.1:49152"
        ;;
    compose*" exec -T lzug python -m backend.healthcheck")
        test "${FAKE_DIRECT_HEALTH:-passed}" = "passed"
        ;;
    compose*" exec -T lzug python -c "*"read_text"*)
        echo "persisted"
        ;;
    compose*" logs")
        echo "fake compose logs" >&2
        ;;
    exec*" id -u")
        echo "10001"
        ;;
esac
"""

FAKE_CURL = r"""#!/usr/bin/env sh
set -eu
printf '%s' "${FAKE_HTTP_STATUS:-200}"
"""


class ComposeSmokeTests(unittest.TestCase):
    def run_smoke(self, **overrides: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            binary_directory = temporary / "bin"
            binary_directory.mkdir()
            engine_log = temporary / "engine.log"

            for name, content in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL)):
                executable = binary_directory / name
                executable.write_text(textwrap.dedent(content), encoding="utf-8")
                executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            environment = os.environ.copy()
            environment.update(
                {
                    "CONTAINER_ENGINE": "docker",
                    "FAKE_ENGINE_LOG": str(engine_log),
                    "LZUG_COMPOSE_READY_INTERVAL_SECONDS": "1",
                    "LZUG_COMPOSE_READY_TIMEOUT_SECONDS": "1",
                    "LZUG_IMAGE": "lzug:0.0.0-test.local",
                    "PATH": f"{binary_directory}{os.pathsep}{environment['PATH']}",
                }
            )
            environment.update(overrides)

            result = subprocess.run(
                ["sh", "scripts/compose-smoke.sh"],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )
            commands = engine_log.read_text(encoding="utf-8")
        return result, commands

    def test_lifecycle_uses_functional_health_while_scheduler_is_starting(self) -> None:
        result, commands = self.run_smoke(
            FAKE_DIRECT_HEALTH="passed",
            FAKE_DOCKER_HEALTH="starting",
            FAKE_HTTP_STATUS="200",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Waiting for Compose readiness after start.", result.stdout)
        self.assertIn("Waiting for Compose readiness after restart.", result.stdout)
        self.assertIn("Waiting for Compose stop to complete.", result.stdout)
        self.assertIn("Waiting for Compose readiness after stop/start.", result.stdout)
        self.assertEqual(commands.count("python -m backend.healthcheck"), 3)
        self.assertIn(" restart lzug", commands)
        self.assertIn(" stop lzug", commands)
        self.assertIn(" start lzug", commands)
        self.assertGreaterEqual(commands.count("read_text"), 2)
        stop_offset = commands.index(" stop lzug")
        stopped_state_offset = commands.index(" ps --all --format json", stop_offset)
        start_offset = commands.index(" start lzug")
        self.assertLess(stop_offset, stopped_state_offset)
        self.assertLess(stopped_state_offset, start_offset)

    def test_stop_timeout_does_not_start_a_container_that_is_still_stopping(self) -> None:
        result, commands = self.run_smoke(
            FAKE_DIRECT_HEALTH="passed",
            FAKE_DOCKER_HEALTH="healthy",
            FAKE_DOCKER_STATE="stopping",
            FAKE_HTTP_STATUS="200",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose stop timed out", result.stderr)
        self.assertIn("lifecycle_status=stopping", result.stderr)
        self.assertNotIn(" start lzug", commands)

    def test_timeout_reports_direct_health_failure_with_runtime_diagnostics(self) -> None:
        result, _commands = self.run_smoke(
            FAKE_DIRECT_HEALTH="failed",
            FAKE_DOCKER_HEALTH="unhealthy",
            FAKE_HTTP_STATUS="200",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose readiness timed out after start", result.stderr)
        self.assertIn("http_status=200", result.stderr)
        self.assertIn("direct_healthcheck=failed", result.stderr)
        self.assertIn("docker_health=unhealthy", result.stderr)
        self.assertIn("Compose service state:", result.stderr)
        self.assertIn("fake-container running (unhealthy)", result.stderr)
        self.assertIn("Compose logs:", result.stderr)
        self.assertIn("fake compose logs", result.stderr)

    def test_timeout_reports_public_http_failure(self) -> None:
        result, _commands = self.run_smoke(
            FAKE_DIRECT_HEALTH="passed",
            FAKE_DOCKER_HEALTH="healthy",
            FAKE_HTTP_STATUS="503",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose readiness timed out after start", result.stderr)
        self.assertIn("http_status=503", result.stderr)
        self.assertIn("direct_healthcheck=passed", result.stderr)
        self.assertIn("docker_health=healthy", result.stderr)


if __name__ == "__main__":
    unittest.main()
