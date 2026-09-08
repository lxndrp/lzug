from __future__ import annotations

import unittest

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_planning_router import (
    MIGRATED_PLANNING_RESOURCES,
    PLANNING_DOMAIN_RESOURCES,
)
from backend.identity.auth import AuthenticationRepository
from backend.tests.helpers import TempDatabase


def api_routes(routes):
    """Yield FastAPI routes across explicit nested APIRouter ownership boundaries."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from api_routes(original_router.routes)


class FastAPIPlanningRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = self.enterContext(TempDatabase())
        authentication = AuthenticationRepository(self.db_path)
        self.chair = authentication.create_session(1)
        self.examiner = authentication.create_session(2)
        self.app = create_app(FastAPIConfig(db_path=self.db_path, session_cookie_name="session"))
        self.client = self.enterContext(TestClient(self.app, base_url="https://testserver"))

    def headers(self, credentials, *, csrf: bool = True) -> dict[str, str]:
        result = {"Cookie": f"session={credentials.token}"}
        if csrf:
            result["X-CSRF-Token"] = credentials.csrf_token
        return result

    def test_planning_routes_have_one_explicit_router_owner(self) -> None:
        expected = {
            ("GET", "/api/scheduling-overview"),
            ("GET", "/api/confirmed-plans"),
            ("GET", "/api/confirmed-plan-days/{id}"),
            ("POST", "/api/planning-proposals"),
            ("GET", "/api/exam-rounds/{id}/planning-proposal"),
            ("PUT", "/api/exam-rounds/{id}/planning-proposal"),
            ("POST", "/api/exam-rounds/{id}/confirm-plan"),
            ("GET", "/api/exam-rounds/{id}/confirmed-plan"),
            ("PUT", "/api/exam-rounds/{id}/confirmed-plan"),
            ("GET", "/api/exam-rounds/{id}/confirmed-plan/revisions"),
            ("GET", "/api/exam-rounds/{id}/confirmed-plan/consequences"),
            (
                "POST",
                "/api/exam-rounds/{id}/confirmed-plan/revisions/{revision_id}/consequences/retry",
            ),
            ("POST", "/api/candidate-exam-days/generate"),
            ("POST", "/api/exam-rounds/{id}/request-availabilities"),
        }
        for name in PLANNING_DOMAIN_RESOURCES:
            expected.update(
                {
                    ("GET", f"/api/{name}"),
                    ("POST", f"/api/{name}"),
                    ("GET", f"/api/{name}/{{id}}"),
                    ("PATCH", f"/api/{name}/{{id}}"),
                    ("DELETE", f"/api/{name}/{{id}}"),
                }
            )
        for name in MIGRATED_PLANNING_RESOURCES:
            expected.update(
                {
                    ("GET", f"/api/{name}"),
                    ("GET", f"/api/{name}/{{id}}"),
                }
            )
        expected.update(
            {
                ("POST", "/api/candidate-exam-days"),
                ("PATCH", "/api/candidate-exam-days/{id}"),
                ("DELETE", "/api/candidate-exam-days/{id}"),
            }
        )
        for name in ("exam-days", "exam-slots", "exam-day-assignments"):
            expected.update(
                {
                    ("POST", f"/api/{name}"),
                    ("PATCH", f"/api/{name}/{{id}}"),
                    ("DELETE", f"/api/{name}/{{id}}"),
                }
            )

        routes: dict[tuple[str, str], list[APIRoute]] = {}
        for route in api_routes(self.app.routes):
            for method in route.methods:
                routes.setdefault((method, route.path), []).append(route)
        for route_key in expected:
            with self.subTest(route=route_key):
                self.assertEqual(1, len(routes[route_key]))
                self.assertEqual(
                    "backend.fastapi_planning_router",
                    routes[route_key][0].endpoint.__module__,
                )
        self.assertEqual(
            "backend.fastapi_app",
            routes[("GET", "/api/exam-rounds/{id}/lifecycle")][0].endpoint.__module__,
        )

    def test_significant_planning_payloads_use_pydantic_openapi_models(self) -> None:
        document = self.app.openapi()
        requests = (
            ("post", "/api/planning-proposals", "PlanningRoundRequest"),
            ("post", "/api/candidate-exam-days/generate", "PlanningRoundRequest"),
            (
                "put",
                "/api/exam-rounds/{id}/planning-proposal",
                "PlanningProposalWriteRequest",
            ),
            (
                "put",
                "/api/exam-rounds/{id}/confirmed-plan",
                "ConfirmedPlanChangeRequest",
            ),
        )
        for method, path, model_name in requests:
            with self.subTest(method=method, path=path):
                schema = document["paths"][path][method]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(model_name, schema["title"])

        responses = (
            (
                "post",
                "/api/planning-proposals",
                "201",
                "PlanningProposalResultResponse",
            ),
            (
                "get",
                "/api/exam-rounds/{id}/planning-proposal",
                "200",
                "PlanningProposalResponse",
            ),
            (
                "put",
                "/api/exam-rounds/{id}/confirmed-plan",
                "200",
                "PlanningProposalResponse",
            ),
        )
        for method, path, status, model_name in responses:
            with self.subTest(method=method, path=path):
                schema = document["paths"][path][method]["responses"][status]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(f"#/components/schemas/{model_name}", schema["$ref"])

        schemas = document["components"]["schemas"]
        for model_name in (
            "PlanningProposalSlotPayload",
            "PlanningProposalAssignmentPayload",
            "PlanningProposalDayPayload",
            "PlanningProposalResponse",
            "PlanningProposalResultResponse",
        ):
            self.assertIn(model_name, schemas)

    def test_router_keeps_authentication_csrf_and_round_management_precedence(self) -> None:
        path = "/api/planning-proposals"
        response = self.client.post(path, content=b"{")
        self.assertEqual(401, response.status_code)
        self.assertEqual({"error": "Authentication required."}, response.json())

        response = self.client.post(
            path,
            content=b"{",
            headers=self.headers(self.chair, csrf=False),
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual({"error": "CSRF validation failed."}, response.json())

        response = self.client.post(
            path,
            json={"round_id": 1},
            headers=self.headers(self.examiner),
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual({"error": "Forbidden."}, response.json())


if __name__ == "__main__":
    unittest.main()
