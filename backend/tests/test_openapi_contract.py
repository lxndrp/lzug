from __future__ import annotations

import re
import unittest
from http import HTTPStatus
from pathlib import Path

from backend.contract import ContractValidationError, validate_response
from backend.openapi import spec
from backend.repositories import REST_RESOURCES
from backend.tests.helpers import ApiServer, TempDatabase


class OpenApiContractTests(unittest.TestCase):
    def request(
        self,
        api: ApiServer,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, object]:
        status, response = api.request(method, path, payload)
        validate_response(spec(), method, path, status, response)
        return status, response

    def test_seeded_read_operations_match_the_openapi_responses(self) -> None:
        """Exercise each documented collection and item response through the HTTP adapter."""
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            for path in (
                "/api",
                "/api/health",
                "/api/round-summary?round_id=1",
                "/api/confirmed-plans",
            ):
                status, _response = self.request(api, "GET", path)
                self.assertEqual(HTTPStatus.OK, status)

            for resource_name in REST_RESOURCES:
                collection_path = f"/api/{resource_name}"
                if "exam_round_id" in REST_RESOURCES[resource_name].readable_fields:
                    collection_path = f"{collection_path}?round_id=1"
                status, collection = self.request(api, "GET", collection_path)
                self.assertEqual(HTTPStatus.OK, status)
                self.assertIsInstance(collection, dict)
                if collection["items"]:
                    item_id = collection["items"][0]["id"]
                    status, _item = self.request(api, "GET", f"/api/{resource_name}/{item_id}")
                    self.assertEqual(HTTPStatus.OK, status)

    def test_frontend_write_operations_match_the_openapi_responses(self) -> None:
        """Cover each Angular write flow with an actual API response."""
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, committee = self.request(
                api,
                "POST",
                "/api/committees",
                {"name": "PA Vertrag", "occupation": "Fachinformatiker/in"},
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _committee = self.request(
                api, "PATCH", f"/api/committees/{committee['id']}", {"name": "PA Vertrag neu"}
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, member = self.request(
                api,
                "POST",
                "/api/members",
                {
                    "first_name": "Vertrag",
                    "last_name": "Test",
                    "email": "vertrag.test@example.de",
                    "committee_id": committee["id"],
                    "member_status": "ordinary",
                    "committee_role": "member",
                    "representing_side": "employee",
                    "is_active": 1,
                },
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _member = self.request(
                api, "PATCH", f"/api/members/{member['id']}", {"is_active": 0}
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, candidate = self.request(
                api,
                "POST",
                "/api/candidates",
                {
                    "first_name": "Vertrag",
                    "last_name": "Kandidat",
                    "ihk_exam_number": "FI-2026-9999",
                    "specialization": "application_development",
                    "training_company": "Vertrag GmbH",
                    "exam_round_id": 1,
                    "attempt_number": 1,
                    "requires_mep": 0,
                },
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _candidate = self.request(
                api,
                "PATCH",
                f"/api/candidates/{candidate['id']}",
                {"training_company": "Vertrag Neu GmbH", "exam_round_id": 1},
            )
            self.assertEqual(HTTPStatus.OK, status)
            status, response = self.request(api, "DELETE", f"/api/candidates/{candidate['id']}")
            self.assertEqual(HTTPStatus.NO_CONTENT, status)
            self.assertIsNone(response)

            status, location = self.request(
                api,
                "POST",
                "/api/locations",
                {
                    "committee_id": 1,
                    "name": "Vertragsort",
                    "street": "Vertragsweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "room": "V 1",
                    "is_active": 1,
                },
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _location = self.request(
                api, "PATCH", f"/api/locations/{location['id']}", {"room": "V 2"}
            )
            self.assertEqual(HTTPStatus.OK, status)
            status, response = self.request(api, "DELETE", f"/api/locations/{location['id']}")
            self.assertEqual(HTTPStatus.NO_CONTENT, status)
            self.assertIsNone(response)

            status, _settings = self.request(
                api,
                "POST",
                "/api/planning-settings",
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W47",
                    "calendar_week_to": "2026-W49",
                    "exams_per_day": 6,
                    "max_exam_days_per_week": 3,
                    "lunch_break_enabled": 1,
                    "exclude_public_holidays": 0,
                    "holiday_subdivision_code": None,
                    "default_location_id": 1,
                    "updated_by_member_id": 1,
                },
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, candidate_day = self.request(
                api,
                "POST",
                "/api/candidate-exam-days",
                {"exam_round_id": 1, "date": "2026-12-01", "is_active": 1},
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _candidate_day = self.request(
                api, "PATCH", f"/api/candidate-exam-days/{candidate_day['id']}", {"is_active": 0}
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, availability = self.request(
                api,
                "POST",
                "/api/member-availabilities",
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": candidate_day["id"],
                    "availability": "morning",
                },
            )
            self.assertEqual(HTTPStatus.OK, status)
            status, _availability = self.request(
                api,
                "PATCH",
                f"/api/member-availabilities/{availability['id']}",
                {"availability": "pending"},
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, _generation = self.request(
                api, "POST", "/api/candidate-exam-days/generate", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.OK, status)
            status, _proposal = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _confirmed = self.request(api, "POST", "/api/exam-rounds/1/confirm-plan", {})
            self.assertEqual(HTTPStatus.OK, status)

    def test_documented_error_response_matches_the_openapi_schema(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, response = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": "not-a-number"}
            )
            self.assertEqual(HTTPStatus.BAD_REQUEST, status)
            self.assertIsInstance(response, dict)
            self.assertIn("error", response)

    def test_contract_check_rejects_an_intentionally_changed_response(self) -> None:
        """A missing mandatory field is a failing local and CI contract check."""
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, health = api.request("GET", "/api/health")
            altered_health = dict(health)
            altered_health.pop("status")

        with self.assertRaisesRegex(ContractValidationError, "missing required field 'status'"):
            validate_response(spec(), "GET", "/api/health", status, altered_health)

    def test_angular_client_operations_are_documented_in_openapi(self) -> None:
        source = Path("frontend/src/app/api/planning-api.service.ts").read_text()
        operations = _angular_operations(source)
        self.assertGreater(len(operations), 0)
        documented = {
            (method.upper(), path)
            for path, item in spec()["paths"].items()
            for method in item
            if method in {"get", "post", "patch", "delete"}
        }
        self.assertSetEqual(set(operations) - documented, set())


def _angular_operations(source: str) -> list[tuple[str, str]]:
    direct_calls = re.findall(
        r"this\.http\.(get|post|patch|delete)<[^>]+>\(\s*([`'])(/api/.*?)\2",
        source,
        flags=re.DOTALL,
    )
    collection_calls = re.findall(
        r"this\.list<[^>]+>\(\s*([`'])(/api/.*?)\1",
        source,
        flags=re.DOTALL,
    )
    operations = [(method.upper(), _client_path(path)) for method, _quote, path in direct_calls]
    operations.extend(("GET", _client_path(path)) for _quote, path in collection_calls)
    return operations


def _client_path(path: str) -> str:
    normalized = re.sub(r"\$\{[^}]+\}", "{id}", path)
    return normalized.partition("?")[0]
