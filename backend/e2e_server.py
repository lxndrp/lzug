"""Playwright-only FastAPI assembly with a resettable seeded database."""

from __future__ import annotations

from threading import Lock

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .auth import AuthenticationRepository
from .database import initialize
from .fastapi_app import FastAPIConfig, create_app
from .map_provider import MapProviderConfig
from .runtime_policy import ProductRuntimePolicy
from .security import RuntimeSecurityConfig
from .server import parse_args


def create_e2e_app(config: FastAPIConfig) -> FastAPI:
    app = create_app(config)
    reset_lock = Lock()

    @app.post("/__e2e/reset", include_in_schema=False)
    def reset():
        with reset_lock:
            initialize(config.db_path, with_seed=True, reset=True)
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
    args = parse_args()
    security = RuntimeSecurityConfig.from_environment()
    initialize(args.db, with_seed=True, reset=True)
    config = FastAPIConfig(
        db_path=args.db,
        session_cookie_name="lzug_e2e_session",
        csrf_cookie_name="lzug_csrf",
        cookie_secure=False,
        https_only=False,
        cors_allowed_origins=security.cors_allowed_origins,
        max_request_bytes=security.max_request_bytes,
        session_ttl=security.session_ttl,
        static_dir=args.static_dir,
        runtime_policy=ProductRuntimePolicy(),
        auth_rate_limit=security.auth_rate_limit,
        auth_rate_window=security.auth_rate_window,
        map_provider=MapProviderConfig.from_environment(),
    )
    print(f"lzug E2E backend listening on http://{args.host}:{args.port}")
    print(f"database: {args.db}")
    uvicorn.run(
        create_e2e_app(config), host=args.host, port=args.port, log_config=None, access_log=False
    )


if __name__ == "__main__":
    main()
