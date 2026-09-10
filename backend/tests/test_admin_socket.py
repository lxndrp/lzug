"""Real Linux socket, filesystem, peer, process and Go control contract tests."""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.admin import _application
from backend.admin_socket import AdminSocket, SocketConfig, peer_actor
from backend.admin_socket_path import SocketPath, SocketSecurityError
from backend.admin_socket_protocol import read_frame, write_frame
from backend.application.admin import AdminActorContext, AdminApplicationResult
from backend.build_metadata import BuildMetadata
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.persistence.database import initialize, persistence_paths, session_scope
from backend.runtime import RuntimeConflictError, RuntimeCoordinator
from backend.server import initialization_lifespan, main

HELLO = {"type": "hello", "protocol": 1, "schema": 1}
CONFIG = {"version": 1, "command": "config", "arguments": {}}


@unittest.skipUnless(sys.platform == "linux", "Linux kernel credentials and pathname semantics")
class AdminSocketTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "run"
        self.directory.mkdir(mode=0o750)
        self.directory.chmod(0o750)
        self.paths = persistence_paths(data_dir=self.root / "data", environment={})
        self.runtime = RuntimeCoordinator(self.paths.database, lambda: {"ready": True})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.application = _application(paths=self.paths, runtime=self.runtime)
        self.config = SocketConfig(self.directory, os.getegid(), handshake_timeout=0.5)
        self.failure = Mock()
        self.listener = AdminSocket(self.config, self.application, on_failure=self.failure)
        self.addCleanup(self.listener.stop)
        self.audit = io.StringIO()
        redirect = redirect_stdout(self.audit)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def connect(self) -> socket.socket:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(3)
        connection.connect(str(self.directory / "admin.sock"))
        self.addCleanup(connection.close)
        return connection

    def send(self, connection, value):
        write_frame(connection, value, monotonic() + 3)

    def read(self, connection):
        return read_frame(connection, monotonic() + 3, 1024 * 1024)

    def handshake(self, connection):
        self.send(connection, HELLO)
        hello = self.read(connection)
        self.assertEqual("hello", hello["type"])
        return hello

    def request(self, value):
        connection = self.connect()
        hello = self.handshake(connection)
        self.send(connection, value)
        response = self.read(connection)
        self.assertEqual(hello["job_id"], response["job_id"])
        self.assertEqual(hello["correlation_id"], response["correlation_id"])
        connection.close()
        return response

    def drained(self):
        deadline = monotonic() + 3
        while self.listener.snapshot()["active_connections"]:
            self.assertLess(monotonic(), deadline)
            sleep(0.005)

    def test_control_mutation_and_status_share_http_runtime_and_one_process(self):
        initialize(self.paths.database)
        self.listener.start()
        info = (self.directory / "admin.sock").stat()
        self.assertTrue(stat.S_ISSOCK(info.st_mode))
        self.assertEqual(0o660, stat.S_IMODE(info.st_mode))
        result = self.request(
            {
                "version": 1,
                "command": "bootstrap",
                "arguments": {"email": "oberon@demo.lzug.invalid"},
            }
        )
        self.assertEqual(0, result["exit_code"])
        token = result["response"]["result"]["token"]
        with session_scope(self.paths.database) as session:
            self.assertEqual(
                1, session.execute(text("SELECT COUNT(*) FROM user_account")).scalar_one()
            )
        status = self.request(CONFIG)
        self.assertEqual("ready", status["response"]["result"]["runtime"]["state"])
        self.assertEqual(8, status["response"]["result"]["socket"]["max_connections"])
        self.drained()
        events = [json.loads(line) for line in self.audit.getvalue().splitlines()]
        self.assertTrue(any(f"pid:{os.getpid()}:" in event["actor"] for event in events))
        self.assertNotIn(token, self.audit.getvalue())
        self.assertNotIn("oberon@", self.audit.getvalue())

    def test_bad_handshake_never_reaches_application_even_with_pipelined_mutation(self):
        self.listener.start()
        with patch.object(self.application, "execute", side_effect=AssertionError("mutation")):
            for hello in (
                {**HELLO, "protocol": 2},
                {**HELLO, "schema": 2},
                {**HELLO, "schema": True},
                {**HELLO, "actor": "claimed-secret-operator"},
                CONFIG,
            ):
                connection = self.connect()
                self.send(connection, hello)
                self.send(connection, CONFIG)
                result = self.read(connection)
                self.assertEqual("handshake", result["phase"])
                self.assertEqual("version_incompatible", result["code"])
        self.drained()
        self.assertNotIn("claimed-secret", self.audit.getvalue())

    def test_exactly_one_command_per_connection_and_no_lifecycle_or_streaming(self):
        self.listener.start()
        connection = self.connect()
        self.handshake(connection)
        self.send(connection, CONFIG)
        self.send(connection, CONFIG)
        self.assertEqual("result", self.read(connection)["type"])
        try:
            self.assertEqual(b"", connection.recv(1))
        except ConnectionResetError:
            pass
        for command in ("upgrade", "rollback", "backup-create", "secret-invalid-command"):
            response = self.request({**CONFIG, "command": command})
            self.assertEqual("command_unsupported", response["code"])
        self.assertNotIn("secret-invalid", self.audit.getvalue())

    def test_input_limits_duplicates_and_timeout_before_mutation(self):
        self.listener.start()
        with patch.object(self.application, "execute", side_effect=AssertionError("mutation")):
            for payload in (b"{}", b'{"version":1,"version":1}', b'{"x":NaN}', b"[]"):
                connection = self.connect()
                self.handshake(connection)
                connection.sendall(struct.pack("!I", len(payload)) + payload)
                self.assertEqual("validation", self.read(connection)["phase"])
            connection = self.connect()
            self.handshake(connection)
            connection.sendall(struct.pack("!I", 65537))
            self.assertEqual("frame_invalid", self.read(connection)["code"])
            idle = self.connect()
            idle.sendall(b"\x00")
            self.assertEqual(b"", idle.recv(1))
        self.drained()

    def test_untrusted_peer_and_client_actor_claims_cannot_authorize(self):
        self.listener.start()
        with patch(
            "backend.admin_socket.peer_actor", return_value=AdminActorContext("uid:other", False)
        ):
            connection = self.connect()
            self.assertEqual("authorization_failed", self.read(connection)["code"])
        response = self.request({**CONFIG, "actor": {"is_authorized": True}})
        self.assertEqual("request_invalid", response["code"])

    def test_kernel_peer_rejects_foreign_uid_and_gid(self):
        connection = Mock()
        connection.getsockopt.return_value = struct.pack(
            "3i", 123, os.geteuid() + 1, os.getegid() + 1
        )
        self.assertFalse(peer_actor(connection, self.config.gid).is_authorized)
        connection.getsockopt.side_effect = OSError("secret")
        with self.assertRaises(OSError):
            peer_actor(connection, self.config.gid)

    def test_group_peer_is_checked_using_real_linux_credentials(self):
        if os.geteuid() != 0:
            self.skipTest("Changing OS identities requires the isolated root Linux test container")
        self.root.chmod(0o755)
        self.listener.start()
        source = (
            "import socket,sys; s=socket.socket(socket.AF_UNIX); "
            "s.connect(sys.argv[1]); s.sendall(bytes.fromhex(sys.argv[2])); "
            "assert s.recv(4); s.close()"
        )
        payload = json.dumps(HELLO).encode()
        command = [
            sys.executable,
            "-c",
            source,
            str(self.directory / "admin.sock"),
            (struct.pack("!I", len(payload)) + payload).hex(),
        ]
        allowed = subprocess.run(
            command, user=65534, group=os.getegid(), extra_groups=[], capture_output=True
        )
        self.assertEqual(0, allowed.returncode)
        denied = subprocess.run(
            command, user=65534, group=65534, extra_groups=[], capture_output=True
        )
        self.assertNotEqual(0, denied.returncode)
        self.drained()
        self.assertIn("uid:65534:gid:0", self.audit.getvalue())

    def test_supplementary_group_alone_cannot_bypass_kernel_peer_policy(self):
        if os.geteuid() != 0:
            self.skipTest("Changing OS identities requires the isolated root Linux test container")
        self.root.chmod(0o755)
        self.listener.start()
        source = (
            "import socket,struct,json,sys; s=socket.socket(socket.AF_UNIX); "
            "s.connect(sys.argv[1]); n=struct.unpack('!I',s.recv(4))[0]; "
            "r=json.loads(s.recv(n)); assert r['code']=='authorization_failed'"
        )
        result = subprocess.run(
            [sys.executable, "-c", source, str(self.directory / "admin.sock")],
            user=65534,
            group=65534,
            extra_groups=[os.getegid()],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(0, result.returncode)

    def test_foreign_directory_owner_and_group_fail_closed(self):
        if os.geteuid() != 0:
            self.skipTest("Changing ownership requires the isolated root Linux test container")
        try:
            for uid, gid in ((65534, 0), (0, 65534)):
                os.chown(self.directory, uid, gid)
                with self.assertRaises(SocketSecurityError):
                    SocketPath(self.directory, self.config.gid).open()
        finally:
            os.chown(self.directory, os.geteuid(), os.getegid())

    def test_renamed_directory_stays_pinned_and_replacement_is_untouched(self):
        self.listener.start()
        original = self.root / "original"
        self.directory.rename(original)
        self.directory.mkdir(mode=0o750)
        replacement = self.directory / "admin.sock"
        replacement.write_text("keep")
        self.listener.stop()
        self.assertEqual("keep", replacement.read_text())
        self.assertFalse((original / "admin.sock").exists())

    def test_oversize_result_preserves_execution_status_and_never_audits_payload(self):
        self.listener.start()
        large = AdminApplicationResult(
            {"version": 1, "ok": True, "result": {"token": "secret-" * 160000}}, 0
        )
        with patch.object(self.application, "execute", return_value=large):
            result = self.request(CONFIG)
        self.assertEqual("result_too_large", result["code"])
        self.assertEqual("succeeded", result["status"])
        self.assertEqual("transfer", result["phase"])
        self.assertNotIn("secret-", self.audit.getvalue())

    def test_partial_request_expires_without_starting_application(self):
        self.listener.config = replace(self.config, request_timeout=0.1)
        self.listener.start()
        with patch.object(self.application, "execute") as execute:
            connection = self.connect()
            self.handshake(connection)
            connection.sendall(struct.pack("!I", 100) + b"{")
            self.assertEqual(b"", connection.recv(1))
            self.drained()
            execute.assert_not_called()

    def test_foreign_owners_groups_types_modes_and_symlinks_are_preserved(self):
        for kind in ("file", "directory", "symlink", "socket-mode", "socket-group", "socket-owner"):
            with self.subTest(kind=kind):
                candidate = self.directory / "admin.sock"
                if kind == "file":
                    candidate.write_text("keep")
                elif kind == "directory":
                    candidate.mkdir()
                elif kind == "symlink":
                    candidate.symlink_to(self.root / "missing")
                else:
                    with socket.socket(socket.AF_UNIX) as stale:
                        stale.bind(str(candidate))
                    candidate.chmod(0o666 if kind == "socket-mode" else 0o660)
                    if kind in {"socket-group", "socket-owner"}:
                        if os.geteuid() != 0:
                            candidate.unlink()
                            continue
                        os.chown(
                            candidate,
                            65534 if kind == "socket-owner" else 0,
                            65534 if kind == "socket-group" else self.config.gid,
                        )
                inode = candidate.lstat().st_ino
                listener = AdminSocket(self.config, self.application, on_failure=self.failure)
                with self.assertRaises(SocketSecurityError):
                    listener.start()
                self.assertEqual(inode, candidate.lstat().st_ino)
                if kind == "directory":
                    candidate.rmdir()
                else:
                    candidate.unlink()

    def test_directory_checks_reject_symlink_unsafe_parent_and_wrong_leaf(self):
        for mode in (0o777, 0o770, 0o755, 0o700):
            self.directory.chmod(mode)
            with self.assertRaises(SocketSecurityError):
                SocketPath(self.directory, self.config.gid).open()
        self.directory.chmod(0o750)
        link = self.root / "linked"
        link.symlink_to(self.directory)
        with self.assertRaises(SocketSecurityError):
            SocketPath(link, self.config.gid).open()
        self.root.chmod(0o777)
        with self.assertRaises(SocketSecurityError):
            SocketPath(self.directory, self.config.gid).open()
        self.root.chmod(0o700)
        with self.assertRaises(SocketSecurityError):
            SocketPath(self.directory, self.config.gid + 1).open()
        for forbidden in (self.paths.data_dir / "run", self.paths.documents / "run"):
            with self.assertRaises(SocketSecurityError):
                AdminSocket(
                    replace(self.config, directory=forbidden),
                    self.application,
                    on_failure=self.failure,
                )

    def test_owned_stale_socket_replaced_active_socket_and_other_listener_preserved(self):
        candidate = self.directory / "admin.sock"
        with socket.socket(socket.AF_UNIX) as stale:
            stale.bind(str(candidate))
        candidate.chmod(0o660)
        self.listener.start()
        self.assertEqual("result", self.request(CONFIG)["type"])
        other = AdminSocket(self.config, self.application, on_failure=self.failure)
        with self.assertRaises(SocketSecurityError):
            other.start()
        self.assertEqual("result", self.request(CONFIG)["type"])
        self.listener.stop()
        with socket.socket(socket.AF_UNIX) as active:
            active.bind(str(candidate))
            candidate.chmod(0o660)
            active.listen()
            with self.assertRaises(SocketSecurityError):
                AdminSocket(self.config, self.application, on_failure=self.failure).start()
            self.assertTrue(candidate.exists())

    def test_cleanup_preserves_replacement_inode(self):
        self.listener.start()
        candidate = self.directory / "admin.sock"
        candidate.unlink()
        candidate.write_text("keep replacement")
        self.listener.stop()
        self.assertEqual("keep replacement", candidate.read_text())

    def test_bounded_workers_and_history(self):
        self.listener.config = replace(self.config, max_connections=8, history_size=8)
        self.listener.start()
        held = []
        for _ in range(8):
            connection = self.connect()
            self.handshake(connection)
            held.append(connection)
        rejected = self.connect()
        self.assertEqual(b"", rejected.recv(1))
        self.assertEqual(8, self.listener.snapshot()["active_connections"])
        for connection in held:
            connection.close()
        self.drained()
        for _ in range(12):
            self.request(CONFIG)
            self.drained()
        self.assertLessEqual(len(self.listener._jobs), 8)

    def test_disconnect_and_shutdown_retain_running_mutation_no_replay(self):
        self.listener.config = replace(self.config, shutdown_timeout=0.01)
        self.listener.start()
        entered, release = Event(), Event()
        original = self.application.execute

        def delayed(request, actor):
            with self.runtime.admit():
                entered.set()
                if not release.wait(5):
                    raise AssertionError("not released")
                return original(request, actor)

        with patch.object(self.application, "execute", side_effect=delayed) as execute:
            connection = self.connect()
            hello = self.handshake(connection)
            self.send(connection, CONFIG)
            self.assertTrue(entered.wait(3))
            connection.close()
            try:
                with self.assertRaises(TimeoutError):
                    self.listener.stop()
                with self.assertRaises(RuntimeConflictError):
                    self.runtime.stop(timeout=0)
                self.assertIsNotNone(self.listener.path.fd)
            finally:
                release.set()
            self.drained()
            self.listener.stop()
            self.assertEqual(1, execute.call_count)
        job = self.listener._jobs[hello["job_id"]]
        self.assertEqual("succeeded", job["status"])
        self.assertEqual("lost", job["delivery"])

    def test_lost_result_can_be_queried_without_storing_sensitive_results(self):
        self.listener.start()
        result = self.request(CONFIG)
        self.drained()
        status = self.request(
            {
                "version": 1,
                "command": "socket-job-status",
                "arguments": {"job_id": result["job_id"]},
            }
        )
        job = status["response"]["result"]
        self.assertEqual("succeeded", job["status"])
        self.assertNotIn("response", job)
        self.assertNotIn("arguments", job)

    def test_runtime_not_ready_remains_diagnosable_and_rejects_mutation(self):
        self.listener.start()
        self.runtime.stop()
        self.assertEqual("stopped", self.request(CONFIG)["response"]["result"]["runtime"]["state"])
        result = self.request({"version": 1, "command": "invite", "arguments": {"email": "secret"}})
        self.assertEqual("lifecycle", result["phase"])
        self.assertEqual(21, result["exit_code"])

    def test_listener_error_invokes_failure_once_and_does_not_restart(self):
        self.listener.start()
        self.listener._listener.close()
        self.listener._thread.join(3)
        self.assertFalse(self.listener._thread.is_alive())
        self.failure.assert_called_once_with()
        self.assertEqual("failed", self.listener.snapshot()["state"])

    def test_server_assembly_owns_http_and_socket_and_cleans_up_after_http_failure(self):
        initialize(self.paths.database)
        self.runtime.stop()
        args = argparse.Namespace(
            paths=self.paths,
            db=self.paths.database,
            init=False,
            reset=False,
            host="127.0.0.1",
            port=8000,
            static_dir=None,
            admin_socket=self.config,
        )
        entered, release = Event(), Event()

        def prepare(_args):
            entered.set()
            self.assertTrue(release.wait(10))

        original_stop = RuntimeCoordinator.stop

        def stop(runtime, **kwargs):
            self.assertFalse((self.directory / "admin.sock").exists())
            return original_stop(runtime, **kwargs)

        def run(app, **_kwargs):
            with TestClient(app) as client:
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertEqual(503, client.get("/api/ready").status_code)
                    result = self.request(CONFIG)
                    self.assertEqual(
                        "initializing", result["response"]["result"]["runtime"]["state"]
                    )
                finally:
                    release.set()
                deadline = monotonic() + 5
                while not app.state.runtime.snapshot()["ready"]:
                    self.assertLess(monotonic(), deadline)
                    sleep(0.005)
                self.assertEqual(200, client.get("/api/ready").status_code)
                result = self.request(CONFIG)
                self.assertEqual(
                    app.state.runtime.diagnosis(), result["response"]["result"]["runtime"]
                )
            raise RuntimeError("HTTP test stop")

        with (
            patch("backend.server.parse_args", return_value=args),
            patch("backend.server.prepare_database", side_effect=prepare),
            patch("backend.server.uvicorn.run", side_effect=run) as http,
            patch("backend.version.build_metadata", return_value=BuildMetadata.create("1" * 40)),
            patch.object(RuntimeCoordinator, "stop", stop),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP test stop"):
                main()
            http.assert_called_once()
        self.assertFalse((self.directory / "admin.sock").exists())
        self.runtime.start()

    def test_lifespan_socket_drain_timeout_keeps_ownership_without_runtime_admission(self):
        self.runtime.stop()
        self.runtime.claim()
        self.listener.config = replace(self.config, shutdown_timeout=0.01)
        self.listener.start()
        with patch("backend.version.build_metadata", return_value=BuildMetadata.create("1" * 40)):
            app = create_app(
                FastAPIConfig(db_path=self.paths.database, session_cookie_name="session"),
                runtime=self.runtime,
            )
        app.router.lifespan_context = initialization_lifespan(
            self.runtime, None, admin_socket=self.listener
        )
        entered, release = Event(), Event()
        original = self.application.execute

        def delayed(request, actor):
            # Diagnostics need no runtime lease, but their socket worker still owns work.
            entered.set()
            self.assertTrue(release.wait(10))
            return original(request, actor)

        with patch.object(self.application, "execute", side_effect=delayed):
            try:
                with self.assertRaises(TimeoutError), TestClient(app):
                    deadline = monotonic() + 5
                    while not self.runtime.snapshot()["ready"]:
                        self.assertLess(monotonic(), deadline)
                        sleep(0.005)
                    connection = self.connect()
                    self.handshake(connection)
                    self.send(connection, CONFIG)
                    self.assertTrue(entered.wait(5))
                self.assertIsNotNone(self.listener.path.fd)
                contender = RuntimeCoordinator(self.paths.database, lambda: {"ready": True})
                with self.assertRaises(RuntimeConflictError):
                    contender.claim()
            finally:
                release.set()
            self.drained()
        self.listener.stop()
        self.runtime.stop()

    def test_real_go_adapter_against_authoritative_linux_backend(self):
        initialize(self.paths.database)
        self.listener.start()
        environment = {**os.environ, "LZUG_SOCKET_TEST_PATH": str(self.directory / "admin.sock")}
        binary = os.environ.get("LZUG_SOCKET_TEST_BINARY")
        command = (
            [binary, "-test.run=^TestSocketLive$", "-test.v"]
            if binary
            else ["go", "test", "./internal/admincli", "-run", "^TestSocketLive$", "-count=1", "-v"]
        )
        result = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2] / "operator-cli",
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("PASS: TestSocketLive", result.stdout)
        with session_scope(self.paths.database) as session:
            self.assertEqual(
                1, session.execute(text("SELECT COUNT(*) FROM user_account")).scalar_one()
            )


if __name__ == "__main__":
    unittest.main()
