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
if [ "$1" = compose ]; then
    printf 'socket-dir=%s database=%s url=%s\n' \
        "$LZUG_ADMIN_SOCKET_DIR" "$LZUG_DATABASE_PATH" "$LZUG_DATABASE_URL" \
        >>"$FAKE_ENGINE_LOG"
fi

case "$*" in
    info)
        ;;
    compose*" run "*"--user 0:0"*)
        exit "${FAKE_SOCKET_SETUP_STATUS:-0}"
        ;;
    compose*" run "*"initialize()"*)
        exit "${FAKE_DATABASE_INIT_STATUS:-0}"
        ;;
    compose*" exec -T lzug python -c "*"stat.S_ISSOCK"*)
        exit "${FAKE_SOCKET_CHECK_STATUS:-0}"
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
                    "FAKE_ENGINE_LOG": str(engine_log),
                    "LZUG_COMPOSE_READY_INTERVAL_SECONDS": "1",
                    "LZUG_COMPOSE_READY_TIMEOUT_SECONDS": "1",
                    "LZUG_IMAGE": "lzug-app:0.0.0-test.local",
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
            FAKE_DOCKER_HEALTH="starting",
            FAKE_HTTP_STATUS="200",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Waiting for Compose readiness after start.", result.stdout)
        self.assertIn("Waiting for Compose readiness after restart.", result.stdout)
        self.assertIn("Waiting for Compose stop to complete.", result.stdout)
        self.assertIn("Waiting for Compose readiness after stop/start.", result.stdout)
        self.assertNotIn("python -m backend.healthcheck", commands)
        self.assertIn(" restart lzug", commands)
        self.assertIn(" stop lzug", commands)
        self.assertIn(" start lzug", commands)
        self.assertGreaterEqual(commands.count("read_text"), 2)
        stop_offset = commands.index(" stop lzug")
        stopped_state_offset = commands.index(" ps --all --format json", stop_offset)
        start_offset = commands.index(" start lzug")
        self.assertLess(stop_offset, stopped_state_offset)
        self.assertLess(stopped_state_offset, start_offset)
        self.assertEqual(commands.count("stat.S_ISSOCK"), 3)

    def test_private_fixture_is_prepared_before_service_start_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            operator_directory = Path(directory) / "operator-socket"
            operator_directory.mkdir(mode=0o700)
            marker = operator_directory / "keep"
            marker.write_text("operator data", encoding="utf-8")
            result, commands = self.run_smoke(
                LZUG_ADMIN_SOCKET_DIR=str(operator_directory),
                LZUG_DATABASE_PATH="/run/operator.sqlite",
                LZUG_DATABASE_URL="sqlite:////run/operator.sqlite",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "operator data")
            self.assertEqual(stat.S_IMODE(operator_directory.stat().st_mode), 0o700)
            self.assertNotIn(str(operator_directory), commands)
            self.assertNotIn("operator.sqlite", commands)

        mounts = [line for line in commands.splitlines() if line.startswith("socket-dir=")]
        self.assertTrue(mounts)
        self.assertEqual(len(set(mounts)), 1)
        self.assertTrue(mounts[0].endswith(" database=/data/lzug.sqlite url="))
        socket_directory = Path(mounts[0].split(" database=")[0].removeprefix("socket-dir="))
        self.assertFalse(socket_directory.parent.exists())
        setup = commands.index("--user 0:0 --cap-add CHOWN --cap-add FOWNER")
        initialize = commands.index(" run --rm --no-deps --entrypoint python lzug")
        start = commands.index(" up -d")
        self.assertLess(setup, initialize)
        self.assertLess(initialize, start)
        self.assertIn("chown 10001:10001 /run/lzug-admin && chmod 0750", commands)
        self.assertNotIn("--user", commands[initialize:start])

    def test_fixture_failure_prevents_start_and_still_cleans_up(self) -> None:
        for failure in ("FAKE_SOCKET_SETUP_STATUS", "FAKE_DATABASE_INIT_STATUS"):
            with self.subTest(failure=failure):
                result, commands = self.run_smoke(**{failure: "1"})
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(" up -d", commands)
                self.assertIn(" down --volumes --remove-orphans", commands)

    def test_socket_contract_failure_stops_lifecycle_checks(self) -> None:
        result, commands = self.run_smoke(FAKE_SOCKET_CHECK_STATUS="1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(" restart lzug", commands)
        self.assertIn(" down --volumes --remove-orphans", commands)

    def test_stop_timeout_does_not_start_a_container_that_is_still_stopping(self) -> None:
        result, commands = self.run_smoke(
            FAKE_DOCKER_HEALTH="healthy",
            FAKE_DOCKER_STATE="stopping",
            FAKE_HTTP_STATUS="200",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose stop timed out", result.stderr)
        self.assertIn("lifecycle_status=stopping", result.stderr)
        self.assertNotIn(" start lzug", commands)

    def test_timeout_reports_public_http_failure(self) -> None:
        result, _commands = self.run_smoke(
            FAKE_DOCKER_HEALTH="healthy",
            FAKE_HTTP_STATUS="503",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Compose readiness timed out after start", result.stderr)
        self.assertIn("http_status=503", result.stderr)
        self.assertIn("docker_health=healthy", result.stderr)
        self.assertIn("Compose service state:", result.stderr)
        self.assertIn("Compose logs:", result.stderr)
        self.assertIn("fake compose logs", result.stderr)


if __name__ == "__main__":
    unittest.main()
