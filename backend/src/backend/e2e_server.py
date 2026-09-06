"""Playwright-only FastAPI assembly with a resettable seeded database."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from threading import Lock

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .auth import AuthenticationRepository
from .database import initialize
from .fastapi_app import FastAPIConfig, create_app
from .runtime_policy import ProductRuntimePolicy
from .server import parse_args
from .settings import RuntimeSettings


def _development_seed_sql() -> str:
    from fixtures.generate import load_source, render_profile_sql

    data = deepcopy(load_source())
    # Browser tests use the historical single-round baseline so their
    # interaction and accessibility assertions remain independent of the
    # additional protocol/lifecycle records in the complete development seed.
    data["profiles"]["development"]["seed_records"] = []
    return render_profile_sql(data, "development")


def create_e2e_app(config: FastAPIConfig) -> FastAPI:
    app = create_app(config)
    reset_lock = Lock()

    @app.post("/__e2e/reset", include_in_schema=False)
    def reset():
        with reset_lock:
            initialize(config.db_path, seed_sql=_development_seed_sql(), reset=True)
            credentials = AuthenticationRepository(config.db_path).create_session(1)
        response = JSONResponse({"status": "reset"})
        response.set_cookie(
            config.session_cookie_name,
            credentials.token,
            max_age=int(config.session_ttl.total_seconds()),
            secure=config.cookie_secure,
            httponly=True,
            samesite="strict",
        )
        response.set_cookie(
            config.csrf_cookie_name,
            credentials.csrf_token,
            max_age=int(config.session_ttl.total_seconds()),
            secure=config.cookie_secure,
            httponly=False,
            samesite="strict",
        )
        return response

    return app


def main() -> None:
    settings = RuntimeSettings.from_environment()
    args = parse_args(settings)
    initialize(args.db, seed_sql=_development_seed_sql(), reset=True)
    config = replace(
        FastAPIConfig.from_settings(settings, db_path=args.db, static_dir=args.static_dir),
        session_cookie_name="lzug_e2e_session",
        csrf_cookie_name="lzug_csrf",
        cookie_secure=False,
        https_only=False,
        runtime_policy=ProductRuntimePolicy(),
    )
    print(f"lzug E2E backend listening on http://{args.host}:{args.port}")
    print(f"database: {args.db}")
    uvicorn.run(
        create_e2e_app(config), host=args.host, port=args.port, log_config=None, access_log=False
    )


if __name__ == "__main__":
    main()
