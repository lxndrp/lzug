"""Deterministic concurrency and restart contracts for runtime ownership."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import patch

from sqlalchemy import text

from backend.persistence.database import (
    activation_scope,
    apply_migrations,
    database_readiness,
    initialize,
    session_scope,
    snapshot_scope,
)
from backend.runtime import Operation, RuntimeConflictError, RuntimeCoordinator


class RuntimeCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / "lzug.sqlite"
        self.runtime = RuntimeCoordinator(self.database, lambda: database_readiness(self.database))
        self.addCleanup(self.runtime.stop)
        self.runtime.start(lambda: initialize(self.database))
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.addCleanup(self.pool.shutdown)

    def wait_for(self, predicate) -> None:
        deadline = monotonic() + 5
        while not predicate():
            if monotonic() >= deadline:
                self.fail(f"Timed out: {self.runtime.snapshot()}")
            Event().wait(0.005)

    def hold_transaction(self, entered: Event, release: Event) -> None:
        with session_scope(self.database) as session:
            session.execute(text("SELECT 1"))
            entered.set()
            if not release.wait(5):
                raise AssertionError("transaction was not released")

    def test_restore_and_migration_drain_http_and_reject_new_work(self) -> None:
        for operation in Operation:
            with self.subTest(operation=operation):
                entered, release, started, finish = Event(), Event(), Event(), Event()
                transaction = self.pool.submit(self.hold_transaction, entered, release)
                self.assertTrue(entered.wait(5))

                def maintain(operation=operation, started=started, finish=finish):
                    with self.runtime.operation(operation):
                        started.set()
                        self.assertTrue(finish.wait(5))

                maintenance = self.pool.submit(maintain)
                try:
                    self.wait_for(
                        lambda: self.runtime.snapshot()["job"] is not None
                        and self.runtime.snapshot()["job"]["status"] == "waiting"
                    )
                    self.assertFalse(started.is_set())
                    with self.assertRaises(RuntimeConflictError), session_scope(self.database):
                        self.fail("new transaction was admitted")
                    release.set()
                    transaction.result(5)
                    self.assertTrue(started.wait(5))
                    for competing in Operation:
                        with self.assertRaises(RuntimeConflictError):
                            with self.runtime.operation(competing):
                                self.fail("competing job was admitted")
                    self.assertFalse(self.runtime.snapshot()["ready"])
                finally:
                    release.set()
                    finish.set()
                maintenance.result(5)
                self.assertTrue(self.runtime.snapshot()["ready"])
                self.assertEqual("succeeded", self.runtime.snapshot()["job"]["status"])

    def test_service_entry_points_share_the_conflict_matrix(self) -> None:
        for operation in Operation:
            entered, release = Event(), Event()

            def maintain(operation=operation, entered=entered, release=release):
                if operation == Operation.RESTORE:
                    with activation_scope(self.database):
                        entered.set()
                        self.assertTrue(release.wait(5))
                else:

                    def migration(*_args):
                        entered.set()
                        self.assertTrue(release.wait(5))

                    with patch(
                        "backend.persistence.database._apply_migrations_unlocked", migration
                    ):
                        apply_migrations(self.database)

            maintenance = self.pool.submit(maintain)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(operation.value, self.runtime.snapshot()["job"]["operation"])
                for scope in (session_scope, snapshot_scope, activation_scope):
                    with self.assertRaises(RuntimeConflictError), scope(self.database):
                        self.fail("conflicting service was admitted")
                with self.assertRaises(RuntimeConflictError):
                    apply_migrations(self.database)
            finally:
                release.set()
            maintenance.result(5)

    def test_waiting_job_can_be_cancelled_without_cancelling_transaction(self) -> None:
        entered, release = Event(), Event()
        transaction = self.pool.submit(self.hold_transaction, entered, release)
        self.assertTrue(entered.wait(5))

        def maintain():
            with self.runtime.operation(Operation.RESTORE):
                self.fail("cancelled job was executed")

        maintenance = self.pool.submit(maintain)
        try:
            self.wait_for(lambda: self.runtime.snapshot()["job"]["status"] == "waiting")
            job = self.runtime.snapshot()["job"]
            self.assertTrue(self.runtime.cancel(job["id"]))
            with self.assertRaises(RuntimeConflictError):
                maintenance.result(5)
            self.assertEqual(1, self.runtime.snapshot()["active"])
            self.assertEqual("cancelled", self.runtime.snapshot()["job"]["status"])
        finally:
            release.set()
        transaction.result(5)

    def test_drain_timeout_never_runs_the_job(self) -> None:
        entered, release = Event(), Event()
        transaction = self.pool.submit(self.hold_transaction, entered, release)
        self.assertTrue(entered.wait(5))
        try:
            with self.assertRaises(RuntimeConflictError) as raised:
                with self.runtime.operation(Operation.MIGRATION, timeout=0):
                    self.fail("timed out job was executed")
            self.assertEqual("drain_timeout", raised.exception.code)
            self.assertTrue(self.runtime.snapshot()["ready"])
        finally:
            release.set()
        transaction.result(5)

    def test_running_job_cannot_be_cancelled_and_stop_retains_ownership(self) -> None:
        entered, release = Event(), Event()

        def maintain():
            with self.runtime.operation(Operation.RESTORE):
                entered.set()
                self.assertTrue(release.wait(5))

        maintenance = self.pool.submit(maintain)
        try:
            self.assertTrue(entered.wait(5))
            job = self.runtime.snapshot()["job"]
            self.assertFalse(self.runtime.cancel(job["id"]))
            with self.assertRaises(RuntimeConflictError):
                self.runtime.stop(timeout=0)
            self.assertEqual("stopping", self.runtime.snapshot()["state"])
            replacement = RuntimeCoordinator(self.database, lambda: {"ready": True})
            with self.assertRaises(RuntimeConflictError):
                replacement.start()
        finally:
            release.set()
        maintenance.result(5)
        self.assertEqual("stopping", self.runtime.snapshot()["state"])
        self.runtime.stop()
        replacement.start()
        replacement.stop()

    def test_abandoned_request_does_not_release_its_running_worker(self) -> None:
        entered, release = Event(), Event()
        with self.runtime.admit():
            inherited = copy_context()
            transaction = self.pool.submit(inherited.run, self.hold_transaction, entered, release)
            self.assertTrue(entered.wait(5))
        try:
            self.assertEqual(1, self.runtime.snapshot()["active"])
            with self.assertRaises(RuntimeConflictError):
                self.runtime.stop(timeout=0)
            with self.assertRaises(RuntimeConflictError):
                RuntimeCoordinator(self.database, lambda: {"ready": True}).start()
        finally:
            release.set()
        transaction.result(5)
        self.runtime.stop()

    def test_lock_upgrade_is_rejected_without_deadlock(self) -> None:
        with self.runtime.admit():
            with self.assertRaises(RuntimeConflictError) as raised:
                with self.runtime.operation(Operation.RESTORE):
                    self.fail("ordinary request upgraded to maintenance")
        self.assertEqual("lock_upgrade_forbidden", raised.exception.code)

    def test_detached_worker_cannot_reenter_persistence_after_restart(self) -> None:
        entered, release, between, resume = Event(), Event(), Event(), Event()

        def worker():
            self.hold_transaction(entered, release)
            between.set()
            self.assertTrue(resume.wait(5))
            with self.assertRaises(RuntimeConflictError), session_scope(self.database):
                self.fail("detached worker reentered the new runtime")

        with self.runtime.admit():
            inherited = copy_context()
            request = self.pool.submit(inherited.run, worker)
            self.assertTrue(entered.wait(5))
        release.set()
        try:
            self.assertTrue(between.wait(5))
            self.runtime.stop()
            self.runtime.start()
        finally:
            resume.set()
        request.result(5)

    def test_failed_job_is_secret_free_and_restart_remains_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret"):
            with self.runtime.operation(Operation.RESTORE):
                raise ValueError("secret payload /private/path")
        self.assertEqual("error", self.runtime.snapshot()["state"])
        job_id = self.runtime.snapshot()["job"]["id"]
        self.assertNotIn("secret", json.dumps(self.runtime.snapshot()))
        self.runtime.stop()
        self.runtime.start()
        self.assertEqual("interrupted", self.runtime.snapshot()["job"]["status"])
        self.assertEqual(job_id, self.runtime.snapshot()["job"]["id"])
        self.assertFalse(self.runtime.snapshot()["ready"])
        with self.runtime.operation(Operation.RESTORE):
            pass
        self.assertTrue(self.runtime.snapshot()["ready"])

    def test_base_exception_rolls_back_before_releasing_the_transaction(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            with session_scope(self.database) as session:
                session.execute(text("CREATE TABLE IF NOT EXISTS runtime_test (value INTEGER)"))
                session.execute(text("INSERT INTO runtime_test VALUES (7)"))
                raise KeyboardInterrupt
        with session_scope(self.database) as session:
            self.assertEqual(0, session.execute(text("SELECT COUNT(*) FROM runtime_test")).scalar())
        self.assertEqual(0, self.runtime.snapshot()["active"])

    def test_process_owner_is_exclusive_and_crash_is_not_retried(self) -> None:
        script = """
