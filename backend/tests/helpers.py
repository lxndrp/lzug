from __future__ import annotations

import json
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from fastapi.testclient import TestClient

from backend.app import LzugHandler
from backend.auth import AuthenticationRepository, SessionCredentials
from backend.database import initialize, is_ready
from backend.fastapi_app import FastAPIConfig, create_app


@dataclass(frozen=True)
class AdapterResponse:
    """Transport response shared by the legacy and FastAPI test adapters."""

    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


class HttpAdapter(Protocol):
    """Minimal request contract used by adapter-independent HTTP tests."""

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


class TestLzugHandler(LzugHandler):
    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        pass

    def log_message(self, format: str, *args) -> None:
        pass


class NonClosingBytesIO(BytesIO):
    def close(self) -> None:
        self.flush()


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


class FakeSocket:
    def __init__(self, request: bytes):
        self.input = BytesIO(request)
        self.output = NonClosingBytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        if "r" in mode:
            return self.input
        return self.output

    def sendall(self, data: bytes) -> None:
        self.output.write(data)


class FakeServer:
    server_name = "127.0.0.1"
    server_port = 80


class ApiServer(AbstractContextManager):
    def __init__(self, db_path: Path, handler_type: type[TestLzugHandler] = TestLzugHandler):
        self.db_path = db_path
        self.handler_type = handler_type
        self._previous_db_path = self.handler_type.db_path

    def __enter__(self) -> ApiServer:
        self.handler_type.db_path = self.db_path
        self.credentials: SessionCredentials | None = None
        if is_ready(self.db_path):
            self.credentials = AuthenticationRepository(self.db_path).create_session(1)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.handler_type.db_path = self._previous_db_path

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
    ) -> tuple[int, Any]:
        status, _headers, body = self.request_raw(
            method,
            path,
            payload,
            authenticated=authenticated,
            credentials=credentials,
            request_headers=request_headers,
            raw_body=raw_body,
        )
        return status, self._read_json(body)

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
        if payload is not None and raw_body is not None:
            raise ValueError("Use payload or raw_body, not both")
        body = raw_body or b""
        headers = {
            "Host": "127.0.0.1",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        elif raw_body is not None:
            headers["Content-Length"] = str(len(body))
        headers.update(request_headers or {})
        active_credentials = credentials or self.credentials
        if authenticated and active_credentials is not None:
            headers["Cookie"] = (
                f"{self.handler_type.session_cookie_name}={active_credentials.token}; "
                f"{self.handler_type.csrf_cookie_name}={active_credentials.csrf_token}"
            )
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                headers["X-CSRF-Token"] = active_credentials.csrf_token

        request = (
            f"{method} {path} HTTP/1.1\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
            + "\r\n"
        ).encode("utf-8") + body
        socket = FakeSocket(request)

        self.handler_type(
            socket,
            ("127.0.0.1", 12345),
            FakeServer(),
        )

        raw_response = socket.output.getvalue()
        header_bytes, _, response_body = raw_response.partition(b"\r\n\r\n")
        status_line, _, _header_block = header_bytes.partition(b"\r\n")
        status = int(status_line.split()[1])
        response_headers = {}
        for header_line in _header_block.split(b"\r\n"):
            name, _, value = header_line.partition(b":")
            if name:
                response_headers[name.decode("ascii").lower()] = value.strip().decode("utf-8")
        return status, response_headers, response_body

    def _read_json(self, body: bytes) -> Any:
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


class LegacyAdapter(AbstractContextManager):
    """Adapter facade around the existing synchronous HTTP handler."""

    def __init__(
        self,
        db_path: Path,
        handler_type: type[TestLzugHandler] = TestLzugHandler,
    ):
        self.server = ApiServer(db_path, handler_type)

    def __enter__(self) -> LegacyAdapter:
        self.server.__enter__()
        self.credentials = self.server.credentials
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.server.__exit__(exc_type, exc_value, traceback)

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
        status, headers, body = self.server.request_raw(
            method,
            path,
            payload,
            authenticated=authenticated,
            credentials=credentials,
            request_headers=request_headers,
            raw_body=raw_body,
        )
        return AdapterResponse(status, headers, body)


class FastAPIAdapter(AbstractContextManager):
    """Adapter facade for the opt-in FastAPI core and legacy migration fallback."""

    def __init__(
        self,
        db_path: Path,
        handler_type: type[TestLzugHandler] = TestLzugHandler,
        *,
        include_legacy_routes: bool = True,
    ):
        self.db_path = db_path
        self.handler_type = handler_type
        self.include_legacy_routes = include_legacy_routes
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
        )
        self.client = TestClient(
            create_app(config, include_legacy_routes=self.include_legacy_routes)
        )
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
        active_credentials = credentials or self.credentials
        if authenticated and active_credentials is not None:
            headers["Cookie"] = (
                f"{self.handler_type.session_cookie_name}={active_credentials.token}; "
                f"{self.handler_type.csrf_cookie_name}={active_credentials.csrf_token}"
            )
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                headers["X-CSRF-Token"] = active_credentials.csrf_token
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


def assert_status(actual: int, expected: HTTPStatus) -> None:
    if actual != expected:
        raise AssertionError(f"Expected HTTP {expected.value}, got {actual}")
