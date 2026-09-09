from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import uvicorn
from fastapi import APIRouter, Request
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.server import ServerState

from backend.application.transport import RequestTooLargeError
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_dependencies import BodyContext, buffered_body
from backend.identity.auth import AuthenticationRepository
from backend.tests.helpers import TempDatabase


def request_scope(*, app, method="POST", path="/api/persons", headers=()):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
        "app": app,
        "state": {},
    }


def body_event(body=b"", *, more=False):
    return {"type": "http.request", "body": body, "more_body": more}


class BufferedBodyTests(unittest.IsolatedAsyncioTestCase):
    def request(self, events, headers=()):
        config = SimpleNamespace(max_request_bytes=8)
        app = SimpleNamespace(state=SimpleNamespace(lzug_config=config))
        receive = AsyncMock(side_effect=events)
        return Request(request_scope(app=app, headers=headers), receive), receive

    async def test_missing_or_understated_length_stops_at_first_oversized_chunk(self):
        for headers in ((), ((b"content-length", b"0"),), ((b"content-length", b"1"),)):
            for chunks in ((b"12345678", b"SECRET"), (b"SECRET" * 1000,)):
                with self.subTest(headers=headers, chunk_count=len(chunks)):
                    request, receive = self.request(
                        [*(body_event(chunk, more=True) for chunk in chunks), body_event(b"tail")],
                        headers,
                    )
                    with self.assertRaisesRegex(
                        RequestTooLargeError, "^Request body exceeds 8 bytes.$"
                    ):
                        await buffered_body(request)
                    self.assertEqual(len(chunks), receive.await_count)
                    self.assertFalse(hasattr(request.state, "raw_body"))
                    self.assertFalse(hasattr(request, "_body"))

    async def test_exact_limit_across_empty_and_multiple_events_is_cached_once(self):
        request, receive = self.request(
            [
                body_event(b"12", more=True),
                {"type": "http.request", "more_body": True},
                body_event(b"345", more=True),
                {"type": "http.request", "body": b"678"},
            ]
        )
        with patch.object(Request, "body", side_effect=AssertionError("unbounded body read")):
            first = await buffered_body(request)
            second = await buffered_body(request)
        self.assertEqual(b"12345678", first)
        self.assertIs(first, second)
        self.assertEqual(4, receive.await_count)

    async def test_empty_body_is_complete_without_optional_asgi_fields(self):
        request, receive = self.request([{"type": "http.request"}])
        self.assertEqual(b"", await buffered_body(request))
        self.assertEqual(1, receive.await_count)

    async def test_disconnect_discards_even_a_valid_json_prefix(self):
        for prefix in (b"", b"{}"):
            with self.subTest(prefix=prefix):
                request, receive = self.request(
                    [body_event(prefix, more=True), {"type": "http.disconnect"}, body_event()]
                )
                with self.assertRaisesRegex(ValueError, "^Incomplete request body.$"):
                    await buffered_body(request)
                self.assertFalse(hasattr(request.state, "raw_body"))
                self.assertEqual(2, receive.await_count)

    async def test_cancellation_propagates_without_publishing_partial_body(self):
        request, receive = self.request([body_event(b"{}", more=True), asyncio.CancelledError()])
        with self.assertRaises(asyncio.CancelledError):
            await buffered_body(request)
        self.assertFalse(hasattr(request.state, "raw_body"))
        self.assertEqual(2, receive.await_count)

    async def test_header_precheck_never_receives_body(self):
        for length, error in (
            (b"9", RequestTooLargeError),
            (b"bad", ValueError),
            (b"-1", ValueError),
        ):
            with self.subTest(length=length):
                request, receive = self.request([], ((b"content-length", length),))
                with self.assertRaises(error):
                    await buffered_body(request)
                receive.assert_not_awaited()


class RequestStreamContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_path = self.enterContext(TempDatabase())
        self.credentials = AuthenticationRepository(self.db_path).create_session(1)
        self.app = create_app(
            FastAPIConfig(
                db_path=self.db_path, session_cookie_name="lzug_session", max_request_bytes=32
            )
        )

    def auth_headers(self):
        return (
            (b"cookie", f"lzug_session={self.credentials.token}".encode()),
            (b"x-csrf-token", self.credentials.csrf_token.encode()),
        )

    async def exchange(self, events=(), *, method="POST", path="/api/persons", headers=()):
        receive = AsyncMock(side_effect=events)
        send = AsyncMock()
        scope = request_scope(app=self.app, method=method, path=path, headers=headers)
        await asyncio.wait_for(self.app(scope, receive, send), timeout=5)
        messages = [call.args[0] for call in send.await_args_list]
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return start["status"], dict(start["headers"]), body, receive, scope

    def assert_error(self, result, status, message, reads):
        actual, headers, body, receive, scope = result
        self.assertEqual(status, actual, body)
        self.assertEqual({"error": message}, json.loads(body))
        self.assertEqual(b"no-store", headers[b"cache-control"])
        self.assertEqual(b"nosniff", headers[b"x-content-type-options"])
        self.assertEqual(reads, receive.await_count)
        self.assertNotIn("raw_body", scope["state"])

    async def test_oversize_precedes_auth_and_payload_errors_without_reflection(self):
        for path, method in (
            ("/api/persons", "POST"),
            ("/api/auth/login", "POST"),
            ("/api/exam-venues/1", "DELETE"),
            ("/api/demo/session", "POST"),
        ):
            for length in ((), ((b"content-length", b"1"),)):
                with self.subTest(path=path, length=length):
                    result = await self.exchange(
                        [
                            body_event(b" " * 32, more=True),
                            body_event(b"SECRET", more=True),
                            body_event(b"unread"),
                        ],
                        path=path,
                        method=method,
                        headers=length,
                    )
                    self.assert_error(result, 413, "Request body exceeds 32 bytes.", 2)

    async def test_origin_and_header_failures_do_not_read(self):
        cases = (
            (
                ((b"origin", b"https://blocked.invalid"), (b"content-length", b"33")),
                403,
                "Cross-origin request is not allowed.",
            ),
            (((b"content-length", b"33"),), 413, "Request body exceeds 32 bytes."),
            (((b"content-length", b"bad"),), 400, "Invalid Content-Length"),
            (((b"transfer-encoding", b"chunked"),), 400, "Transfer-Encoding is not supported"),
        )
        for headers, status, message in cases:
            for path in ("/api/persons", "/api/missing"):
                with self.subTest(path=path, headers=headers):
                    self.assert_error(
                        await self.exchange(path=path, headers=headers), status, message, 0
                    )

    async def test_bodyless_paths_respond_without_receiving(self):
        cases = (
            ("GET", "/api/health", 200),
            ("GET", "/api/ready", 200),
            ("GET", "/api/persons", 200),
            ("HEAD", "/api/health", 404),
            ("GET", "/missing", 404),
            ("POST", "/api/missing", 405),
            ("DELETE", "/api/persons/999999", 403),
            ("POST", "/api/exam-venue-changes/999999/consequences/retry", 404),
            ("POST", "/api/locations", 410),
            ("PATCH", "/api/locations/1", 410),
            ("DELETE", "/api/locations/1", 410),
            ("POST", "/api/session/logout", 204),
        )
        for method, path, expected in cases:
            with self.subTest(method=method, path=path):
                status, _, body, receive, scope = await self.exchange(
                    method=method,
                    path=path,
                    headers=(*self.auth_headers(), (b"content-length", b"1")),
                )
                self.assertEqual(expected, status, body)
                receive.assert_not_awaited()
                self.assertNotIn("raw_body", scope["state"])
        result = await self.exchange(
            method="OPTIONS", headers=((b"origin", b"https://testserver"),)
        )
        self.assertEqual(204, result[0])
        result[3].assert_not_awaited()

    async def test_disconnect_is_a_fixed_error_and_does_not_run_handler(self):
        result = await self.exchange([body_event(b"{}", more=True), {"type": "http.disconnect"}])
        self.assert_error(result, 400, "Incomplete request body.", 2)

    async def test_exact_limit_reaches_a_body_route_with_json_intact(self):
        router = APIRouter()

        @router.post("/stream-test")
        def echo(first: BodyContext, second: BodyContext):
            self.assertIs(first, second)
            return first.read_json()

        fallback = self.app.router.routes.pop()
        self.app.include_router(router)
        self.app.router.routes.append(fallback)
        payload = json.dumps({"text": "ü"}, ensure_ascii=False).encode().ljust(32)
        result = await self.exchange(
            [
                body_event(payload[:11], more=True),
                body_event(payload[11:], more=True),
                body_event(),
            ],
            path="/stream-test",
            headers=((b"content-type", b"application/json"),),
        )
        self.assertEqual(200, result[0], result[2])
        self.assertEqual({"text": "ü"}, json.loads(result[2]))
        self.assertEqual(3, result[3].await_count)

    async def test_limit_does_not_require_a_ready_database(self):
        self.app = create_app(
            FastAPIConfig(
                db_path=self.db_path.parent / "absent.sqlite",
                session_cookie_name="lzug_session",
                max_request_bytes=32,
            )
        )
        result = await self.exchange([body_event(b"x" * 33, more=True)])
        self.assert_error(result, 413, "Request body exceeds 32 bytes.", 1)


