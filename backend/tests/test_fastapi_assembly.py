from __future__ import annotations

import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from backend.fastapi_app import register_application_routes
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_dependencies import BoundedBodyRoute


class FastAPIAssemblyTests(unittest.TestCase):
    def test_factory_assigns_shared_boundaries_in_order(self) -> None:
        config = FastAPIConfig(db_path=Path("assembly.sqlite"), session_cookie_name="session")
        application = object()
        calls: list[str] = []

        def registrar(name: str):
            def register(
                app,
                resolved,
                current_application,
                read_security,
                write_security,
            ) -> None:
                self.assertIs(config, resolved)
                self.assertIs(application, current_application)
                self.assertEqual({}, read_security)
                self.assertEqual({}, write_security)
                self.assertIs(app.router.route_class, BoundedBodyRoute)
                calls.append(name)

            return register

        with (
            patch("backend.fastapi_assembly.ReadApplication", return_value=application),
            patch(
                "backend.fastapi_assembly.register_transport_and_errors",
                side_effect=registrar("transport-and-errors"),
            ),
            patch(
                "backend.fastapi_assembly.register_application_routes",
                side_effect=registrar("application-routes"),
            ),
        ):
            app = create_app(config)

        self.assertIs(config, app.state.lzug_config)
        self.assertEqual(["transport-and-errors", "application-routes"], calls)

    def test_fastapi_generates_the_complete_openapi_document_without_postprocessing(self) -> None:
        app = create_app(FastAPIConfig(db_path=Path(":memory:"), session_cookie_name="session"))

        self.assertIs(app.openapi.__func__, FastAPI.openapi)
        document = app.openapi()
        operation = document["paths"]["/api/candidates"]["post"]
        self.assertEqual([{"sessionCookie": []}], operation["security"])
        self.assertIn(
            "X-CSRF-Token",
            {parameter["name"] for parameter in operation["parameters"]},
        )
        self.assertEqual(
            {"type": "apiKey", "in": "cookie", "name": "lzug_session"},
            document["components"]["securitySchemes"]["sessionCookie"],
        )
        self.assertEqual(
            "#/components/schemas/ErrorResponse",
            operation["responses"]["403"]["content"]["application/json"]["schema"]["$ref"],
        )
        self.assertNotIn("201", document["paths"]["/api/scheduling-overview"]["get"]["responses"])

    def test_application_route_boundary_registers_each_route_group(self) -> None:
        expected = (
            "_register_operations_router",
            "_register_integration_router",
            "_register_round_routes",
            "_register_planning_router",
            "_register_execution_assessment_routes",
            "register_master_data_routes",
            "_register_static_route",
        )
        calls: list[str] = []
        arguments = tuple(object() for _ in range(5))

        with ExitStack() as stack:
            for name in expected:
                stack.enter_context(
                    patch(
                        f"backend.fastapi_app.{name}",
                        side_effect=lambda *args, name=name: calls.append(name),
                    )
                )
            register_application_routes(*arguments)

        self.assertEqual(list(expected), calls)


if __name__ == "__main__":
    unittest.main()
