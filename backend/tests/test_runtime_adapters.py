"""Runtime integration at HTTP, admin and production startup boundaries."""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.application.admin import EXIT_NOT_READY, EXIT_OK, AdminActorContext, AdminApplication
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_runtime import RuntimeAdmissionMiddleware
from backend.persistence.database import (
    PersistenceConfigurationError,
    initialize,
    persistence_paths,
    session_scope,
)
from backend.runtime import Operation, RuntimeConflictError, RuntimeCoordinator
from backend.server import main, prepare_database, runtime_coordinator
from backend.tests import test_admin_application


class RuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = persistence_paths(data_dir=temporary.name, environment={})
        self.args = argparse.Namespace(
            paths=self.paths,
            db=self.paths.database,
            init=True,
            reset=False,
            host="127.0.0.1",
            port=8000,
            static_dir=None,
        )
        self.config = FastAPIConfig(
            db_path=self.paths.database,
            session_cookie_name="session",
            https_only=False,
        )
        self.runtime = runtime_coordinator(self.args)
        self.addCleanup(self.runtime.stop)

    def test_not_ready_is_diagnosable_without_persistence_and_blocks_business_work(self) -> None:
        self.args.init = False
        self.runtime.start(lambda: prepare_database(self.args))
        services = test_admin_application.AdminApplicationTests().services()
        diagnostics = Mock(side_effect=AssertionError("diagnostics opened storage"))
        services = replace(services, diagnostics=diagnostics)
        admin = AdminApplication(self.paths, services, runtime=self.runtime)
        app = create_app(self.config, runtime=self.runtime)
        with (
            patch("backend.persistence.database.engine_for", side_effect=AssertionError("SQL")),
            TestClient(app) as client,
        ):
            self.assertEqual(200, client.get("/api/health").status_code)
            self.assertEqual(503, client.get("/api/ready").status_code)
            for path in ("/api", "/api/candidates", "/api/auth/session", "/"):
                response = client.get(path)
                self.assertEqual(503, response.status_code, path)
                self.assertEqual("no-store", response.headers["cache-control"])
                self.assertEqual("DENY", response.headers["x-frame-options"])
            result = admin.execute(
                {
                    "version": 1,
                    "command": "status",
                    "arguments": {
                        "client": {"identity": "development", "revision": "unknown"},
                    },
                },
                AdminActorContext("verified", True),
            )
            self.assertEqual(EXIT_OK, result.exit_code)
            self.assertFalse(result.response["result"]["runtime"]["ready"])
            result = admin.execute(
                {"version": 1, "command": "invite", "arguments": {"email": "secret"}},
                AdminActorContext("verified", True),
            )
            self.assertEqual(EXIT_NOT_READY, result.exit_code)
            self.assertNotIn("secret", result.encode().decode())

    def test_existing_pending_schema_without_init_stays_live_and_not_ready(self) -> None:
        self.args.init = False
        initialize(self.paths.database)
        with session_scope(self.paths.database) as session:
            last = session.execute(text("SELECT MAX(name) FROM schema_migration")).scalar_one()
            session.execute(
                text("DELETE FROM schema_migration_checksum WHERE name = :name"), {"name": last}
            )
            session.execute(text("DELETE FROM schema_migration WHERE name = :name"), {"name": last})
        with patch("backend.server.initialize", side_effect=AssertionError("auto migration")):
            self.runtime.start(lambda: prepare_database(self.args))
        self.assertEqual("migration_required", self.runtime.snapshot()["state"])
        with TestClient(create_app(self.config, runtime=self.runtime)) as client:
            self.assertEqual(200, client.get("/api/health").status_code)
            self.assertEqual(503, client.get("/api/ready").status_code)

    def test_new_database_starts_ready_and_shutdown_releases_owner(self) -> None:
        observations = []

        def run(app, **_kwargs):
            observations.append(app.state.runtime)
            with TestClient(app) as client:
                self.assertEqual(200, client.get("/api/ready").status_code)
                self.assertEqual(401, client.get("/api").status_code)

        with (
            patch("backend.server.parse_args", return_value=self.args),
            patch("backend.server.uvicorn.run", run),
        ):
            main()
        self.assertEqual("stopped", observations[0].snapshot()["state"])
        self.runtime.start()
        self.assertTrue(self.runtime.snapshot()["ready"])

    def test_invalid_persistence_keeps_the_http_process_diagnosable(self) -> None:
        with patch(
            "backend.server.validate_persistence",
            side_effect=PersistenceConfigurationError("secret"),
        ):
            self.runtime.start(lambda: prepare_database(self.args))
        self.assertEqual("error", self.runtime.snapshot()["state"])
        self.assertNotIn("secret", str(self.runtime.snapshot()))

    def test_restore_waits_for_the_entire_http_command_between_transactions(self) -> None:
        self.runtime.start(lambda: prepare_database(self.args))
        app = create_app(self.config, runtime=self.runtime)
        entered, finish = Event(), Event()

        @app.get("/runtime-test")
        def command():
            with session_scope(self.paths.database) as session:
                session.execute(text("SELECT 1"))
            entered.set()
            if not finish.wait(5):
                raise AssertionError("HTTP command was not released")
            # An already admitted command is allowed to complete its next unit
            # of work after maintenance closes admission to new requests.
            with session_scope(self.paths.database) as session:
                return {"value": session.execute(text("SELECT 2")).scalar_one()}

        # The product's SPA fallback is deliberately the last registered route.
        app.router.routes.insert(0, app.router.routes.pop())

        def maintain():
            with self.runtime.operation(Operation.RESTORE):
                self.assertTrue(finish.is_set())

        with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(client.get, "/runtime-test")
            self.assertTrue(entered.wait(5))
            maintenance = pool.submit(maintain)
            try:
                deadline = monotonic() + 5
                while self.runtime.snapshot()["job"]["status"] != "waiting":
                    self.assertLess(monotonic(), deadline)
                    Event().wait(0.005)
                self.assertFalse(maintenance.done())
                self.assertEqual(503, client.get("/api").status_code)
                self.assertEqual(503, client.get("/api/ready").status_code)
                self.assertEqual(200, client.get("/api/health").status_code)
            finally:
                finish.set()
            self.assertEqual({"value": 2}, request.result(5).json())
            maintenance.result(5)

    def test_injected_adapters_cannot_use_another_database(self) -> None:
        unrelated = RuntimeCoordinator(Path("another.sqlite"), lambda: {"ready": True})
        with self.assertRaises(ValueError):
            create_app(self.config, runtime=unrelated)
        with self.assertRaises(ValueError):
            AdminApplication(
                self.paths,
                test_admin_application.AdminApplicationTests().services(),
                runtime=unrelated,
            )


class RuntimeCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_cancellation_waits_for_the_entire_application_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeCoordinator(Path(directory) / "app.sqlite", lambda: {"ready": True})
            runtime.start()
            entered, release = Event(), Event()

            def worker():
                entered.set()
                if not release.wait(5):
                    raise AssertionError("worker was not released")

            async def app(_scope, _receive, _send):
                await asyncio.to_thread(worker)

            async def receive():
                return {"type": "http.disconnect"}

            async def send(_message):
                pass

            middleware = RuntimeAdmissionMiddleware(app, runtime)
            request = asyncio.create_task(
                middleware({"type": "http", "path": "/api"}, receive, send)
            )
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                request.cancel()
                await asyncio.sleep(0)
                self.assertFalse(request.done())
                self.assertEqual(1, runtime.snapshot()["active"])
                with self.assertRaises(RuntimeConflictError):
                    runtime.stop(timeout=0)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(request, timeout=5)
                runtime.stop()


if __name__ == "__main__":
    unittest.main()
