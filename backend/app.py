"""HTTP entry point that maps JSON requests onto repository and planning services."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import hateoas, openapi
from .candidate_days import CandidateDayService
from .database import DEFAULT_DB_PATH, initialize, is_available
from .models import CANDIDATE, CANDIDATE_COMMITTEE_ASSIGNMENT, Resource
from .planning import PlanningService
from .repositories import REST_RESOURCES, ResourceRepository


class LzugHandler(BaseHTTPRequestHandler):
    """Serve the versioned JSON API and its OpenAPI-backed interactive documentation.

    This adapter parses transport data, delegates domain work to services and
    repositories, and maps expected errors to HTTP responses. Endpoint details
    remain canonical in :mod:`backend.openapi`, rather than being duplicated in
    method documentation here.
    """

    db_path = DEFAULT_DB_PATH

    @property
    def repository(self) -> ResourceRepository:
        return ResourceRepository(self.db_path)

    @property
    def planning_service(self) -> PlanningService:
        return PlanningService(self.db_path)

    @property
    def candidate_day_service(self) -> CandidateDayService:
        return CandidateDayService(self.db_path)

    def do_GET(self) -> None:
        """Dispatch read, health, OpenAPI, and Swagger UI requests."""
        try:
            parsed = urlparse(self.path)
            path_parts = self.path_parts(parsed.path)
            query = parse_qs(parsed.query)

            if path_parts == []:
                self.respond(hateoas.api_root())
                return

            if path_parts == ["health"]:
                self.respond(self.health())
                return

            if path_parts == ["openapi.json"]:
                self.respond(openapi.spec())
                return

            if path_parts == ["docs"]:
                self.respond_html(self.docs_html())
                return

            if path_parts == ["round-summary"]:
                round_id = int(query.get("round_id", ["1"])[0])
                summary = self.repository.round_summary(round_id)
                if summary is None:
                    self.respond({"error": "Exam round not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.round_summary(summary, round_id))
                return

            if path_parts == ["scheduling-overview"]:
                self.respond(hateoas.scheduling_overview(self.repository.scheduling_overview()))
                return

            if path_parts == ["confirmed-plans"]:
                self.respond(hateoas.confirmed_plans(self.repository.confirmed_plans()))
                return

            if len(path_parts) == 2 and path_parts[0] == "confirmed-plan-days":
                day = self.repository.confirmed_plan_day(int(path_parts[1]))
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if path_parts and path_parts[0] == "candidate-committee-assignments":
                if len(path_parts) == 1:
                    candidate_id = query.get("candidate_id", [None])[0]
                    rows = self.repository.candidate_committee_assignments(
                        int(candidate_id) if candidate_id is not None else None
                    )
                    self.respond(
                        hateoas.collection(
                            "candidate-committee-assignments",
                            CANDIDATE_COMMITTEE_ASSIGNMENT,
                            rows,
                            parsed.query,
                            allow_create=False,
                            allow_item_mutation=False,
                        )
                    )
                    return
                if len(path_parts) == 2:
                    row = self.repository.get(CANDIDATE_COMMITTEE_ASSIGNMENT, int(path_parts[1]))
                    if row is None:
                        self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                        return
                    self.respond(
                        hateoas.resource_item(
                            "candidate-committee-assignments",
                            CANDIDATE_COMMITTEE_ASSIGNMENT,
                            row,
                            allow_item_mutation=False,
                        )
                    )
                    return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            entity = REST_RESOURCES[resource_name]
            if entity_id is None:
                if resource_name in {"members", "memberships"}:
                    rows = self.repository.member_list(self.resource_filters(entity, query))
                elif resource_name == "candidates":
                    rows = self.repository.candidate_list()
                else:
                    filters = self.resource_filters(entity, query)
                    if filters:
                        rows = self.repository.list_filtered(entity, filters)
                    else:
                        rows = self.repository.list(entity)
                self.respond(
                    hateoas.collection(
                        resource_name,
                        entity,
                        rows,
                        parsed.query,
                    )
                )
                return

            row = (
                self.repository.member_get(entity_id)
                if resource_name in {"members", "memberships"}
                else self.repository.get(entity, entity_id)
            )
            if row is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond(hateoas.resource_item(resource_name, entity, row))
        except ValueError:
            self.respond({"error": "Invalid request"}, HTTPStatus.BAD_REQUEST)
        except SQLAlchemyError as error:
            self.respond({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        """Dispatch creates and planning actions, translating domain errors to HTTP."""
        try:
            path_parts = self.path_parts(urlparse(self.path).path)
            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "slots"
                and path_parts[4] == "start"
            ):
                day_id = int(path_parts[1])
                slot_id = int(path_parts[3])
                self.repository.start_exam_slot(day_id, slot_id, self.read_json())
                day = self.repository.confirmed_plan_day(day_id)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] == "request-availabilities"
            ):
                exam_round = self.planning_service.request_availabilities(int(path_parts[1]))
                self.respond(
                    hateoas.resource_item(
                        "exam-rounds",
                        REST_RESOURCES["exam-rounds"],
                        exam_round,
                    )
                )
                return

            if (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] == "confirm-plan"
            ):
                confirmed_plan = self.planning_service.confirm_plan(int(path_parts[1]))
                self.respond(hateoas.confirmed_plan(confirmed_plan))
                return

            if path_parts == ["planning-proposals"]:
                payload = self.read_json()
                round_id = int(payload.get("round_id", 1))
                proposal = self.planning_service.generate_proposal(round_id)
                self.respond(hateoas.planning_proposal(proposal), HTTPStatus.CREATED)
                return

            if path_parts == ["candidate-exam-days", "generate"]:
                payload = self.read_json()
                round_id = int(payload.get("round_id", 1))
                result = self.candidate_day_service.generate(round_id)
                self.respond(hateoas.candidate_day_generation(result))
                return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None or entity_id is not None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            payload = self.read_json()
            status = HTTPStatus.CREATED
            if resource_name == "candidates":
                row = self.repository.create_candidate(payload)
            elif resource_name == "planning-settings":
                row = self.repository.save_planning_settings(payload)
                status = HTTPStatus.OK
            elif resource_name == "member-availabilities":
                row = self.repository.save_member_availability(payload)
                status = HTTPStatus.OK
            elif resource_name in {"members", "memberships"}:
                row = self.repository.create_membership(payload)
            else:
                row = self.repository.create(REST_RESOURCES[resource_name], payload)
            self.respond(
                hateoas.resource_item(
                    resource_name,
                    REST_RESOURCES[resource_name],
                    row,
                ),
                status,
            )
        except ValueError as error:
            self.respond({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except IntegrityError as error:
            self.respond({"error": str(error)}, HTTPStatus.CONFLICT)
        except SQLAlchemyError as error:
            self.respond({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PATCH(self) -> None:
        """Dispatch partial updates through the repository validation boundary."""
        try:
            path_parts = self.path_parts(urlparse(self.path).path)
            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] in {"slots", "assignments"}
                and path_parts[4] == "attendance"
            ):
                day_id = int(path_parts[1])
                entity_id = int(path_parts[3])
                payload = self.read_json()
                if path_parts[2] == "slots":
                    self.repository.save_candidate_attendance(day_id, entity_id, payload)
                else:
                    self.repository.save_member_attendance(day_id, entity_id, payload)
                day = self.repository.confirmed_plan_day(day_id)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "slots"
                and path_parts[4] == "status"
            ):
                day_id = int(path_parts[1])
                slot_id = int(path_parts[3])
                self.repository.update_exam_slot_status(day_id, slot_id, self.read_json())
                day = self.repository.confirmed_plan_day(day_id)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None or entity_id is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            payload = self.read_json()
            if resource_name == "planning-settings":
                row = self.repository.update_planning_settings(entity_id, payload)
            elif resource_name == "member-availabilities":
                row = self.repository.update_member_availability(entity_id, payload)
            elif resource_name == "candidates":
                row = self.repository.update_candidate(entity_id, payload)
            elif resource_name == "exam-rounds":
                row = self.repository.update_exam_round(entity_id, payload)
            elif resource_name in {"members", "memberships"}:
                row = self.repository.update_membership(entity_id, payload)
            else:
                row = self.repository.update(
                    REST_RESOURCES[resource_name],
                    entity_id,
                    payload,
                )
            if row is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond(
                hateoas.resource_item(
                    resource_name,
                    REST_RESOURCES[resource_name],
                    row,
                )
            )
        except ValueError as error:
            self.respond({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except IntegrityError as error:
            self.respond({"error": str(error)}, HTTPStatus.CONFLICT)
        except SQLAlchemyError as error:
            self.respond({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        try:
            resource_name, entity_id = self.resource_target(
                self.path_parts(urlparse(self.path).path)
            )
            if resource_name is None or entity_id is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            if resource_name == "candidates":
                deleted = self.repository.delete_candidate(entity_id)
            else:
                deleted = self.repository.delete(REST_RESOURCES[resource_name], entity_id)
            if not deleted:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond({}, HTTPStatus.NO_CONTENT)
        except IntegrityError as error:
            self.respond({"error": str(error)}, HTTPStatus.CONFLICT)
        except SQLAlchemyError as error:
            self.respond({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def health(self) -> dict:
        status = "ok" if is_available(self.db_path) else "unavailable"
        return hateoas.health(status)

    def resource_target(self, path_parts: list[str]) -> tuple[str | None, int | None]:
        if len(path_parts) not in (1, 2):
            return None, None
        resource_name = path_parts[0]
        if resource_name not in REST_RESOURCES:
            return None, None
        if len(path_parts) == 1:
            return resource_name, None
        return resource_name, int(path_parts[1])

    def path_parts(self, path: str) -> list[str]:
        normalized = path.strip("/")
        if normalized == "api":
            return []
        if normalized.startswith("api/"):
            normalized = normalized[4:]
        return [part for part in normalized.split("/") if part]

    def resource_filters(self, resource: Resource, query: dict[str, list[str]]) -> dict:
        aliases = {"round_id": "exam_round_id"}
        fields = set(resource.readable_fields)
        filters = {}
        for key, values in query.items():
            field = aliases.get(key, key)
            if field not in fields or not values:
                continue
            filters[field] = self.normalize_filter_value(field, values[0])
        return filters

    def normalize_filter_value(self, field: str, value: str):
        if field == "id" or field.endswith("_id") or field in {"is_active"}:
            return int(value)
        return value

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Invalid JSON body") from error
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return self.normalize_payload(payload)

    def normalize_payload(self, payload: dict) -> dict:
        normalized = dict(payload)
        if "specialization_label" in normalized:
            normalized.pop("specialization_label")
        if "attempt_number" in normalized:
            normalized["attempt_number"] = max(1, int(normalized["attempt_number"]))
        if "requires_mep" in normalized:
            normalized["requires_mep"] = self.normalize_bool(normalized["requires_mep"])
        if "is_active" in normalized:
            normalized["is_active"] = self.normalize_bool(normalized["is_active"])
        if "lunch_break_enabled" in normalized:
            normalized["lunch_break_enabled"] = self.normalize_bool(
                normalized["lunch_break_enabled"]
            )
        if "exclude_public_holidays" in normalized:
            normalized["exclude_public_holidays"] = self.normalize_bool(
                normalized["exclude_public_holidays"]
            )
        if CANDIDATE.table in normalized:
            normalized.pop(CANDIDATE.table)
        return normalized

    def normalize_bool(self, value) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return int(value != 0)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return 1
            if normalized in {"0", "false", "no", "off"}:
                return 0
        raise ValueError("Expected boolean value")

    def respond(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else self.json_bytes(payload)
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

    def respond_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_bytes(self, payload) -> bytes:
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def docs_html(self) -> str:
        return """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>lzug API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/api/openapi.json",
        dom_id: "#swagger-ui"
      });
    };
  </script>
</body>
</html>"""

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the lzug demo backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--init", action="store_true", help="Create schema before starting.")
    parser.add_argument("--seed", action="store_true", help="Load demo data with --init.")
    parser.add_argument("--reset", action="store_true", help="Delete the database before --init.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.init:
        initialize(args.db, with_seed=args.seed, reset=args.reset)

    LzugHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), LzugHandler)
    print(f"lzug backend listening on http://{args.host}:{args.port}")
    print(f"database: {args.db}")
    server.serve_forever()


if __name__ == "__main__":
    main()
