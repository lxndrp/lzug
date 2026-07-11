from __future__ import annotations

import json
import tempfile
from contextlib import AbstractContextManager
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any

from server.app import LzugHandler
from server.database import initialize


class TestLzugHandler(LzugHandler):
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
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._previous_db_path = TestLzugHandler.db_path

    def __enter__(self) -> ApiServer:
        TestLzugHandler.db_path = self.db_path
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        TestLzugHandler.db_path = self._previous_db_path

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        status, _headers, body = self.request_raw(method, path, payload)
        return status, self._read_json(body)

    def request_raw(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        body = b""
        headers = {
            "Host": "127.0.0.1",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))

        request = (
            f"{method} {path} HTTP/1.1\r\n"
            + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
            + "\r\n"
        ).encode("utf-8") + body
        socket = FakeSocket(request)

        TestLzugHandler(
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


def assert_status(actual: int, expected: HTTPStatus) -> None:
    if actual != expected:
        raise AssertionError(f"Expected HTTP {expected.value}, got {actual}")
