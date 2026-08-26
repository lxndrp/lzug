from __future__ import annotations

import copy
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
                "/api/notifications",
                "/api/notification-overview",
                "/api/notification-problems",
                "/api/notification-channels",
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

    def test_notification_channel_write_contracts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, registration = self.request(
                api,
                "POST",
                "/api/push-subscriptions",
                {"endpoint": "https://push.example.invalid/openapi"},
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _deleted = self.request(
                api, "DELETE", f"/api/push-subscriptions/{registration['id']}"
            )
            self.assertEqual(HTTPStatus.NO_CONTENT, status)

    def test_confirmed_day_read_model_matches_success_and_not_found_contracts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _proposal = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _confirmed = self.request(api, "POST", "/api/exam-rounds/1/confirm-plan", {})
            self.assertEqual(HTTPStatus.OK, status)
            status, calendar = api.request("GET", "/api/confirmed-plans")
            self.assertEqual(HTTPStatus.OK, status)
            day_id = calendar["items"][0]["days"][0]["id"]

            status, view = self.request(api, "GET", f"/api/confirmed-plan-days/{day_id}")
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(day_id, view["day"]["id"])

            status, _missing = self.request(api, "GET", "/api/confirmed-plan-days/999999")
            self.assertEqual(HTTPStatus.NOT_FOUND, status)

    def test_planning_proposal_success_conflict_and_validation_contracts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _generated = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            path = "/api/exam-rounds/1/planning-proposal"
            status, proposal = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)

            stale = copy.deepcopy(proposal)
            status, saved = self.request(api, "PUT", path, proposal)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(proposal["revision"] + 1, saved["revision"])
            status, _conflict = self.request(api, "PUT", path, stale)
            self.assertEqual(HTTPStatus.CONFLICT, status)

            invalid = copy.deepcopy(saved)
            invalid["exam_days"][0]["slots"][0]["round_candidate_id"] = invalid["exam_days"][0][
                "slots"
            ][1]["round_candidate_id"]
            status, _validation = self.request(api, "PUT", path, invalid)
            self.assertEqual(HTTPStatus.UNPROCESSABLE_ENTITY, status)

    def test_frontend_write_operations_match_the_openapi_responses(self) -> None:
        """Cover each Angular write flow with an actual API response."""
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            committee = {"id": 1}
            status, _committee = self.request(
                api,
                "PATCH",
                "/api/committees/1",
                {"name": "Prüfungsausschuss Vertragstest Neu"},
            )
            self.assertEqual(HTTPStatus.OK, status)

            status, member = self.request(
                api,
                "POST",
                "/api/members",
                {
                    "first_name": "Testperson",
                    "last_name": "Vertrag",
                    "email": "testperson.vertrag@example.invalid",
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
                    "first_name": "Prüfling",
                    "last_name": "Vertrag",
                    "ihk_exam_number": "TEST-2026-9999",
                    "specialization": "application_development",
                    "training_company": "Testbetrieb Vertrag",
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
                {"training_company": "Testbetrieb Vertrag Neu", "exam_round_id": 1},
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
                    "name": "Prüfungszentrum Vertrag (Test)",
                    "street": "Testweg 99",
                    "postal_code": "00000",
                    "city": "Teststadt",
                    "room": "Testraum V-01",
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
            if method in {"get", "post", "put", "patch", "delete"}
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
    normalized = re.sub(
        r"\$\{([^}]+)\}",
        lambda match: "{"
        + (
            "id"
            if match.group(1).startswith("this.")
            or (match.group(1) == "dayId" and "/slots/" not in path and "/assignments/" not in path)
            else re.sub(r"(?<!^)([A-Z])", r"_\1", match.group(1)).lower()
        )
        + "}",
        path,
    )
    return normalized.partition("?")[0]