import sys
from pathlib import Path
from backend.runtime import Operation, RuntimeCoordinator, RuntimeConflictError
runtime = RuntimeCoordinator(Path(sys.argv[1]), lambda: {'ready': True})
try:
    runtime.start()
except RuntimeConflictError:
    print('owned', flush=True)
    sys.exit(0)
with runtime.operation(Operation.RESTORE):
    print('running', flush=True)
    sys.stdin.read()
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.database)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual("owned", result.stdout.strip())
        self.runtime.stop()
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(self.database)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual("running", process.stdout.readline().strip())
        finally:
            process.kill()
            process.communicate(timeout=10)
        self.runtime.start()
        self.assertEqual("interrupted", self.runtime.snapshot()["job"]["status"])
        self.assertFalse(self.runtime.snapshot()["ready"])

    def test_invalid_journal_fails_closed(self) -> None:
        self.runtime.stop()
        Path(f"{self.database}.runtime-job.json").write_text('{"id": "secret-invalid"}')
        self.runtime.start()
        self.assertEqual("error", self.runtime.snapshot()["state"])
        self.assertNotIn("secret", json.dumps(self.runtime.snapshot()))

    def test_failed_final_status_write_keeps_recovery_required(self) -> None:
        save = self.runtime._save_job

        def fail_success_record():
            if self.runtime.snapshot()["job"]["status"] == "succeeded":
                raise OSError("journal unavailable")
            save()

        with patch.object(self.runtime, "_save_job", fail_success_record):
            with self.assertRaises(OSError):
                with self.runtime.operation(Operation.RESTORE):
                    pass
        self.runtime.stop()
        self.runtime.start()
        self.assertFalse(self.runtime.snapshot()["ready"])

    def test_cancelled_recovery_does_not_erase_the_restart_guard(self) -> None:
        with self.assertRaises(ValueError):
            with self.runtime.operation(Operation.RESTORE):
                raise ValueError("restore failed")
        save = self.runtime._save_job

        def cancel_waiting():
            save()
            job = self.runtime.snapshot()["job"]
            if job["status"] == "waiting":
                self.runtime.cancel(job["id"])

        with patch.object(self.runtime, "_save_job", cancel_waiting):
            with self.assertRaises(RuntimeConflictError):
                with self.runtime.operation(Operation.RESTORE):
                    self.fail("cancelled recovery ran")
        self.assertEqual("cancelled", self.runtime.snapshot()["job"]["status"])
        self.runtime.stop()
        self.runtime.start()
        self.assertFalse(self.runtime.snapshot()["ready"])

    def test_interrupted_initialization_does_not_become_ready_on_restart(self) -> None:
        self.runtime.stop()
        with patch(
            "backend.persistence.database._apply_migrations_unlocked", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.runtime.start(lambda: initialize(self.database, reset=True))
        self.runtime.stop()
        self.runtime.start()
        self.assertEqual("interrupted", self.runtime.snapshot()["job"]["status"])
        self.assertFalse(self.runtime.snapshot()["ready"])


if __name__ == "__main__":
    unittest.main()
