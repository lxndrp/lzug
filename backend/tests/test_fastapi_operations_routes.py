from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.routing import APIRoute

from backend.application import ReadApplication
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_operations_routes import (
    create_auth_router,
    create_demo_router,
    create_observability_router,
    create_operations_router,
    create_runtime_router,
)


def _operations(router) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


class FastAPIOperationsRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory())
        self.config = FastAPIConfig(
            db_path=Path(directory) / "operations.sqlite", session_cookie_name="session"
        )
        self.application = ReadApplication(self.config.db_path)
        self.read_security = {"security": [{"sessionCookie": []}]}
        self.write_security = {"security": [{"sessionCookie": [], "csrfHeader": []}]}

    def test_operations_router_composes_owned_route_groups(self) -> None:
        runtime = _operations(create_runtime_router(self.application))
        demo = _operations(create_demo_router(self.config, self.read_security, self.write_security))
        authentication = _operations(create_auth_router(self.config))
        observability = _operations(create_observability_router())
        composed = _operations(
            create_operations_router(
                self.config, self.application, self.read_security, self.write_security
            )
        )

        self.assertEqual(
            {
                ("GET", "/api"),
                ("GET", "/api/docs"),
                ("GET", "/api/health"),
                ("GET", "/api/openapi.json"),
                ("GET", "/api/ready"),
            },
            runtime,
        )
        self.assertEqual(
            {
                ("GET", "/api/demo/status"),
                ("POST", "/api/demo/session"),
                ("GET", "/api/demo/scenarios"),
                ("POST", "/api/demo/reset"),
            },
            demo,
        )
        self.assertEqual(
            {
                ("POST", "/api/auth/login"),
                ("POST", "/api/auth/invitation/prepare"),
                ("POST", "/api/auth/invitation/activate"),
                ("POST", "/api/auth/recovery/prepare"),
                ("POST", "/api/auth/recovery/complete"),
                ("GET", "/api/session"),
                ("POST", "/api/session/rotate"),
                ("POST", "/api/session/logout"),
            },
            authentication,
        )
        self.assertEqual({("POST", "/api/observability/frontend-errors")}, observability)
        self.assertEqual(runtime | demo | authentication | observability, composed)

    def test_operations_generate_request_schemas_from_runtime_payload_models(self) -> None:
        document = create_app(self.config).openapi()
        expected = {
            ("/api/auth/login", "LoginRequest"),
            ("/api/auth/invitation/prepare", "TokenRequest"),
            ("/api/auth/invitation/activate", "FactorActivationRequest"),
            ("/api/auth/recovery/prepare", "TokenRequest"),
            ("/api/auth/recovery/complete", "FactorActivationRequest"),
            ("/api/observability/frontend-errors", "FrontendErrorRequest"),
        }
        for path, model in expected:
            with self.subTest(path=path):
                schema = document["paths"][path]["post"]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(model, schema["title"])


if __name__ == "__main__":
    unittest.main()
