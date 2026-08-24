"""Playwright-only backend server with a resettable, seeded database."""

from __future__ import annotations

from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import override
from urllib.parse import urlparse

from .app import LzugHandler, parse_args
from .auth import AuthenticationRepository
from .database import initialize
from .security import RequestRateLimiter, RuntimeSecurityConfig


class E2EHandler(LzugHandler):
    """Expose a reset endpoint only from the Playwright-specific server."""

    reset_lock = Lock()
    cookie_secure = False
    https_only = False
    session_cookie_name = "lzug_e2e_session"

    @override
    def do_GET(self) -> None:
        with self.reset_lock:
            super().do_GET()

    @override
    def do_PATCH(self) -> None:
        with self.reset_lock:
            super().do_PATCH()

    @override
    def do_DELETE(self) -> None:
        with self.reset_lock:
            super().do_DELETE()

    @override
    def do_POST(self) -> None:
        if urlparse(self.path).path == "/__e2e/reset":
            with self.reset_lock:
                initialize(self.db_path, with_seed=True, reset=True)
                credentials = AuthenticationRepository(self.db_path).create_session(1)
            self.issue_session_cookies(credentials)
            self.respond({"status": "reset"}, HTTPStatus.OK)
            return
        with self.reset_lock:
            super().do_POST()


def main() -> None:
    args = parse_args()
    runtime_security = RuntimeSecurityConfig.from_environment()
    database_path: Path = args.db
    initialize(database_path, with_seed=True, reset=True)

    E2EHandler.db_path = database_path
    E2EHandler.static_dir = args.static_dir
    E2EHandler.cors_allowed_origins = runtime_security.cors_allowed_origins
    E2EHandler.session_ttl = runtime_security.session_ttl
    E2EHandler.max_request_bytes = runtime_security.max_request_bytes
    E2EHandler.auth_rate_limiter = RequestRateLimiter(
        runtime_security.auth_rate_limit,
        runtime_security.auth_rate_window,
    )
    server = ThreadingHTTPServer((args.host, args.port), E2EHandler)
    print(f"lzug E2E backend listening on http://{args.host}:{args.port}")
    print(f"database: {database_path}")
    server.serve_forever()


if __name__ == "__main__":
    main()
