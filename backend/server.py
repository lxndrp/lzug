"""Production FastAPI process bootstrap."""

from __future__ import annotations

import argparse
import os
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
from .map_provider import MapProviderConfig
from .observability import emit_event
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .security import RuntimeSecurityConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the lzug FastAPI backend.")
    parser.add_argument("--host", default=os.environ.get("LZUG_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LZUG_PORT", "8000")))
    parser.add_argument("--static-dir", default=os.environ.get("LZUG_STATIC_DIR"))
    parser.add_argument("--db", dest="db_value")
    parser.add_argument("--data-dir")
    parser.add_argument("--documents")
    parser.add_argument("--backups")
    parser.add_argument("--database-url")
    parser.add_argument("--init", action="store_true")
    parser.add_argument(
        "--seed-profile",
        choices=("development", "public-demo"),
        help="Select an explicit synthetic seed profile for --init",
    )
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.db_value and args.database_url:
        parser.error("Use only one of --db and --database-url")
    try:
        args.paths = persistence_paths(
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
                with_seed=args.seed,
                seed_profile=args.seed_profile,
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
) -> None:
    args = parse_args()
    prepare_database(args)
    security = RuntimeSecurityConfig.from_environment()
    config = FastAPIConfig(
        db_path=args.db,
        session_cookie_name="__Host-lzug_session" if security.https_only else "lzug_session",
        cookie_secure=security.https_only,
        https_only=security.https_only,
        cors_allowed_origins=security.cors_allowed_origins,
        max_request_bytes=security.max_request_bytes,
        session_ttl=session_ttl or security.session_ttl,
        static_dir=args.static_dir,
        runtime_policy=runtime_policy or ProductRuntimePolicy(),
        auth_rate_limit=security.auth_rate_limit,
        auth_rate_window=security.auth_rate_window,
        map_provider=MapProviderConfig.from_environment(),
    )
    emit_event("runtime", severity="info", signal="started")
    uvicorn.run(
        create_app(config), host=args.host, port=args.port, log_config=None, access_log=False
    )


if __name__ == "__main__":
    main()
