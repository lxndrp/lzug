from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated
from unittest.mock import patch

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from backend.auth import AuthenticationRepository
from backend.database import session_scope
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_dependencies import (
    BodyContext,
    Context,
    ManageRoundContext,
    ReadContext,
    access_context,
    request_context,
    round_access,
)
from backend.models import COMMITTEE, COMMITTEE_MEMBER, EXAM_ROUND, Committee
from backend.repositories import ResourceRepository
from backend.runtime_policy import ProductRuntimePolicy
from backend.tests.helpers import TempDatabase
from backend.transport import RequestContext


class FastAPIDependencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = self.enterContext(TempDatabase())
        self.auth = AuthenticationRepository(self.db_path)
        self.chair = self.auth.create_session(1)
        self.member = self.auth.create_session(2)
        operator = self.auth.create_account("operator@demo.lzug.invalid", is_operator=True)
        self.operator = self.auth.create_session(operator["id"])
        self.config = FastAPIConfig(
            db_path=self.db_path, session_cookie_name="session", max_request_bytes=128
        )
        self.app = create_app(self.config)
        self.client = self.enterContext(TestClient(self.app, base_url="https://testserver"))

    def headers(self, credentials=None, *, csrf: bool = True) -> dict[str, str]:
        credentials = credentials or self.chair
        result = {"Cookie": f"session={credentials.token}"}
        if csrf:
            result["X-CSRF-Token"] = credentials.csrf_token
        return result

    def assert_error(self, response, status: int, message: str) -> None:
        self.assertEqual(status, response.status_code, response.text)
        self.assertEqual({"error": message}, response.json())
        self.assertEqual("no-store", response.headers["cache-control"])
        self.assertEqual("nosniff", response.headers["x-content-type-options"])

    def test_router_dependencies_share_one_context_and_authentication_per_request(self) -> None:
        router = APIRouter(prefix="/dependency-test", dependencies=[Depends(request_context)])
        contexts = []

        @router.get("/scope")
        def scope(first: ReadContext, second: ReadContext, raw: Context):
            self.assertIs(first, second)
            self.assertIs(first, raw)
            contexts.append(first)
            return {"committees": sorted(first.authorization_scope.committee_ids)}

        fallback = self.app.router.routes.pop()
        self.app.include_router(router)
        self.app.router.routes.append(fallback)
        original = RequestContext.require_authenticated
        with patch.object(
            RequestContext, "require_authenticated", autospec=True, side_effect=original
        ) as authenticate:
            for credentials in (self.chair, self.member):
                response = self.client.get(
                    "/dependency-test/scope", headers=self.headers(credentials)
                )
                self.assertEqual({"committees": [1]}, response.json())
            self.assertEqual(2, authenticate.call_count)
        self.assertIsNot(contexts[0], contexts[1])

    def test_session_and_actor_boundaries_keep_operator_and_inactive_membership_distinct(
        self,
    ) -> None:
        self.assertEqual(
            200, self.client.get("/api/session", headers=self.headers(self.operator)).status_code
        )
        self.assert_error(
            self.client.get("/api/committees", headers=self.headers(self.operator)),
            403,
            "Forbidden.",
        )
        self.assertEqual(
            200,
            self.client.get("/api/exam-venues", headers=self.headers(self.operator)).status_code,
        )
        member_id = self.auth.authenticate(self.member.token).committee_member_id
        ResourceRepository(self.db_path).update(COMMITTEE_MEMBER, member_id, {"is_active": 0})
        for path in ("/api/committees", "/api/exam-venues"):
            self.assert_error(
                self.client.get(path, headers=self.headers(self.member)), 403, "Forbidden."
            )
        self.assertEqual(
            200, self.client.get("/api/session", headers=self.headers(self.member)).status_code
        )

    def test_absent_expired_revoked_and_invalid_sessions_never_reach_the_handler(self) -> None:
        expired = self.auth.create_session(1, now=datetime.now(UTC) - timedelta(days=1))
        revoked = self.auth.create_session(1)
        self.auth.revoke_session(revoked.token, reason="test")
        for cookie in (None, "invalid", expired.token, revoked.token):
            with self.subTest(cookie_state="absent" if cookie is None else "invalid"):
                headers = {} if cookie is None else {"Cookie": f"session={cookie}"}
                self.assert_error(
                    self.client.get("/api/committees", headers=headers),
                    401,
                    "Authentication required.",
                )

    def test_csrf_precedes_membership_and_json_errors(self) -> None:
        path = "/api/persons"
        self.assert_error(self.client.post(path, content=b"{"), 401, "Authentication required.")
        for credentials in (self.chair, self.operator):
            self.assert_error(
                self.client.post(path, content=b"{", headers=self.headers(credentials, csrf=False)),
                403,
                "CSRF validation failed.",
            )
        self.assert_error(
            self.client.post(path, content=b"{", headers=self.headers(self.operator)),
            403,
            "Forbidden.",
        )
        self.assert_error(
            self.client.post(path, content=b"{", headers=self.headers()),
            415,
            "Content-Type must be application/json.",
        )
        response = self.client.post(
            path, content=b"{", headers={**self.headers(), "Content-Type": "application/json"}
        )
        self.assertEqual(400, response.status_code)
        self.assertIn("error", response.json())

    def test_body_framing_precedes_routing_and_keeps_security_headers(self) -> None:
        cases = (
            ({"Content-Length": "-1"}, 400, "Invalid Content-Length"),
            ({"Content-Length": "bad"}, 400, "Invalid Content-Length"),
            ({"Transfer-Encoding": "chunked"}, 400, "Transfer-Encoding is not supported"),
            ({"Content-Length": "129"}, 413, "Request body exceeds 128 bytes."),
        )
        for path in ("/api/persons", "/api/missing", "/missing"):
            for headers, status, message in cases:
                with self.subTest(path=path, headers=headers):
                    self.assert_error(
                        self.client.post(path, content=b"{}", headers=headers), status, message
                    )
        self.assert_error(
            self.client.post(
                "/api/persons",
                content=b" " * 129,
                headers={
                    **self.headers(),
                    "Content-Length": "1",
                    "Content-Type": "application/json",
                },
            ),
            413,
            "Request body exceeds 128 bytes.",
        )

    def test_typed_venue_identifiers_keep_validation_before_authentication(self) -> None:
        for method, path, parameter in (
            ("GET", "/api/exam-venues/not-an-id", "id"),
            ("PATCH", "/api/exam-rooms/not-an-id", "id"),
            ("DELETE", "/api/exam-venue-contacts/not-an-id", "id"),
            ("PATCH", "/api/locations/not-an-id", "id"),
            ("POST", "/api/exam-venue-changes/not-an-id/consequences/retry", "audit_id"),
        ):
            with self.subTest(path=path):
                response = self.client.request(method, path, content=b"{")
                self.assertEqual(422, response.status_code, response.text)
                self.assertEqual(
                    [
                        {
                            "type": "int_parsing",
                            "loc": ["path", parameter],
                            "msg": (
                                "Input should be a valid integer, "
                                "unable to parse string as an integer"
                            ),
                            "input": "not-an-id",
                        }
                    ],
                    response.json()["detail"],
                )
        self.assert_error(
            self.client.get("/api/persons/not-an-id"), 401, "Authentication required."
        )

    def test_round_dependency_delegates_read_and_management_scope_without_disclosure(self) -> None:
        router = APIRouter(prefix="/dependency-round")

        @router.get("/{id}")
        def read(context: Annotated[RequestContext, Depends(round_access(access_context()))]):
            return {"allowed": True}

        @router.get("/{id}/manage")
        def manage(context: ManageRoundContext):
            return {"allowed": True}

        fallback = self.app.router.routes.pop()
        self.app.include_router(router)
        self.app.router.routes.append(fallback)
        repository = ResourceRepository(self.db_path)
        foreign = repository.create(COMMITTEE, {"name": "Feenwald", "occupation": "FI"})
        with session_scope(self.db_path) as session:
            session.get(Committee, foreign["id"]).bootstrap_state = "ready"
        foreign_member = repository.create(
            COMMITTEE_MEMBER,
            {
                "person_id": self.auth.authenticate(self.member.token).person_id,
                "committee_id": foreign["id"],
                "member_status": "ordinary",
                "committee_role": "chair",
                "representing_side": "employer",
                "is_active": 1,
            },
        )
        foreign_round = repository.create(
            EXAM_ROUND,
            {
                "committee_id": foreign["id"],
                "exam_half_year_id": 1,
                "name": "Fremde Runde",
                "created_by_member_id": foreign_member["id"],
            },
        )
        self.assertEqual(
            200,
            self.client.get("/dependency-round/1", headers=self.headers(self.member)).status_code,
        )
        self.assertEqual(
            200, self.client.get("/dependency-round/1/manage", headers=self.headers()).status_code
        )
        self.assert_error(
            self.client.get("/dependency-round/1/manage", headers=self.headers(self.member)),
            403,
            "Forbidden.",
        )
        for round_id in (foreign_round["id"], 999999):
            for suffix in ("", "/manage"):
                self.assert_error(
                    self.client.get(
                        f"/dependency-round/{round_id}{suffix}", headers=self.headers()
                    ),
                    403,
                    "Forbidden.",
                )

    def test_runtime_policy_receives_method_and_route_before_payload_validation(self) -> None:
        calls = []

        class Policy(ProductRuntimePolicy):
            def authorize_mutation(self, context, method, path_parts, auth):
                calls.append((method, path_parts, auth.account_id))
                raise PermissionError("Runtime denies mutation")

        self.app.state.lzug_config = replace(self.config, runtime_policy=Policy())
        self.assert_error(
            self.client.patch("/api/persons/1", content=b"{", headers=self.headers()),
            403,
            "Runtime denies mutation",
        )
        self.assertEqual([("PATCH", ["persons", "1"], 1)], calls)

    def test_context_uses_runtime_database_and_response_cookies_are_preserved(self) -> None:
        selected = self.enterContext(TempDatabase())
        selected_auth = AuthenticationRepository(selected)
        credentials = selected_auth.create_session(1)
        calls = []

        class Policy(ProductRuntimePolicy):
            def database_for_request(self, default, token):
                calls.append((default, token))
                return selected

        self.app.state.lzug_config = replace(self.config, runtime_policy=Policy())
        response = self.client.post("/api/session/rotate", headers=self.headers(credentials))
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([(self.db_path, credentials.token)], calls)
        cookies = response.headers.get_list("set-cookie")
        self.assertEqual(2, len(cookies))
        self.assertTrue(
            any(
                "session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
                for cookie in cookies
            )
        )
        self.assertIsNone(selected_auth.authenticate(credentials.token))
        self.assertEqual(200, self.client.get("/api/session").status_code)
        response = self.client.post(
            "/api/session/logout", headers={"X-CSRF-Token": self.client.cookies["lzug_csrf"]}
        )
        self.assertEqual(204, response.status_code)
        self.assertEqual(2, len(response.headers.get_list("set-cookie")))
        self.assert_error(self.client.get("/api/session"), 401, "Authentication required.")

    def test_body_dependency_works_on_an_independent_router(self) -> None:
        router = APIRouter(prefix="/dependency-body")

        @router.post("/json")
        def echo(context: BodyContext):
            return context.read_json()

        fallback = self.app.router.routes.pop()
        self.app.include_router(router)
        self.app.router.routes.append(fallback)
        self.assertEqual(
            {"ok": True}, self.client.post("/dependency-body/json", json={"ok": True}).json()
        )

    def test_declarative_parameters_do_not_leak_context_into_openapi(self) -> None:
        for item in self.app.openapi()["paths"].values():
            for operation in item.values():
                for parameter in operation.get("parameters", []):
                    self.assertNotIn(
                        parameter["name"],
                        {"context", "request", "body", "actor", "csrf", "mutation", "operator"},
                    )


if __name__ == "__main__":
    unittest.main()
