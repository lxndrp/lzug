from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from backend.api_contracts import (
    DomainCollectionResponse,
    DomainResourceResponse,
)
from backend.fastapi_app import MIGRATED_DOMAIN_RESOURCES, FastAPIConfig
from backend.fastapi_master_data import create_master_data_router


class FastAPIMasterDataRouterTests(unittest.TestCase):
    def router(self):
        return create_master_data_router(
            FastAPIConfig(db_path=Path("master-data.sqlite"), session_cookie_name="session"),
            {"security": [{"sessionCookie": []}]},
            {"security": [{"sessionCookie": [], "csrfHeader": []}]},
            lambda model: {
                "security": [{"sessionCookie": [], "csrfHeader": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": f"#/components/schemas/{model}"}}
                    },
                },
            },
        )

    def routes(self) -> dict[tuple[str, str], APIRoute]:
        return {
            (method, route.path): route
            for route in self.router().routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }

    def test_router_owns_master_data_and_organization_endpoints(self) -> None:
        routes = self.routes()
        expected = {("GET", f"/api/{resource}") for resource in MIGRATED_DOMAIN_RESOURCES} | {
            ("GET", f"/api/{resource}/{{id}}") for resource in MIGRATED_DOMAIN_RESOURCES
        }
        expected.update(
            {
                ("GET", "/api/candidate-committee-assignments"),
                ("GET", "/api/candidate-committee-assignments/{id}"),
                ("GET", "/api/exam-venues"),
                ("POST", "/api/exam-venues"),
                ("POST", "/api/exam-venues/{id}/rooms"),
                ("POST", "/api/exam-venues/{id}/contacts"),
            }
        )

        self.assertTrue(expected <= set(routes))
        self.assertTrue(
            all(
                route.endpoint.__module__ == "backend.fastapi_master_data"
                for route in routes.values()
            )
        )
        self.assertFalse(any(path == "/api/planning-proposals" for _method, path in routes))

    def test_generic_resources_publish_pydantic_contracts(self) -> None:
        routes = self.routes()
        collection = routes[("GET", "/api/candidates")]
        item = routes[("GET", "/api/candidates/{id}")]
        create = routes[("POST", "/api/candidates")]
        update = routes[("PATCH", "/api/candidates/{id}")]

        self.assertIs(collection.response_model, DomainCollectionResponse)
        self.assertIs(item.response_model, DomainResourceResponse)
        self.assertIs(create.response_model, DomainResourceResponse)
        self.assertIs(update.response_model, DomainResourceResponse)
        for route in (create, update):
            schema = route.openapi_extra["requestBody"]["content"]["application/json"]["schema"]
            self.assertEqual("#/components/schemas/DomainResourceWrite", schema["$ref"])


if __name__ == "__main__":
    unittest.main()
