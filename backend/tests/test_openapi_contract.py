from __future__ import annotations

import copy
import re
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

from backend.contract import ContractValidationError, validate_response
from backend.database import connect
from backend.fastapi_app import FastAPIConfig, create_app
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
        if api.client is None:
            raise AssertionError("API client is not active")
        validate_response(api.client.app.openapi(), method, path, status, response)
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

    def test_confirmed_plan_revision_success_conflict_and_history_contracts(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _generated = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _confirmed = self.request(api, "POST", "/api/exam-rounds/1/confirm-plan", {})
            self.assertEqual(HTTPStatus.OK, status)

            path = "/api/exam-rounds/1/confirmed-plan"
            status, original = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)
            change = copy.deepcopy(original)
            change["reason"] = "Reihenfolge nach Rücksprache korrigiert"
            status, saved = self.request(api, "PUT", path, change)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(original["revision"] + 1, saved["revision"])
            self.assertEqual(
                "Reihenfolge nach Rücksprache korrigiert",
                saved["latest_revision"]["reason"],
            )
            self.assertEqual("succeeded", saved["consequence_status"]["derivation_status"])

            history_path = "/api/exam-rounds/1/confirmed-plan/revisions"
            status, history = self.request(api, "GET", history_path)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual([saved["latest_revision"]], history["items"])

            consequences_path = "/api/exam-rounds/1/confirmed-plan/consequences"
            status, consequences = self.request(api, "GET", consequences_path)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual([], consequences["items"])
            retry_path = (
                "/api/exam-rounds/1/confirmed-plan/revisions/"
                f"{saved['latest_revision']['id']}/consequences/retry"
            )
            status, retried = api.request("POST", retry_path, {})
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual("succeeded", retried["derivation_status"])

            stale = copy.deepcopy(original)
            stale["reason"] = "Veraltete Änderung"
            status, conflict = self.request(api, "PUT", path, stale)
            self.assertEqual(HTTPStatus.CONFLICT, status)
            self.assertEqual("confirmed_plan_conflict", conflict["error"]["code"])

    def test_consequence_failure_does_not_roll_back_the_confirmed_revision(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _generated = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _confirmed = self.request(api, "POST", "/api/exam-rounds/1/confirm-plan", {})
            self.assertEqual(HTTPStatus.OK, status)
            path = "/api/exam-rounds/1/confirmed-plan"
            status, original = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)
            change = copy.deepcopy(original)
            change["reason"] = "Folgenfehler unabhängig behandeln"

            with patch(
                "backend.plan_consequences.PlanConsequenceService.process_revision",
                side_effect=RuntimeError("simulated consequence failure"),
            ):
                status, saved = self.request(api, "PUT", path, change)

            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(original["revision"] + 1, saved["revision"])
            self.assertIn("consequence_warning", saved)
            status, persisted = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(saved["revision"], persisted["revision"])
            status, history = self.request(
                api, "GET", "/api/exam-rounds/1/confirmed-plan/revisions"
            )
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(saved["latest_revision"]["id"], history["items"][0]["id"])

    def test_confirmed_plan_revision_locks_started_day_but_accepts_later_day_change(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _generated = self.request(
                api, "POST", "/api/planning-proposals", {"round_id": 1}
            )
            self.assertEqual(HTTPStatus.CREATED, status)
            status, _confirmed = self.request(api, "POST", "/api/exam-rounds/1/confirm-plan", {})
            self.assertEqual(HTTPStatus.OK, status)

            path = "/api/exam-rounds/1/confirmed-plan"
            status, original = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)
            first_day = original["exam_days"][0]
            later_day = original["exam_days"][1]
            later_regular = [slot for slot in later_day["slots"] if slot["slot_type"] == "regular"]
            later_mep = [slot for slot in later_day["slots"] if slot["slot_type"] == "mep"]
            self.assertGreaterEqual(len(later_regular), 2)
            with connect(db_path) as connection:
                connection.execute(
                    text(
                        "UPDATE exam_slot SET execution_status = 'running', "
                        "actual_started_at = '2026-11-16T08:30:00+00:00' WHERE id = :id"
                    ),
                    {"id": first_day["slots"][0]["id"]},
                )
                connection.commit()

            later_change = copy.deepcopy(original)
            later_change["reason"] = "Späteren Prüfungstag umsortiert"
            later_change["exam_days"][1]["slots"] = [*reversed(later_regular), *later_mep]
            status, saved = self.request(api, "PUT", path, later_change)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(original["exam_days"][0], saved["exam_days"][0])
            self.assertNotEqual(original["exam_days"][1]["slots"], saved["exam_days"][1]["slots"])

            started_change = copy.deepcopy(saved)
            started_change["reason"] = "Begonnenen Prüfungstag ändern"
            started_regular = [
                slot
                for slot in started_change["exam_days"][0]["slots"]
                if slot["slot_type"] == "regular"
            ]
            started_mep = [
                slot
                for slot in started_change["exam_days"][0]["slots"]
                if slot["slot_type"] == "mep"
            ]
            started_change["exam_days"][0]["slots"] = [*reversed(started_regular), *started_mep]
            status, conflict = self.request(api, "PUT", path, started_change)
            self.assertEqual(HTTPStatus.CONFLICT, status)
            self.assertEqual("confirmed_plan_conflict", conflict["error"]["code"])

            status, persisted = self.request(api, "GET", path)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(saved["revision"], persisted["revision"])
            self.assertEqual(saved["exam_days"], persisted["exam_days"])
            status, history = self.request(api, "GET", f"{path}/revisions")
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual(1, len(history["items"]))

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

    def test_committee_administration_is_not_exposed_over_http(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            if api.client is None:
                raise AssertionError("API client is not active")
            documented = api.client.app.openapi()["paths"]

            self.assertNotIn("post", documented["/api/committees"])
            self.assertFalse(
                any(
                    path.startswith("/api/admin")
                    or "committee-bootstrap" in path
                    or "committee-deactivate" in path
                    or "committee-reactivate" in path
                    for path in documented
                )
            )

            status, response = api.request(
                "POST",
                "/api/committees",
                {"name": "Nicht per HTTP", "ihk": "IHK", "occupation": "Test"},
            )
            self.assertEqual(HTTPStatus.METHOD_NOT_ALLOWED, status)
            self.assertIsInstance(response, dict)

    def test_contract_check_rejects_an_intentionally_changed_response(self) -> None:
        """A missing mandatory field is a failing local and CI contract check."""
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, health = api.request("GET", "/api/health")
            altered_health = dict(health)
            altered_health.pop("status")

        with self.assertRaisesRegex(ContractValidationError, "missing required field 'status'"):
            validate_response(
                create_app(
                    FastAPIConfig(
                        db_path=db_path,
                        session_cookie_name="lzug_session",
                        cookie_secure=False,
                        https_only=False,
                    )
                ).openapi(),
                "GET",
                "/api/health",
                status,
                altered_health,
            )

    def test_angular_client_operations_are_documented_in_openapi(self) -> None:
        source = Path("frontend/src/app/api/planning-api.service.ts").read_text()
        operations = _angular_operations(source)
        self.assertGreater(len(operations), 0)
        with TempDatabase() as db_path:
            documented_spec = create_app(
                FastAPIConfig(
                    db_path=db_path,
                    session_cookie_name="lzug_session",
                    cookie_secure=False,
                    https_only=False,
                )
            ).openapi()
        documented = {
            (method.upper(), _route_shape(path))
            for path, item in documented_spec["paths"].items()
            for method in item
            if method in {"get", "post", "put", "patch", "delete"}
        }
        requested = {(method, _route_shape(path)) for method, path in operations}
        self.assertSetEqual(requested - documented, set())


def _angular_operations(source: str) -> list[tuple[str, str]]:
    direct_calls = re.findall(
        r"this\.http\.(get|post|put|patch|delete)<[^>]+>\(\s*([`'])(/api/.*?)\2",
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
        lambda match: (
            "{"
            + (
                "id"
                if match.group(1).startswith("this.")
                or (
                    match.group(1) == "dayId"
                    and "/slots/" not in path
                    and "/assignments/" not in path
                )
                else re.sub(r"(?<!^)([A-Z])", r"_\1", match.group(1)).lower()
            )
            + "}"
        ),
        path,
    )
    return normalized.partition("?")[0]


def _route_shape(path: str) -> str:
    """Compare URL templates without coupling client variables to OpenAPI names."""
    return re.sub(r"\{[^}]+\}", "{}", path)
