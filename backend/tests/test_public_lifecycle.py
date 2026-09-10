"""Public lifecycle, admission, initialization and diagnostic consistency."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api_contracts import LifecycleResponse, RuntimeUnavailableResponse
from backend.application.admin import AdminActorContext, AdminApplication
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.persistence.database import persistence_paths
from backend.public_lifecycle import public_lifecycle
from backend.runtime import Operation, RuntimeConflictError, RuntimeCoordinator, RuntimeState
from backend.server import initialization_lifespan
from backend.tests import test_admin_application


class PublicLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = persistence_paths(data_dir=self.root, environment={})
        static = self.root / "static"
        static.mkdir()
        (static / "index.html").write_text("<html><app-root></app-root></html>")
        (static / "main.js").write_text('console.log("shell")')
        self.probe = {"ready": True}
        self.runtime = RuntimeCoordinator(self.paths.database, lambda: self.probe)
        self.addCleanup(self.runtime.stop)
        self.config = FastAPIConfig(
            db_path=self.paths.database,
            session_cookie_name="session",
            static_dir=static,
            max_request_bytes=32,
            https_only=False,
        )

    def assert_state(self, client, state):
        ready = state == "ready"
        self.assertEqual(200, client.get("/api/health").status_code)
        response = client.get("/api/ready")
        self.assertEqual(200 if ready else 503, response.status_code)
        LifecycleResponse.model_validate(response.json())
        self.assertEqual(state, response.json()["state"])
        self.assertEqual(ready, response.json()["ready"])
        lifecycle = client.get("/api/lifecycle")
        self.assertEqual(200, lifecycle.status_code)
        self.assertEqual(state, lifecycle.json()["state"])
        self.assertEqual("no-store", lifecycle.headers["cache-control"])
        self.assertEqual(
            {"status", "version", "revision", "_links", "state", "ready"}, set(lifecycle.json())
        )
        for path in ("/", "/dashboard", "/login", "/main.js"):
            self.assertEqual(200, client.get(path).status_code, path)
        self.assertEqual(200, client.head("/dashboard").status_code)
        self.assertEqual(404, client.get("/missing.js").status_code)
        if not ready:
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                for path in ("/api", "/api/session", "/api/candidates", "/api/missing"):
                    rejected = client.request(method, path)
                    self.assertEqual(503, rejected.status_code)
                    RuntimeUnavailableResponse.model_validate(rejected.json())
                    self.assertEqual(state, rejected.json()["error"]["state"])
            # Header limits and origin policy precede lifecycle. Rejected bodies
            # without a length are never consumed by the admission adapter.
            self.assertEqual(413, client.post("/api/candidates", content=b"x" * 33).status_code)
            self.assertEqual(
                403,
                client.get(
                    "/api/health", headers={"Origin": "https://invalid.example"}
                ).status_code,
            )

    def test_all_public_states_and_unknown_diagnostics_are_allowlisted(self):
        for state in RuntimeState:
            snapshot = {
                "state": state.value,
                "ready": state == RuntimeState.READY,
                "reason": "/secret/database",
                "job": "private",
                "schema": "private",
            }
            self.assertEqual(
                {"state": state.value, "ready": state == RuntimeState.READY},
                public_lifecycle(snapshot),
            )
        self.assertEqual({"state": "error", "ready": False}, public_lifecycle({"state": "secret"}))

    def test_initialization_keeps_http_live_and_agrees_with_admin(self):
        entered, release = Event(), Event()

        def prepare():
            entered.set()
            self.assertTrue(release.wait(60))

        self.runtime.claim()
        app = create_app(self.config, runtime=self.runtime)
        app.router.lifespan_context = initialization_lifespan(self.runtime, prepare)
        services = replace(
            test_admin_application.AdminApplicationTests().services(),
            diagnostics=lambda *_: self.fail("storage probe"),
        )
        admin = AdminApplication(self.paths, services, runtime=self.runtime)
        with TestClient(app) as client:
            try:
                self.assertTrue(entered.wait(5))
                self.assert_state(client, "initializing")
                result = admin.execute(
                    {
                        "version": 1,
                        "command": "status",
                        "arguments": {"client": {"identity": "development", "revision": "unknown"}},
                    },
                    AdminActorContext("verified", True),
                )
                self.assertEqual(
                    client.get("/api/lifecycle").json()["state"],
                    result.response["result"]["runtime"]["state"],
                )
            finally:
                release.set()

    def test_maintenance_migration_and_final_journal_have_no_premature_ready(self):
        self.runtime.start()
        with TestClient(create_app(self.config, runtime=self.runtime)) as client:
            self.assert_state(client, "ready")
            for operation, state in (
                (Operation.RESTORE, "maintenance"),
                (Operation.MIGRATION, "migrating"),
            ):
                save_job = self.runtime._save_job

                def save(state=state, save_job=save_job):
                    self.assertEqual(state, self.runtime.snapshot()["state"])
                    self.assertFalse(self.runtime.snapshot()["ready"])
                    save_job()

                with patch.object(self.runtime, "_save_job", save):
                    with ThreadPoolExecutor() as pool:
                        entered, release = Event(), Event()

                        def work(operation=operation, entered=entered, release=release):
                            with self.runtime.operation(operation):
                                entered.set()
                                self.assertTrue(release.wait(60))

                        job = pool.submit(work)
                        try:
                            self.assertTrue(entered.wait(5))
                            self.assert_state(client, state)
                        finally:
                            release.set()
                        job.result(10)
                self.assert_state(client, "ready")

    def test_failed_postcheck_remains_diagnosable_after_restart(self):
        self.runtime.start()
        with self.assertRaises(RuntimeConflictError):
            with self.runtime.operation(Operation.MIGRATION):
                self.probe = {"ready": False, "reason": "migration_required"}
        self.assertEqual("failed", self.runtime.snapshot()["job"]["status"])
        with TestClient(create_app(self.config, runtime=self.runtime)) as client:
            self.assert_state(client, "error")
        self.runtime.stop()
        self.probe = {"ready": True}
        self.runtime.start()
        self.assertEqual("error", self.runtime.snapshot()["state"])
        with self.runtime.operation(Operation.RESTORE):
            pass
        self.assertTrue(self.runtime.snapshot()["ready"])

    def test_pending_migration_and_start_failure_never_expose_details(self):
        self.probe = {
            "ready": False,
            "reason": "migration_required",
            "migration": {
                "state": "migration_required",
                "current": "001_private.sql",
                "target": "002_private.sql",
                "pending": ["002_private.sql"],
            },
        }
        self.runtime.start()
        self.assertEqual("002_private.sql", self.runtime.diagnosis()["migration"]["target"])
        self.assertEqual("inspect_upgrade", self.runtime.diagnosis()["next_action"]["code"])
        with TestClient(create_app(self.config, runtime=self.runtime)) as client:
            self.assert_state(client, "migration_required")
            self.assertNotIn("private", client.get("/api/lifecycle").text)
        self.runtime.stop()
        self.runtime.start(lambda: (_ for _ in ()).throw(ValueError("secret path password schema")))
        with TestClient(create_app(self.config, runtime=self.runtime)) as client:
            self.assert_state(client, "error")

    def test_ownership_can_be_released_if_listener_never_starts(self):
        self.runtime.claim()
        self.runtime.stop(timeout=0)
        self.runtime.start()
        self.assertTrue(self.runtime.snapshot()["ready"])

    def test_each_initialization_operation_retains_recovery_evidence(self):
        def prepare():
            with self.runtime.operation(Operation.MIGRATION):
                with self.runtime.operation(Operation.MIGRATION):
                    first = self.runtime.snapshot()["job"]["id"]
            with self.runtime.operation(Operation.MIGRATION):
                self.assertNotEqual(first, self.runtime.snapshot()["job"]["id"])
                raise ValueError("private initialization failure")

        self.runtime.start(prepare)
        self.assertEqual("failed", self.runtime.snapshot()["job"]["status"])
        self.runtime.stop()
        self.runtime.start()
        self.assertEqual("error", self.runtime.snapshot()["state"])
