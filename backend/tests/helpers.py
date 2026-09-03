from __future__ import annotations

import json
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol

from fastapi.testclient import TestClient

from backend.auth import AuthenticationRepository, SessionCredentials
from backend.database import initialize, is_ready
from backend.fastapi_app import FastAPIConfig, create_app
from backend.map_provider import MapProviderConfig
from backend.runtime_policy import ProductRuntimePolicy, RuntimePolicy
from backend.security import RequestRateLimiter


@dataclass(frozen=True)
class AdapterResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def json(self) -> Any:
        return None if not self.body else json.loads(self.body.decode("utf-8"))


class HttpAdapter(Protocol):
    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        credentials: SessionCredentials | None = None,
        request_headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> AdapterResponse: ...


class TestLzugHandler:
    """Compatibility configuration fixture retained for existing unit tests."""

    static_dir: Path | None = None
    cookie_secure = True
    https_only = True
    session_cookie_name = "lzug_session"
    csrf_cookie_name = "lzug_csrf"
    cors_allowed_origins: frozenset[str] = frozenset()
    session_ttl = timedelta(hours=8)
    max_request_bytes = 1024 * 1024
    runtime_policy: RuntimePolicy = ProductRuntimePolicy()
    auth_rate_limiter = RequestRateLimiter(20, timedelta(minutes=1))
    map_provider = MapProviderConfig()


class TempDatabase(AbstractContextManager):
    def __init__(self, with_seed: bool = True):
        self.with_seed = with_seed
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self._directory = tempfile.TemporaryDirectory()
        self.path = Path(self._directory.name) / "lzug-test.sqlite3"
        initialize(self.path, with_seed=self.with_seed, reset=True)
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._directory:
            self._directory.cleanup()


class FastAPIAdapter(AbstractContextManager):
    def __init__(
        self,
        db_path: Path,
        handler_type: type[TestLzugHandler] = TestLzugHandler,
        *,
        include_legacy_routes: bool = False,
    ):
        self.db_path = db_path
        self.handler_type = handler_type
        self.client: TestClient | None = None
        self.credentials: SessionCredentials | None = None

    def __enter__(self) -> FastAPIAdapter:
        config = FastAPIConfig(
            db_path=self.db_path,
            session_cookie_name=self.handler_type.session_cookie_name,
            csrf_cookie_name=self.handler_type.csrf_cookie_name,
            cookie_secure=self.handler_type.cookie_secure,
            https_only=self.handler_type.https_only,
            cors_allowed_origins=self.handler_type.cors_allowed_origins,
            max_request_bytes=self.handler_type.max_request_bytes,
            session_ttl=self.handler_type.session_ttl,
            static_dir=self.handler_type.static_dir,
            runtime_policy=self.handler_type.runtime_policy,
            auth_rate_limiter=self.handler_type.auth_rate_limiter,
            map_provider=self.handler_type.map_provider,
        )
        self.client = TestClient(create_app(config), base_url="http://127.0.0.1")
        if is_ready(self.db_path):
            self.credentials = AuthenticationRepository(self.db_path).create_session(1)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        credentials: SessionCredentials | None = None,
        request_headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> AdapterResponse:
        if self.client is None:
            raise RuntimeError("FastAPIAdapter must be used as a context manager")
        headers = dict(request_headers or {})
        active = credentials or self.credentials
        if authenticated and active is not None:
            headers["Cookie"] = (
                f"{self.handler_type.session_cookie_name}={active.token}; "
                f"{self.handler_type.csrf_cookie_name}={active.csrf_token}"
            )
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                headers["X-CSRF-Token"] = active.csrf_token
        if raw_body is not None and payload is not None:
            raise ValueError("Use payload or raw_body, not both")
        response = (
            self.client.request(method, path, content=raw_body, headers=headers)
            if raw_body is not None
            else self.client.request(method, path, json=payload, headers=headers)
        )
        return AdapterResponse(
            response.status_code,
            {name.lower(): value for name, value in response.headers.items()},
            response.content,
        )


class ApiServer(FastAPIAdapter):
    """Historical test name now backed directly by the canonical FastAPI app."""

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, **kwargs):
        response = super().request(method, path, payload, **kwargs)
        return response.status, response.json

    def request_raw(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        credentials: SessionCredentials | None = None,
        request_headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        response = super().request(
            method,
            path,
            payload,
            authenticated=authenticated,
            credentials=credentials,
            request_headers=request_headers,
            raw_body=raw_body,
        )
        return response.status, response.headers, response.body


class LegacyAdapter(FastAPIAdapter):
    """Retained test fixture name; both sides now exercise the same adapter."""


def assert_status(actual: int, expected: HTTPStatus) -> None:
    if actual != expected:
        raise AssertionError(f"Expected HTTP {expected.value}, got {actual}")
