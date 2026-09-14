from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

FAKE_DOCKER = r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["ENGINE_LOG"], "a") as stream:
    stream.write(json.dumps(args) + "\n")
if args[:2] == ["image", "inspect"]:
    print("amd64")
elif args[0] == "inspect":
    print("Backend state=running exit=0 oom=false user=10001:10001 readonly=true")
elif args[0] == "logs":
    print("backend.admin_socket_path.SocketSecurityError: invitation-token-sentinel")
elif args[0] == "exec":
    if args[-3:] == ["sh", "-c", "command -v go"]:
        sys.exit(1)
    elif "/usr/local/bin/lzug-admin" in args:
        if "cli" in args:
            print("Sitzung beendet.")
        elif "--build-metadata" in args:
            print("{}")
        else:
            print(json.dumps({"schema_version": 1, "protocol_version": 1, "exit_code": 0, "ok": True}))
    elif args[-2:] == ["id", "-u"]:
        print("10001")
    elif args[-1] == "/app/backend/src/build-metadata.json":
        print("{}")
    elif args[-2] == "-c":
        print("admin.sock: uid=10001 gid=10001 mode=0660 socket=True")
elif args[0] == "run" and "--entrypoint" in args:
    entrypoint = args[args.index("--entrypoint") + 1]
    if entrypoint == "sh":
        sys.exit(int(os.environ.get("SETUP_EXIT", "0")))
    cli = args[args.index("--entrypoint") + 3:]
    if cli[:2] == ["recipient-key", "generate"]:
        Path(cli[cli.index("--identity-file") + 1]).write_text("AGE-SECRET-KEY-SENTINEL\n")
        Path(cli[cli.index("--recipient-file") + 1]).write_text("age1public\n")
    elif cli == ["--build-metadata"]:
        print("{}")
    else:
        code, error = (2, "invalid_invocation") if "apply" in cli else (11, "connection_failed")
        if "rollback" in cli:
            code = int(os.environ.get("ROLLBACK_EXIT", "11"))
            error = "rollback_not_supported" if code == 28 else "connection_failed"
        payload = {"schema_version": 1, "protocol_version": 1, "exit_code": code,
                   "ok": False, "error": {"class": error, "phase": "connect",
                   "message": "invitation-token-sentinel member@example.invalid"}}
        if "rollback" in cli and os.environ.get("BAD_JSON"):
            print("invalid JSON invitation-token-sentinel")
        else:
            print(json.dumps(payload))
        print("stderr invitation-token-sentinel", file=sys.stderr)
        if os.environ.get("LEAK_KEY") and "rollback" in cli:
            print("AGE-SECRET-KEY-SENTINEL", file=sys.stderr)
        sys.exit(code)
"""


class OperatorSmokeTests(unittest.TestCase):
    def run_smoke(self, **overrides: str) -> tuple[subprocess.CompletedProcess[str], list]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / "docker"
            docker.write_text(textwrap.dedent(FAKE_DOCKER))
            docker.chmod(0o755)
            log = root / "engine.log"
            env = dict(
                os.environ,
                PATH=f"{root}:{os.environ['PATH']}",
                ENGINE_LOG=str(log),
            )
            env.update(overrides)
            result = subprocess.run(
                ["sh", "scripts/operator-container-smoke.sh", "fixture:image"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            import json

            commands = [json.loads(line) for line in log.read_text().splitlines()]
            return result, commands

    def test_missing_socket_reports_boundary_expected_actual_and_safe_error(self) -> None:
        result, commands = self.run_smoke()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "stage=reject rollback through live admin socket expected=28 actual=11", result.stderr
        )
        self.assertIn("CLI error.class=connection_failed", result.stderr)
        self.assertIn("CLI error.phase=connect", result.stderr)
        self.assertIn("Reproduce:", result.stderr)
        self.assertIn("Backend state=running", result.stderr)
        self.assertIn(
            "Backend exception=backend.admin_socket_path.SocketSecurityError", result.stderr
        )
        self.assertIn("mode=0660", result.stderr)
        self.assertNotIn("invitation-token-sentinel", result.stderr)
        self.assertNotIn("member@example.invalid", result.stderr)
        self.assertNotIn("AGE-SECRET-KEY-SENTINEL", result.stderr)
        for cmd in commands:
            for argument in cmd:
                if "target=/run/lzug-admin" in argument:
                    self.assertIn("volume-nocopy", argument)
        backend = next(cmd for cmd in commands if "--detach" in cmd)
        self.assertIn("--admin-socket-dir", backend)
        self.assertIn("--admin-socket-gid", backend)
        direct = next(
            cmd for cmd in commands if cmd[0] == "exec" and "/usr/local/bin/lzug-admin" in cmd
        )
        self.assertIn("--user", direct)
        self.assertIn("10001:10001", direct)
        for cmd in commands:
            if "--interactive" in cmd:
                expected_user = "10001:10001" if cmd[0] == "exec" else f"{os.getuid()}:10001"
                self.assertIn(expected_user, cmd)
                if cmd[0] == "run" and "--endpoint" in cmd:
                    self.assertIn("--pid", cmd)
                    self.assertIn("container:" + backend[backend.index("--name") + 1], cmd)
                if cmd[0] == "run":
                    if "recipient-key" in cmd:
                        self.assertNotIn("--pid", cmd)
                    self.assertIn("no-new-privileges:true", cmd)
                    self.assertIn("--read-only", cmd)
                    self.assertIn("none", cmd)
                    self.assertFalse(any("target=/data" in arg for arg in cmd))
                    self.assertTrue(any("target=/run/lzug-admin,readonly" in arg for arg in cmd))
        self.assertTrue(any(cmd[:2] == ["rm", "--force"] for cmd in commands))

    def test_malformed_response_reports_json_failure_without_raw_payload(self) -> None:
        result, _ = self.run_smoke(ROLLBACK_EXIT="28", BAD_JSON="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stage=reject rollback through live admin socket", result.stderr)
        self.assertIn("CLI response: invalid JSON", result.stderr)
        self.assertNotIn("invitation-token-sentinel", result.stderr)

    def test_private_key_in_suppressed_stderr_still_fails(self) -> None:
        result, _ = self.run_smoke(ROLLBACK_EXIT="28", LEAK_KEY="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected=28 actual=1", result.stderr)
        self.assertNotIn("AGE-SECRET-KEY-SENTINEL", result.stderr)

    def test_setup_failure_has_stage_preserves_exit_and_cleans_up(self) -> None:
        result, commands = self.run_smoke(SETUP_EXIT="42")
        self.assertEqual(result.returncode, 42)
        self.assertIn("stage=prepare private socket volume exit=42", result.stderr)
        self.assertFalse(any("--detach" in cmd for cmd in commands))
        self.assertTrue(any(cmd[:2] == ["volume", "rm"] for cmd in commands))


if __name__ == "__main__":
    unittest.main()
