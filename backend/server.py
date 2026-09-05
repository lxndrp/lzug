"""Production FastAPI process bootstrap."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import uvicorn

from .database import (
    MigrationError,
    PersistenceConfigurationError,
    database_readiness,
    initialize,
    persistence_paths,
    validate_persistence,
)
from .fastapi_app import FastAPIConfig, create_app
from .observability import emit_event
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .settings import RuntimeSettings


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
    args = parser.parse_args()
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
    try:
        validate_persistence(args.paths)
        if args.init:
            initialize(
                args.db,
                reset=args.reset,
                backup_dir=args.paths.backups,
            )
    except MigrationError as error:
        raise SystemExit(f"Database migration failed: {error}") from error
    except PersistenceConfigurationError as error:
        raise SystemExit(f"Persistent storage is not ready: {error}") from error
    readiness = database_readiness(args.db)
    if not readiness["ready"]:
        raise SystemExit(
            f"Database is not ready: {args.db}. Reason: {readiness['reason']}. "
            "Start with --init to initialize or migrate it, then retry."
        )
    try:
        validate_persistence(args.paths, require_database=True)
    except PersistenceConfigurationError as error:
        raise SystemExit(f"Persistent storage is not ready: {error}") from error


def main(
    *,
    runtime_policy: RuntimePolicy | None = None,
    session_ttl: timedelta | None = None,
    settings: RuntimeSettings | None = None,
) -> None:
    settings = settings or RuntimeSettings.from_environment()
    args = parse_args(settings)
    prepare_database(args)
    config = FastAPIConfig.from_settings(settings, db_path=args.db, static_dir=args.static_dir)
    config = replace(
        config,
        session_ttl=session_ttl or config.session_ttl,
        runtime_policy=runtime_policy or ProductRuntimePolicy(),
    )
    emit_event("runtime", severity="info", signal="started")
    uvicorn.run(
        create_app(config), host=args.host, port=args.port, log_config=None, access_log=False
    )


if __name__ == "__main__":
    main()
