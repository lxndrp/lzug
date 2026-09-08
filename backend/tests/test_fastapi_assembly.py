from __future__ import annotations

import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from backend.fastapi_app import register_application_routes
from backend.fastapi_assembly import FastAPIConfig, create_app


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
                venue_write_openapi,
            ) -> None:
                self.assertIs(config, resolved)
                self.assertIs(application, current_application)
                self.assertEqual({"security": [{"sessionCookie": []}]}, read_security)
                self.assertEqual(
                    {"security": [{"sessionCookie": [], "csrfHeader": []}]},
                    write_security,
                )
                self.assertEqual(
                    {
                        "security": [{"sessionCookie": [], "csrfHeader": []}],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Command"}
                                }
                            },
                        },
                    },
                    venue_write_openapi("Command"),
                )
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
            patch(
                "backend.fastapi_assembly.register_openapi_schema",
                side_effect=registrar("openapi"),
            ),
        ):
            app = create_app(config)

        self.assertIs(config, app.state.lzug_config)
        self.assertEqual(["transport-and-errors", "application-routes", "openapi"], calls)

    def test_application_route_boundary_registers_each_route_group(self) -> None:
        expected = (
            "_register_operations_router",
            "_register_integration_router",
            "_register_round_routes",
            "_register_planning_routes",
            "_register_planning_resource_routes",
            "_register_execution_assessment_routes",
            "register_master_data_routes",
            "_register_static_route",
        )
        calls: list[str] = []
        arguments = tuple(object() for _ in range(6))

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