class RecordingTransport(asyncio.Transport):
    """Drive the pinned Uvicorn HTTP parser without ports or network timing."""

    def __init__(self):
        self.output = bytearray()
        self.closed = False

    def get_extra_info(self, name, default=None):
        return {"sockname": ("127.0.0.1", 8000), "peername": ("127.0.0.1", 1234)}.get(name, default)

    def write(self, data):
        self.output.extend(data)

    def is_closing(self):
        return self.closed

    def close(self):
        self.closed = True

    def pause_reading(self):
        pass

    def resume_reading(self):
        pass


class UvicornBodyBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, request, *, disconnect=False):
        # These paths must never touch persistence, even with incomplete uploads.
        app = create_app(
            FastAPIConfig(
                db_path=Path("unused.sqlite"),
                session_cookie_name="lzug_session",
                max_request_bytes=32,
            )
        )
        config = uvicorn.Config(app, http="h11", lifespan="off", access_log=False, log_config=None)
        state = ServerState()
        protocol = H11Protocol(config, state, {})
        transport = RecordingTransport()
        protocol.connection_made(transport)
        try:
            protocol.data_received(request)
            if disconnect:
                protocol.connection_lost(None)
            with self.assertNoLogs("uvicorn.error", level="ERROR"):
                await asyncio.wait_for(asyncio.gather(*state.tasks), timeout=5)
            return bytes(transport.output), protocol
        finally:
            protocol.connection_lost(None)

    async def test_rejected_length_never_requests_continue_or_remaining_body(self):
        response, protocol = await self.exchange(
            b"POST /api/auth/login HTTP/1.1\r\nHost: testserver\r\n"
            b"Content-Length: 1000000\r\nExpect: 100-continue\r\n\r\n"
        )
        self.assertIn(b"HTTP/1.1 413", response)
        self.assertNotIn(b"100 Continue", response)
        self.assertEqual("http.disconnect", (await protocol.cycle.receive())["type"])

    async def test_bodyless_route_finishes_with_upload_still_pending(self):
        response, _ = await self.exchange(
            b"GET /api/health HTTP/1.1\r\nHost: testserver\r\nContent-Length: 32\r\n"
            b"Expect: 100-continue\r\n\r\n"
        )
        self.assertIn(b"HTTP/1.1 200", response)
        self.assertNotIn(b"100 Continue", response)

    async def test_disconnect_during_upload_does_not_become_an_asgi_server_error(self):
        await self.exchange(
            b"POST /api/auth/login HTTP/1.1\r\nHost: testserver\r\nContent-Length: 32\r\n\r\n{}",
            disconnect=True,
        )
