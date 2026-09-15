from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from backend.api_contracts import (
    CandidateCollectionResponse,
    CandidateCreate,
    CandidateResponse,
    CandidateUpdate,
)
from backend.fastapi_app import MIGRATED_DOMAIN_RESOURCES, FastAPIConfig
from backend.fastapi_master_data import MASTER_DATA_CONTRACTS, create_master_data_router
from backend.fastapi_planning_router import PLANNING_DOMAIN_RESOURCES


class FastAPIMasterDataRouterTests(unittest.TestCase):
    def router(self):
        return create_master_data_router(
            FastAPIConfig(db_path=Path("master-data.sqlite"), session_cookie_name="session"),
            {},
            {},
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
        master_data_resources = set(MIGRATED_DOMAIN_RESOURCES) - set(PLANNING_DOMAIN_RESOURCES)
        expected = {("GET", f"/api/{resource}") for resource in master_data_resources} | {
            ("GET", f"/api/{resource}/{{id}}") for resource in master_data_resources
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

        self.assertIs(collection.response_model, CandidateCollectionResponse)
        self.assertIs(item.response_model, CandidateResponse)
        self.assertIs(create.response_model, CandidateResponse)
        self.assertIs(update.response_model, CandidateResponse)
        for route in (create, update):
            self.assertIsNotNone(route.body_field)
        self.assertIs(create.body_field.field_info.annotation, CandidateCreate)
        self.assertIs(update.body_field.field_info.annotation, CandidateUpdate)

    def test_each_generic_resource_uses_its_explicit_contract(self) -> None:
        routes = self.routes()
        for name, (
            create_model,
            update_model,
            response_model,
            collection_model,
        ) in MASTER_DATA_CONTRACTS.items():
            with self.subTest(resource=name):
                collection = routes[("GET", f"/api/{name}")]
                item = routes[("GET", f"/api/{name}/{{id}}")]
                update = routes[("PATCH", f"/api/{name}/{{id}}")]
                self.assertIs(collection.response_model, collection_model)
                self.assertIs(item.response_model, response_model)
                self.assertIs(update.response_model, response_model)
                self.assertIs(update.body_field.field_info.annotation, update_model)
                if create_model is not None:
                    create = routes[("POST", f"/api/{name}")]
                    self.assertIs(create.response_model, response_model)
                    self.assertIs(create.body_field.field_info.annotation, create_model)

    def test_partial_updates_preserve_missing_and_null_values(self) -> None:
        omitted = CandidateUpdate.model_validate({})
        explicit_null = CandidateUpdate.model_validate({"training_company": None})
        self.assertNotIn("training_company", omitted.model_fields_set)
        self.assertIn("training_company", explicit_null.model_fields_set)
        self.assertIsNone(explicit_null.training_company)

        with self.assertRaises(ValueError):
            CandidateUpdate.model_validate({"not_a_candidate_field": "rejected"})


if __name__ == "__main__":
    unittest.main()
