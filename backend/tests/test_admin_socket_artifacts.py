"""Linux streaming, bounded resources, interruption and authoritative restore tests."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from backend.admin_socket_artifacts import StreamWriter
from backend.admin_socket_protocol import (
    DATA_FRAME_TAG,
    MAX_DATA_BYTES,
    SocketProtocolError,
    read_stream_frame,
    write_data,
)
from backend.identity.local_auth import authentication_key
from backend.operations.backup_restore import ArtifactError
from backend.persistence.database import activation_scope, initialize
from backend.runtime import RuntimeConflictError
from backend.tests import test_admin_socket as control

FINGERPRINT = "sha256:" + "a" * 64
CREATE = {
    "version": 1,
    "command": "backup-package-create",
    "arguments": {"recipient_key_fingerprint": FINGERPRINT},
}
VERIFY = {
    "version": 1,
    "command": "artifact-package-verify",
    "arguments": {"artifact_type": "backup"},
}
RESTORE = {
    "version": 1,
    "command": "backup-package-restore",
    "arguments": {
        "recipient_key_fingerprint": FINGERPRINT,
        "replace": True,
        "safety_artifact": "safety.lzug",
    },
}
SERVICE = "backend.admin_socket_artifacts.ClearArtifactService"


@unittest.skipUnless(sys.platform == "linux", "Linux authoritative socket assembly")
class SocketArtifactTests(unittest.TestCase):
    setUp = control.AdminSocketTests.setUp
    connect = control.AdminSocketTests.connect
    send = control.AdminSocketTests.send
    read = control.AdminSocketTests.read
    handshake = control.AdminSocketTests.handshake
    request = control.AdminSocketTests.request
    drained = control.AdminSocketTests.drained

    def start(self, *, limit=1024 * 1024, timeout=3):
        self.listener.config = replace(self.config, max_stream_bytes=limit, stream_timeout=timeout)
        self.listener.artifacts.limit = limit
        self.listener.start()

    def begin(self, request=VERIFY):
        connection = self.connect()
        hello = self.handshake(connection)
        self.send(connection, request)
        ready = self.read(connection)
        self.assertEqual("stream-ready", ready["type"])
        self.assertEqual(hello["job_id"], ready["job_id"])
        return connection, hello["job_id"]

    def finish(self, connection, content):
        self.send(
            connection,
            {
                "type": "stream-end",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        connection.shutdown(socket.SHUT_WR)

    def clean(self):
        self.drained()
        self.assertEqual([], list(self.paths.backups.glob(".lzug-*")))

    def test_real_go_age_backup_export_verify_restore(self):
        initialize(self.paths.database)
        authentication_key(self.paths.database)
        self.start(limit=64 * 1024 * 1024, timeout=30)
        binary = os.environ.get("LZUG_SOCKET_TEST_BINARY")
        result = subprocess.run(
            (
                [binary, "-test.run=^TestSocketArtifactsLive$", "-test.v"]
                if binary
                else [
                    "go",
                    "test",
                    "./internal/admincli",
                    "-run",
                    "^TestSocketArtifactsLive$",
                    "-count=1",
                    "-v",
                ]
            ),
            cwd=Path(__file__).resolve().parents[2] / "operator-cli",
            env={
                **os.environ,
                "LZUG_SOCKET_ARTIFACT_TEST_PATH": str(self.directory / "admin.sock"),
            },
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.drained()
        self.assertEqual(
            0,
            result.returncode,
            result.stdout + result.stderr + json.dumps(list(self.listener._jobs.values())),
        )
        self.assertIn("PASS: TestSocketArtifactsLive", result.stdout)
        self.clean()
        self.assertNotIn("AGE-SECRET-KEY-", self.audit.getvalue())
        self.assertEqual("ready", self.runtime.snapshot()["state"])

    def test_partial_upload_eof_never_executes_and_is_diagnosable(self):
        self.start()
        with patch(SERVICE + ".restore_package") as restore:
            connection, job_id = self.begin(RESTORE)
            write_data(connection, b"partial-secret-content", monotonic() + 3)
            connection.shutdown(socket.SHUT_WR)
            self.clean()
            restore.assert_not_called()
            job = self.request(
                {"version": 1, "command": "socket-job-status", "arguments": {"job_id": job_id}}
            )["response"]["result"]
            self.assertEqual("rejected", job["status"])
            self.assertEqual("upload", job["phase"])
            self.assertEqual("connection_lost", job["code"])
            self.assertNotIn("partial-secret-content", self.audit.getvalue())

    def test_invalid_control_data_boundary_and_end_reject_before_execution(self):
        self.start(limit=16)
        with patch(SERVICE + ".verify_package") as verify:
            for wire in (
                struct.pack("!I", DATA_FRAME_TAG),
                struct.pack("!I", DATA_FRAME_TAG | (MAX_DATA_BYTES + 1)),
                struct.pack("!I", 1025),
                struct.pack("!I", DATA_FRAME_TAG | 17) + b"x" * 17,
            ):
                connection, _ = self.begin()
                connection.sendall(wire)
                self.assertIn(
                    self.read(connection)["code"], {"stream_frame_invalid", "stream_limit_exceeded"}
                )
                connection.close()
                self.clean()
            for end in (
                {"type": "stream-end", "bytes": 1, "sha256": "bad"},
                {"type": "stream-end", "bytes": True, "sha256": hashlib.sha256(b"x").hexdigest()},
                {"type": "stream-end", "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
                {"type": "abort"},
            ):
                connection, _ = self.begin()
                write_data(connection, b"x", monotonic() + 3)
                self.send(connection, end)
                connection.shutdown(socket.SHUT_WR)
                self.assertEqual("stream_incomplete", self.read(connection)["code"])
                connection.close()
                self.clean()
            connection, _ = self.begin()
            write_data(connection, b"x", monotonic() + 3)
            self.send(
                connection,
                {"type": "stream-end", "bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()},
            )
            connection.sendall(b"trailing")
            self.assertEqual("stream_frame_invalid", self.read(connection)["code"])
            connection.close()
            self.clean()
            verify.assert_not_called()

    def test_upload_absolute_deadline_and_exclusive_artifact_slot(self):
        self.start(timeout=0.15)
        with patch(SERVICE + ".verify_package") as verify:
            connection, job_id = self.begin()
            self.assertEqual("artifact_busy", self.request(VERIFY)["code"])
            self.assertTrue(self.request(control.CONFIG)["response"]["ok"])
            started = monotonic()
            while monotonic() - started < 0.4:
                try:
                    write_data(connection, b"x", monotonic() + 1)
                except OSError:
                    break
                sleep(0.03)
            self.clean()
            self.assertLess(monotonic() - started, 0.5)
            self.assertEqual("timeout", self.listener._jobs[job_id]["code"])
            verify.assert_not_called()
            # The permit is released, even after timeout and cleanup.
            other, _ = self.begin()
            other.close()
            self.clean()

    def test_continuing_producer_is_bounded_and_backpressured(self):
        self.start(limit=MAX_DATA_BYTES * 4, timeout=0.15)
        writes = []

        def produce(output, fingerprint):
            while True:
                output.write(b"z" * MAX_DATA_BYTES)
                writes.append(1)

        with patch(SERVICE + ".write_backup_package", side_effect=produce):
            connection, _ = self.begin(CREATE)
            count = 0
            while True:
                frame = read_stream_frame(connection, monotonic() + 3)
                if isinstance(frame, dict):
                    self.assertEqual("stream_limit_exceeded", frame["code"])
                    break
                count += len(frame)
            self.assertEqual(MAX_DATA_BYTES * 4, count)
            self.assertEqual(4, len(writes))
            self.clean()

        self.listener.artifacts.limit = 32 * 1024 * 1024
        writes.clear()
        with patch(SERVICE + ".write_backup_package", side_effect=produce):
            connection, job_id = self.begin(CREATE)
            # A non-reader cannot cause buffering of the remaining 32 MiB.
            self.clean()
            self.assertLess(len(writes), 32)
            self.assertEqual("lost", self.listener._jobs[job_id]["delivery"])

    def test_large_download_has_bounded_frames_and_matching_digest(self):
        limit = 32 * 1024 * 1024
        self.start(limit=limit, timeout=10)

        def produce(output, fingerprint):
            for _ in range(limit // MAX_DATA_BYTES):
                output.write(b"z" * MAX_DATA_BYTES)
            return {"artifact_id": "test"}

        with patch(SERVICE + ".write_backup_package", side_effect=produce):
            connection, _ = self.begin(CREATE)
            digest, count = hashlib.sha256(), 0
            while True:
                frame = read_stream_frame(connection, monotonic() + 10)
                if isinstance(frame, dict):
                    self.assertEqual("stream-end", frame["type"])
                    self.assertEqual(count, frame["bytes"])
                    self.assertEqual(digest.hexdigest(), frame["sha256"])
                    break
                self.assertLessEqual(len(frame), MAX_DATA_BYTES)
                count += len(frame)
                digest.update(frame)
            self.assertEqual(limit, count)
            self.assertTrue(self.read(connection)["response"]["ok"])
            self.clean()

    def test_admitted_restore_keeps_runtime_until_completion_after_result_loss(self):
        self.start()
        entered, release = Event(), Event()

        def restore(*args, **kwargs):
            with activation_scope(self.paths.database):
                entered.set()
                self.assertTrue(release.wait(3))
                return {"artifact_id": "test"}

        with patch(SERVICE + ".restore_package", side_effect=restore) as execute:
            connection, job_id = self.begin(RESTORE)
            write_data(connection, b"complete", monotonic() + 3)
            self.finish(connection, b"complete")
            self.assertTrue(entered.wait(2))
            connection.close()
            try:
                with self.assertRaises(RuntimeConflictError):
                    with self.runtime.admit():
                        pass
                self.assertEqual("artifact_busy", self.request(VERIFY)["code"])
            finally:
                release.set()
            self.clean()
            execute.assert_called_once()
        job = self.request(
            {"version": 1, "command": "socket-job-status", "arguments": {"job_id": job_id}}
        )["response"]["result"]
        self.assertEqual("succeeded", job["status"])
        self.assertEqual("lost", job["delivery"])

    def test_private_identity_arguments_and_malformed_requests_fail_closed(self):
        self.start()
        for arguments in (
            {**CREATE["arguments"], "identity": "AGE-SECRET-KEY-DO-NOT-LOG"},
            {"recipient_key_fingerprint": "AGE-SECRET-KEY-DO-NOT-LOG"},
            {"recipient_key_fingerprint": []},
        ):
            self.assertEqual(
                "request_invalid", self.request({**CREATE, "arguments": arguments})["code"]
            )
        self.assertNotIn("AGE-SECRET-KEY-", self.audit.getvalue())

    def test_cleanup_failure_blocks_further_artifacts_but_keeps_diagnosis(self):
        self.start()
        with patch(
            SERVICE + ".write_backup_package",
            side_effect=ArtifactError("artifact_cleanup_failed", "Cleanup failed", phase="cleanup"),
        ):
            connection, _ = self.begin(CREATE)
            response = self.read(connection)
            self.assertFalse(response["response"]["ok"])
            self.assertEqual("artifact_cleanup_failed", response["response"]["error"]["class"])
        self.drained()
        self.assertEqual("artifact_cleanup_required", self.request(CREATE)["code"])
        self.assertTrue(
            self.request(control.CONFIG)["response"]["result"]["socket"][
                "artifact_cleanup_required"
            ]
        )


class StreamWriterTests(unittest.TestCase):
    def test_oversize_write_rejected_before_any_output(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        writer = StreamWriter(left, monotonic() + 1, 3)
        with self.assertRaises(SocketProtocolError):
            writer.write(b"four")
        self.assertEqual(0, writer.count)
        right.setblocking(False)
        with self.assertRaises(BlockingIOError):
            right.recv(1)


@unittest.skipUnless(sys.platform == "linux", "Linux authoritative migration socket")
class SocketMigrationTests(unittest.TestCase):
    connect = SocketArtifactTests.connect
    send = SocketArtifactTests.send
    read = SocketArtifactTests.read
    handshake = SocketArtifactTests.handshake
    request = SocketArtifactTests.request
    drained = SocketArtifactTests.drained
    begin = SocketArtifactTests.begin
    finish = SocketArtifactTests.finish
    clean = SocketArtifactTests.clean
    start = SocketArtifactTests.start

    # Keep only dedicated migration cases; inherited generic artifact cases stay
    # in SocketArtifactTests and use their own ready-runtime setup.
    def setUp(self):
        control.AdminSocketTests.setUp(self)

    def pending(self, recipient=None):
        import sqlite3
        from contextlib import closing

        from backend.build_metadata import BuildMetadata
        from backend.operations.backup_recipients import (
            BackupRecipientRepository,
            recipient_fingerprint,
        )
        from backend.persistence.database import database_readiness
        from backend.tests.test_backup_recipients import RECIPIENT

        self.runtime.stop()
        initialize(self.paths.database)
        authentication_key(self.paths.database)
        recipient = recipient or RECIPIENT
        self.fingerprint = recipient_fingerprint(recipient)
        BackupRecipientRepository(self.paths.database).set(recipient, self.fingerprint)
        with closing(sqlite3.connect(self.paths.database)) as db, db:
            db.execute("DELETE FROM schema_migration_checksum WHERE name LIKE '028_%'")
            db.execute("DELETE FROM schema_migration WHERE name LIKE '028_%'")
        self.runtime._probe = lambda: database_readiness(self.paths.database)
        self.runtime.start()
        lifecycle = self.listener.artifacts.lifecycle
        lifecycle.metadata = BuildMetadata.create("a" * 40, "v0.9.0")
        self.application.services = replace(
            self.application.services, lifecycle_factory=lambda _: lifecycle
        )
        self.plan = lifecycle.status()["plan_id"]
        self.create = {**CREATE, "arguments": {"recipient_key_fingerprint": self.fingerprint}}
        self.apply = {
            "version": 1,
            "command": "upgrade-package-apply",
            "arguments": {
                "plan_id": self.plan,
                "recipient_key_fingerprint": self.fingerprint,
                "confirm_irreversible": True,
            },
        }
        self.start(limit=64 * 1024 * 1024, timeout=30)

    def backup_bytes(self):
        connection, _job_id = self.begin(self.create)
        data = bytearray()
        while True:
            frame = read_stream_frame(connection, monotonic() + 30)
            if isinstance(frame, bytes):
                data.extend(frame)
            else:
                self.assertEqual("stream-end", frame["type"])
                break
        result = self.read(connection)
        self.assertTrue(result["response"]["ok"], result)
        connection.close()
        self.drained()
        return bytes(data)

    def upload(self, content):
        connection, job_id = self.begin(self.apply)
        for offset in range(0, len(content), MAX_DATA_BYTES):
            write_data(connection, content[offset : offset + MAX_DATA_BYTES], monotonic() + 30)
        self.finish(connection, content)
        return connection, job_id

    def test_migration_disconnect_keeps_durable_job_and_never_replays(self):
        from backend.persistence.database import apply_migrations

        self.pending()
        content = self.backup_bytes()
        entered, release = Event(), Event()
        calls = []

        def migrate(database, backups):
            calls.append(os.getpid())
            entered.set()
            if not release.wait(10):
                raise AssertionError("test release missing")
            apply_migrations(database, backups)

        self.listener.artifacts.lifecycle.migration_runner = migrate
        connection, job_id = self.upload(content)
        self.assertTrue(entered.wait(5))
        connection.close()
        self.assertFalse(self.runtime.snapshot()["ready"])
        self.assertEqual(job_id, self.runtime.snapshot()["job"]["id"])
        release.set()
        self.drained()
        self.assertTrue(self.runtime.snapshot()["ready"])
        self.assertEqual([os.getpid()], calls)
        # A repeated mutation stream is rejected by state/evidence, never replayed.
        connection, _ = self.upload(content)
        self.assertFalse(self.read(connection)["response"]["ok"])
        connection.close()
        self.drained()
        self.assertEqual([os.getpid()], calls)
        self.listener._jobs.clear()
        self.runtime.stop()
        self.runtime.start()
        result = self.request(
            {"version": 1, "command": "socket-job-status", "arguments": {"job_id": job_id}}
        )
        self.assertEqual("succeeded", result["response"]["result"]["status"])
        self.assertNotIn("AGE-SECRET", self.audit.getvalue())

    def test_incomplete_upload_never_authorizes_migration(self):
        self.pending()
        content = self.backup_bytes()
        connection, _ = self.begin(self.apply)
        write_data(connection, content[:100], monotonic() + 5)
        connection.shutdown(socket.SHUT_WR)
        with self.assertRaises(ConnectionError):
            self.read(connection)
        connection.close()
        self.drained()
        self.assertEqual("migration_required", self.runtime.snapshot()["state"])
        self.assertIsNone(self.runtime.snapshot()["job"])
        self.clean()

    def test_real_go_cli_backup_approval_migration_and_job_lookup(self):
        directory = self.root / "operator"
        directory.mkdir()
        binary = os.environ.get("LZUG_SOCKET_TEST_BINARY")
        command = (
            [binary, "-test.run=^TestSocketMigrationLive$", "-test.v"]
            if binary
            else [
                "go",
                "test",
                "./internal/admincli",
                "-run",
                "^TestSocketMigrationLive$",
                "-count=1",
                "-v",
            ]
        )
        environment = {
            **os.environ,
            "LZUG_MIGRATION_TEST_DIRECTORY": str(directory),
            "LZUG_MIGRATION_TEST_ENDPOINT": "",
        }

        def invoke():
            result = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[2] / "operator-cli",
                env=environment,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        invoke()
        self.pending((directory / "recipient").read_text().strip())
        environment["LZUG_MIGRATION_TEST_ENDPOINT"] = "unix://" + str(self.directory / "admin.sock")
        invoke()
        self.assertTrue(self.runtime.snapshot()["ready"])
        self.assertEqual("succeeded", self.runtime.snapshot()["job"]["status"])
        self.assertNotIn((directory / "identity").read_text().strip(), self.audit.getvalue())
        self.clean()
