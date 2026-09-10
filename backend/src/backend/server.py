"""Production FastAPI process bootstrap."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import uvicorn

from backend.persistence.database import (
    PersistenceConfigurationError,
    database_readiness,
    initialize,
    persistence_paths,
    validate_persistence,
)

from .admin import _application
from .admin_socket import AdminSocket, SocketConfig
from .fastapi_assembly import FastAPIConfig, create_app
from .observability import emit_event
from .runtime import RuntimeConflictError, RuntimeCoordinator
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .settings import RuntimeSettings


def initialization_lifespan(
    runtime: RuntimeCoordinator, prepare, *, admin_socket: AdminSocket | None = None
):
    """Run preparation in this process after transport assembly, without blocking HTTP."""

    @asynccontextmanager
    async def lifespan(_app):
        initialization = asyncio.create_task(asyncio.to_thread(runtime.initialize, prepare))
        try:
            yield
        finally:
            if admin_socket is not None:
                # A failed drain must keep ownership while socket workers remain.
                await asyncio.to_thread(admin_socket.stop)
            # Stop admission before waiting; retain ownership until the worker exits.
            await asyncio.to_thread(runtime.stop)
            await initialization

    return lifespan


def parse_args(settings: RuntimeSettings | None = None) -> argparse.Namespace:
    settings = settings or RuntimeSettings.from_environment()
    parser = argparse.ArgumentParser(description="Run the lzug FastAPI backend.")
    parser.add_argument("--host", default=settings.server.host)
    parser.add_argument("--port", type=int, default=settings.server.port)
    parser.add_argument("--static-dir", default=settings.server.static_dir)
    parser.add_argument("--db", dest="db_value")
    parser.add_argument("--data-dir")
    parser.add_argument("--documents")
    parser.add_argument("--backups")
    parser.add_argument("--database-url")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--admin-socket-dir", type=Path)
    parser.add_argument("--admin-socket-gid", type=int)
    parser.add_argument("--admin-socket-connections", type=int, default=8)
    parser.add_argument("--admin-socket-handshake-timeout", type=float, default=5)
    parser.add_argument("--admin-socket-request-timeout", type=float, default=30)
    parser.add_argument("--admin-socket-shutdown-timeout", type=float, default=30)
    args = parser.parse_args()
    args.admin_socket = None
    if (args.admin_socket_dir is None) != (args.admin_socket_gid is None):
        parser.error("Admin socket directory and dedicated operator GID must be set together")
    if args.admin_socket_dir is not None:
        try:
            args.admin_socket = SocketConfig(
                args.admin_socket_dir,
                args.admin_socket_gid,
                max_connections=args.admin_socket_connections,
                handshake_timeout=args.admin_socket_handshake_timeout,
                request_timeout=args.admin_socket_request_timeout,
                shutdown_timeout=args.admin_socket_shutdown_timeout,
            )
        except ValueError as error:
            parser.error(str(error))
    if args.db_value and args.database_url:
        parser.error("Use only one of --db and --database-url")
    try:
        args.paths = persistence_paths(
            settings=settings.persistence,
            data_dir=args.data_dir,
            database=args.database_url or args.db_value,
            documents=args.documents,
            backups=args.backups,
        )
        args.db = args.paths.database
        args.static_dir = Path(args.static_dir).expanduser() if args.static_dir else None
    except (ValueError, PersistenceConfigurationError) as error:
        parser.error(str(error))
    if args.static_dir is not None and not (args.static_dir / "index.html").is_file():
        parser.error(f"Static directory must contain index.html: {args.static_dir}")
    return args


def prepare_database(args: argparse.Namespace) -> None:
    """Preserve the existing explicit --init path under runtime ownership."""
    validate_persistence(args.paths)
    if args.init:
        initialize(args.db, reset=args.reset, backup_dir=args.paths.backups)


def runtime_coordinator(args: argparse.Namespace) -> RuntimeCoordinator:
    """Compose lifecycle ownership with the existing storage readiness checks."""

    def probe():
        validate_persistence(args.paths, require_database=True)
        return database_readiness(args.db)

    return RuntimeCoordinator(args.db, probe)


def start_admin_socket(
    args: argparse.Namespace, settings: RuntimeSettings, runtime: RuntimeCoordinator
) -> AdminSocket | None:
    """Attach the opt-in control listener to the existing process owner."""
    if getattr(args, "admin_socket", None) is None:
        return None

    def listener_failed() -> None:
        # Stop ordinary admission; HTTP can still expose liveness/not-readiness.
        try:
            runtime.stop(timeout=0)
        except RuntimeConflictError:
            pass

    listener = AdminSocket(
        args.admin_socket,
        _application(settings=settings, paths=args.paths, runtime=runtime),
        on_failure=listener_failed,
    )
    listener.start()
    return listener


def main(
    *,
    runtime_policy: RuntimePolicy | None = None,
    session_ttl: timedelta | None = None,
    settings: RuntimeSettings | None = None,
) -> None:
    settings = settings or RuntimeSettings.from_environment()
    args = parse_args(settings)
    runtime = runtime_coordinator(args)
    config = FastAPIConfig.from_settings(settings, db_path=args.db, static_dir=args.static_dir)
    config = replace(
        config,
        session_ttl=session_ttl or config.session_ttl,
        runtime_policy=runtime_policy or ProductRuntimePolicy(),
    )
    admin_socket = None

    try:
        runtime.claim()
        admin_socket = start_admin_socket(args, settings, runtime)
        app = create_app(config, runtime=runtime)
        app.router.lifespan_context = initialization_lifespan(
            runtime, lambda: prepare_database(args), admin_socket=admin_socket
        )
        emit_event("runtime", severity="info", signal="started")
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_config=None,
            access_log=False,
        )
    finally:
        if admin_socket is not None:
            # A drain timeout retains runtime ownership; never detach a mutation.
            admin_socket.stop()
        runtime.stop()


if __name__ == "__main__":
    main()
