from __future__ import annotations

from typing import Any

from .models import CANDIDATE_COMMITTEE_ASSIGNMENT
from .repositories import PLAN_AGGREGATE_RESOURCES, REST_RESOURCES
from .version import application_version

REST_SCHEMA_FIELDS = {
    "specialization": {
        "type": "string",
        "enum": [
            "application_development",
            "system_integration",
            "data_and_process_analysis",
            "digital_networking",
        ],
    },
    "availability": {
        "type": "string",
        "enum": ["full_day", "morning", "afternoon", "unavailable", "pending"],
    },
    "season": {"type": "string", "enum": ["summer", "winter"]},
    "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
    "committee_role": {
        "type": "string",
        "enum": ["chair", "deputy_chair", "member"],
    },
    "member_status": {"type": "string", "enum": ["ordinary", "deputy"]},
    "representing_side": {
        "type": "string",
        "enum": ["employer", "employee", "school"],
    },
    "slot_type": {"type": "string", "enum": ["regular", "mep"]},
    "assignment_role": {"type": "string", "enum": ["examiner", "fallback"]},
    "day_part": {"type": "string", "enum": ["morning", "afternoon", "full_day"]},
    "status": {"type": "string"},
    "mobile": {"type": ["string", "null"]},
    "fallback_status": {"type": ["string", "null"]},
    "default_location_id": {"type": ["integer", "null"]},
    "is_active": {"type": "integer", "enum": [0, 1]},
    "requires_mep": {"type": "integer", "enum": [0, 1]},
    "lunch_break_enabled": {"type": "integer", "enum": [0, 1]},
    "exclude_public_holidays": {"type": "integer", "enum": [0, 1]},
    "created_from_proposal": {"type": "integer", "enum": [0, 1]},
    "holiday_subdivision_code": {
        "type": ["string", "null"],
        "enum": [
            None,
            "DE-BB",
            "DE-BE",
            "DE-BW",
            "DE-BY",
            "DE-HB",
            "DE-HE",
            "DE-HH",
            "DE-MV",
            "DE-NI",
            "DE-NW",
            "DE-RP",
            "DE-SH",
            "DE-SL",
            "DE-SN",
            "DE-ST",
            "DE-TH",
        ],
    },
}


def spec() -> dict[str, Any]:
    paths: dict[str, Any] = {
        "/api": {
            "get": {
                "summary": "API entry point",
                "operationId": "getApiRoot",
                "responses": {"200": json_response("ApiRoot")},
            }
        },
        "/api/health": {
            "get": {
                "summary": "Health check",
                "operationId": "getHealth",
                "responses": {
                    "200": json_response("Health"),
                    "503": json_response("Health"),
                },
            }
        },
        "/api/openapi.json": {
            "get": {
                "summary": "OpenAPI specification",
                "operationId": "getOpenApiSpecification",
                "responses": {"200": json_response("OpenApiDocument")},
            }
        },
        "/api/session": {
            "get": {
                "summary": "Inspect the authenticated server-side session",
                "operationId": "getSession",
                "security": [{"sessionCookie": []}],
                "responses": {
                    "200": json_response("SessionView"),
                    "401": json_response("Error"),
                },
            }
        },
        "/api/session/rotate": {
            "post": {
                "summary": "Rotate the authenticated session",
                "operationId": "rotateSession",
                "security": [{"sessionCookie": [], "csrfHeader": []}],
                "responses": {
                    "200": json_response("SessionRotated"),
                    "401": json_response("Error"),
                    "403": json_response("Error"),
                },
            }
        },
        "/api/session/logout": {
            "post": {
                "summary": "Revoke the authenticated session",
                "operationId": "logoutSession",
                "security": [{"sessionCookie": [], "csrfHeader": []}],
                "responses": {
                    "204": {"description": "Session revoked"},
                    "401": json_response("Error"),
                    "403": json_response("Error"),
                },
            }
        },
        "/api/auth/login": {
            "post": {
                "summary": "Authenticate with password and TOTP or one recovery code",
                "operationId": "loginWithPasswordAndTotp",
                "requestBody": json_request("AuthLoginWrite"),
                "responses": {
                    "200": json_response("AuthLogin"),
                    "401": json_response("Error"),
                    "429": json_response("Error"),
                },
            }
        },
        "/api/auth/invitation/prepare": {
            "post": {
                "summary": "Prepare an invitation activation without consuming its token",
                "operationId": "prepareInvitationActivation",
                "requestBody": json_request("AuthTokenWrite"),
                "responses": {
                    "200": json_response("InvitationPreparation"),
                    "400": json_response("Error"),
                },
            }
        },
        "/api/auth/invitation/activate": {
            "post": {
                "summary": "Activate an invited account and issue recovery codes once",
                "operationId": "activateInvitation",
                "requestBody": json_request("AuthActivationWrite"),
                "responses": {
                    "200": json_response("AuthActivation"),
                    "400": json_response("Error"),
                },
            }
        },
        "/api/auth/recovery/prepare": {
            "post": {
                "summary": "Prepare recovery without consuming its operator token",
                "operationId": "prepareRecovery",
                "requestBody": json_request("AuthTokenWrite"),
                "responses": {
                    "200": json_response("RecoveryPreparation"),
                    "400": json_response("Error"),
                },
            }
        },
        "/api/auth/recovery/complete": {
            "post": {
                "summary": "Replace local factors using a one-time recovery token",
                "operationId": "completeRecovery",
                "requestBody": json_request("AuthActivationWrite"),
                "responses": {"200": json_response("AuthRecovery"), "400": json_response("Error")},
            }
        },
        "/api/round-summary": {
            "get": {
                "summary": "Round summary",
                "operationId": "getRoundSummary",
                "parameters": [query_parameter("round_id", "integer")],
                "responses": {"200": json_response("RoundSummary")},
            }
        },
        "/api/scheduling-overview": {
            "get": {
                "summary": "List scheduling organizations grouped by planning state",
                "operationId": "getSchedulingOverview",
                "responses": {"200": json_response("SchedulingOverview")},
            }
        },
        "/api/confirmed-plans": {
            "get": {
                "summary": "List confirmed exam plans grouped for the calendar view",
                "operationId": "getConfirmedPlans",
                "responses": {"200": json_response("ConfirmedPlanCalendar")},
            }
        },
        "/api/confirmed-plan-days/{id}": {
            "get": {
                "summary": "Get one confirmed exam day for operational viewing",
                "operationId": "getConfirmedPlanDay",
                "parameters": [path_parameter("id")],
                "responses": {
                    "200": json_response("ConfirmedPlanDayView"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance": {
            "patch": {
                "summary": "Record attendance for the candidate of a confirmed slot",
                "operationId": "recordCandidateAttendance",
                "parameters": [path_parameter("day_id"), path_parameter("slot_id")],
                "requestBody": json_request("AttendanceWrite"),
                "responses": {
                    "200": json_response("ConfirmedPlanDayView"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status": {
            "patch": {
                "summary": "Advance the execution status of a confirmed slot",
                "operationId": "updateConfirmedSlotStatus",
                "parameters": [path_parameter("day_id"), path_parameter("slot_id")],
                "requestBody": json_request("ExamSlotStatusWrite"),
                "responses": {
                    "200": json_response("ConfirmedPlanDayView"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance": {
            "patch": {
                "summary": "Record attendance for a confirmed day assignment",
                "operationId": "recordMemberAttendance",
                "parameters": [path_parameter("day_id"), path_parameter("assignment_id")],
                "requestBody": json_request("AttendanceWrite"),
                "responses": {
                    "200": json_response("ConfirmedPlanDayView"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start": {
            "post": {
                "summary": "Record the actual start of an eligible confirmed slot",
                "operationId": "startConfirmedSlot",
                "parameters": [path_parameter("day_id"), path_parameter("slot_id")],
                "requestBody": json_request("ExamSlotStartWrite"),
                "responses": {
                    "200": json_response("ConfirmedPlanDayView"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/candidate-committee-assignments": {
            "get": {
                "summary": "List candidate committee assignment history",
                "operationId": "listCandidateCommitteeAssignments",
                "parameters": [query_parameter("candidate_id", "integer")],
                "responses": {"200": json_response("CandidateCommitteeAssignmentCollection")},
            }
        },
        "/api/candidate-committee-assignments/{id}": {
            "get": {
                "summary": "Get candidate committee assignment history entry",
                "operationId": "getCandidateCommitteeAssignment",
                "parameters": [path_parameter("id")],
                "responses": {
                    "200": json_response("CandidateCommitteeAssignment"),
                    "404": json_response("Error"),
                },
            }
        },
        "/api/planning-proposals": {
            "post": {
                "summary": "Generate planning proposal",
                "operationId": "generatePlanningProposal",
                "requestBody": json_request("PlanningProposalRequest"),
                "responses": {
                    "201": json_response("PlanningProposal"),
                    "400": json_response("Error"),
                    "409": json_response("Error"),
                },
            }
        },
        "/api/candidate-exam-days/generate": {
            "post": {
                "summary": "Generate candidate exam days from the configured calendar weeks",
                "operationId": "generateCandidateExamDays",
                "requestBody": json_request("CandidateExamDayGenerationRequest"),
                "responses": {
                    "200": json_response("CandidateExamDayGeneration"),
                    "400": json_response("Error"),
                },
            }
        },
        "/api/exam-rounds/{id}/confirm-plan": {
            "post": {
                "summary": "Confirm planning proposal",
                "operationId": "confirmPlanningProposal",
                "parameters": [path_parameter("id")],
                "responses": {
                    "200": json_response("ConfirmedPlan"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                    "409": json_response("Error"),
                },
            }
        },
        "/api/exam-rounds/{id}/request-availabilities": {
            "post": {
                "summary": "Request committee availabilities",
                "operationId": "requestCommitteeAvailabilities",
                "parameters": [path_parameter("id")],
                "responses": {
                    "200": json_response("ExamRounds"),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                },
            }
        },
    }

    for resource_name, resource in REST_RESOURCES.items():
        schema_name = schema_ref_name(resource_name)
        collection_schema = f"{schema_name}Collection"
        collection_operations = {
            "get": {
                "summary": f"List {resource_name}",
                "operationId": operation_id("list", resource_name),
                "parameters": collection_parameters(resource),
                "responses": {"200": json_response(collection_schema)},
            }
        }
        item_operations = {
            "get": {
                "summary": f"Get {resource_name} resource",
                "operationId": operation_id("get", resource_name),
                "parameters": [path_parameter("id")],
                "responses": {"200": json_response(schema_name), "404": json_response("Error")},
            }
        }
        if resource not in PLAN_AGGREGATE_RESOURCES:
            collection_operations["post"] = {
                "summary": f"Create or update {resource_name}",
                "operationId": operation_id("create", resource_name),
                "requestBody": json_request(f"{schema_name}Write"),
                "responses": {
                    "200": json_response(schema_name),
                    "201": json_response(schema_name),
                    "400": json_response("Error"),
                    "409": json_response("Error"),
                },
            }
            item_operations["patch"] = {
                "summary": f"Update {resource_name} resource",
                "operationId": operation_id("update", resource_name),
                "parameters": [path_parameter("id")],
                "requestBody": json_request(f"{schema_name}Write"),
                "responses": {
                    "200": json_response(schema_name),
                    "400": json_response("Error"),
                    "404": json_response("Error"),
                    "409": json_response("Error"),
                },
            }
            item_operations["delete"] = {
                "summary": f"Delete {resource_name} resource",
                "operationId": operation_id("delete", resource_name),
                "parameters": [path_parameter("id")],
                "responses": {
                    "204": {"description": "Deleted"},
                    "404": json_response("Error"),
                    "409": json_response("Error"),
                },
            }
        paths[f"/api/{resource_name}"] = collection_operations
        paths[f"/api/{resource_name}/{{id}}"] = item_operations

    public_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/invitation/prepare",
        "/api/auth/invitation/activate",
        "/api/auth/recovery/prepare",
        "/api/auth/recovery/complete",
    }
    for path, operations in paths.items():
        if path in public_paths:
            continue
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            if path not in {"/api/session", "/api/session/rotate", "/api/session/logout"}:
                operation["security"] = (
                    [{"sessionCookie": [], "csrfHeader": []}]
                    if method in {"post", "patch", "delete"}
                    else [{"sessionCookie": []}]
                )
            responses = operation.setdefault("responses", {})
            responses.setdefault("401", json_response("Error"))
            responses.setdefault("403", json_response("Error"))

    schemas = {
        "ApiRoot": object_schema(
            {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "_links": link_map(),
            },
            required=("name", "version", "_links"),
        ),
        "Health": object_schema(
            {
                "status": {"type": "string"},
                "version": {"type": "string"},
                "revision": {"type": "string"},
                "_links": link_map(),
            },
            required=("status", "version", "revision", "_links"),
        ),
        "Error": object_schema({"error": {"type": "string"}}, required=("error",)),
        "AuthTokenWrite": object_schema(
            {"token": {"type": "string", "minLength": 1}}, required=("token",)
        ),
        "AuthLoginWrite": object_schema(
            {
                "email": {"type": "string", "format": "email"},
                "password": {"type": "string", "writeOnly": True},
                "second_factor": {"type": "string", "writeOnly": True},
            },
            required=("email", "password", "second_factor"),
        ),
        "AuthActivationWrite": object_schema(
            {
                "token": {"type": "string", "writeOnly": True},
                "password": {"type": "string", "writeOnly": True},
                "totp_secret": {"type": "string", "writeOnly": True},
                "totp_code": {"type": "string", "writeOnly": True, "pattern": "^[0-9]{6}$"},
            },
            required=("token", "password", "totp_secret", "totp_code"),
        ),
        "AuthAccount": object_schema(
            {
                "id": {"type": "integer"},
                "email": {"type": "string"},
                "is_operator": {"type": "boolean"},
            },
            required=("id", "email", "is_operator"),
        ),
        "AuthLogin": object_schema(
            {
                "authenticated": {"type": "boolean", "const": True},
                "account_id": {"type": "integer"},
                "expires_at": {"type": "string"},
            },
            required=("authenticated", "account_id", "expires_at"),
        ),
        "InvitationPreparation": object_schema(
            {
                "email": {"type": "string"},
                "expires_at": {"type": "string"},
                "totp_secret": {"type": "string"},
            },
            required=("email", "expires_at", "totp_secret"),
        ),
        "RecoveryPreparation": object_schema(
            {
                "email": {"type": "string"},
                "expires_at": {"type": "string"},
                "totp_secret": {"type": "string"},
            },
            required=("email", "expires_at", "totp_secret"),
        ),
        "AuthActivation": object_schema(
            {
                "activated": {"type": "boolean", "const": True},
                "account": {"$ref": "#/components/schemas/AuthAccount"},
                "recovery_codes": {"type": "array", "items": {"type": "string"}},
            },
            required=("activated", "account", "recovery_codes"),
        ),
        "AuthRecovery": object_schema(
            {
                "recovered": {"type": "boolean", "const": True},
                "account": {"$ref": "#/components/schemas/AuthAccount"},
                "recovery_codes": {"type": "array", "items": {"type": "string"}},
            },
            required=("recovered", "account", "recovery_codes"),
        ),
        "Link": object_schema(
            {
                "href": {"type": "string"},
                "method": {"type": "string"},
                "title": {"type": "string"},
            },
            required=("href",),
        ),
        "RoundSummary": object_schema(
            {
                "round": {"type": "object"},
                "counts": {"type": "object"},
                "settings": {"type": ["object", "null"]},
                "availability": {"type": "array", "items": {"type": "object"}},
                "_links": link_map(),
            },
            required=("round", "counts", "settings", "availability", "_links"),
        ),
        "SchedulingOverviewItem": object_schema(
            {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "status": {"type": "string"},
                "status_group": {
                    "type": "string",
                    "enum": ["draft", "coordination", "planning", "confirmed"],
                },
                "committee_name": {"type": "string"},
                "exam_half_year": {"$ref": "#/components/schemas/ExamHalfYears"},
                "calendar_week_from": {"type": ["string", "null"]},
                "calendar_week_to": {"type": ["string", "null"]},
                "can_continue": {"type": "boolean"},
                "_links": link_map(),
            },
            required=(
                "id",
                "name",
                "status",
                "status_group",
                "committee_name",
                "exam_half_year",
                "calendar_week_from",
                "calendar_week_to",
                "can_continue",
                "_links",
            ),
        ),
        "SchedulingOverview": object_schema(
            {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/SchedulingOverviewItem"},
                },
                "_links": link_map(),
            },
            required=("items", "_links"),
        ),
        "ConfirmedPlanCalendar": object_schema(
            {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ConfirmedPlanCalendarItem"},
                },
                "_links": link_map(),
            },
            required=("items", "_links"),
        ),
        "ConfirmedPlanCalendarItem": object_schema(
            {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "committee": {"$ref": "#/components/schemas/ConfirmedPlanCommittee"},
                "exam_half_year": {"$ref": "#/components/schemas/ExamHalfYears"},
                "days": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ConfirmedPlanDay"},
                },
            },
            required=("id", "name", "committee", "exam_half_year", "days"),
        ),
        "ConfirmedPlanDayView": object_schema(
            {
                "plan": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "committee": {"$ref": "#/components/schemas/ConfirmedPlanCommittee"},
                        "exam_half_year": {"$ref": "#/components/schemas/ExamHalfYears"},
                    },
                    "required": ("id", "name", "committee", "exam_half_year"),
                },
                "day": {"$ref": "#/components/schemas/ConfirmedPlanDay"},
                "_links": link_map(),
            },
            required=("plan", "day", "_links"),
        ),
        "ConfirmedPlanCommittee": object_schema(
            {"id": {"type": "integer"}, "name": {"type": "string"}}, required=("id", "name")
        ),
        "ConfirmedPlanDay": object_schema(
            {
                "id": {"type": "integer"},
                "date": {"type": "string"},
                "location": {"type": ["object", "null"]},
                "status_summary": {"$ref": "#/components/schemas/ExecutionStatusSummary"},
                "slots": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ConfirmedPlanSlot"},
                },
                "assignments": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/ConfirmedPlanAssignment"},
                },
            },
            required=("id", "date", "location", "status_summary", "slots", "assignments"),
        ),
        "ConfirmedPlanSlot": object_schema(
            {
                "id": {"type": "integer"},
                "starts_at": {"type": "string"},
                "ends_at": {"type": "string"},
                "sequence_number": {"type": "integer"},
                "slot_type": {"type": "string"},
                "actual_started_at": {"type": ["string", "null"]},
                "execution_status": {
                    "type": "string",
                    "enum": ["open", "running", "completed", "cancelled", "needs_follow_up"],
                },
                "status_changed_at": {"type": "string"},
                "actual_completed_at": {"type": ["string", "null"]},
                "status_reason": {"type": ["string", "null"]},
                "candidate_attendance": {"$ref": "#/components/schemas/Attendance"},
                "candidate": {"type": "object"},
            },
            required=(
                "id",
                "starts_at",
                "ends_at",
                "sequence_number",
                "slot_type",
                "actual_started_at",
                "execution_status",
                "status_changed_at",
                "actual_completed_at",
                "status_reason",
                "candidate_attendance",
                "candidate",
            ),
        ),
        "ConfirmedPlanAssignment": object_schema(
            {
                "id": {"type": "integer"},
                "assignment_role": {"type": "string"},
                "day_part": {"type": "string"},
                "fallback_status": {"type": ["string", "null"]},
                "attendance": {"$ref": "#/components/schemas/Attendance"},
                "member": {"type": "object"},
            },
            required=(
                "id",
                "assignment_role",
                "day_part",
                "fallback_status",
                "attendance",
                "member",
            ),
        ),
        "Attendance": object_schema(
            {
                "status": {
                    "type": "string",
                    "enum": ["open", "present", "late", "absent"],
                },
                "arrived_at": {"type": ["string", "null"]},
            },
            required=("status", "arrived_at"),
        ),
        "AttendanceWrite": object_schema(
            {
                "status": {
                    "type": "string",
                    "enum": ["open", "present", "late", "absent"],
                },
                "arrived_at": {"type": ["string", "null"]},
            },
            required=("status",),
        ),
        "ExecutionStatusSummary": object_schema(
            {
                status: {"type": "integer", "minimum": 0}
                for status in ("open", "running", "completed", "cancelled", "needs_follow_up")
            },
            required=("open", "running", "completed", "cancelled", "needs_follow_up"),
        ),
        "ExamSlotStatusWrite": object_schema(
            {
                "status": {
                    "type": "string",
                    "enum": ["completed", "cancelled", "needs_follow_up"],
                },
                "reason": {"type": ["string", "null"]},
            },
            required=("status",),
        ),
        "ExamSlotStartWrite": object_schema(
            {"actual_started_at": {"type": ["string", "null"]}},
        ),
        "PlanningProposalRequest": object_schema(
            {"round_id": {"type": "integer"}},
            required=("round_id",),
        ),
        "CandidateExamDayGenerationRequest": object_schema(
            {"round_id": {"type": "integer"}},
            required=("round_id",),
        ),
        "CandidateExamDayGeneration": object_schema(
            {
                "round_id": {"type": "integer"},
                "calendar_week_from": {"type": "string"},
                "calendar_week_to": {"type": "string"},
                "exclude_public_holidays": field_schema("exclude_public_holidays"),
                "holiday_subdivision_code": {"type": ["string", "null"]},
                "created_days": {"type": "array", "items": {"type": "object"}},
                "skipped_existing": {"type": "array", "items": {"type": "string"}},
                "excluded_holidays": {"type": "array", "items": {"type": "object"}},
                "counts": {"type": "object"},
                "_links": link_map(),
            },
            required=(
                "round_id",
                "calendar_week_from",
                "calendar_week_to",
                "exclude_public_holidays",
                "holiday_subdivision_code",
                "created_days",
                "skipped_existing",
                "excluded_holidays",
                "counts",
                "_links",
            ),
        ),
        "PlanningProposal": object_schema(
            {
                "round_id": {"type": "integer"},
                "status": {"type": "string"},
                "exam_days": {"type": "array", "items": {"type": "object"}},
                "validation": {"type": "object"},
                "counts": {"type": "object"},
                "_links": link_map(),
            },
            required=("round_id", "status", "exam_days", "validation", "counts", "_links"),
        ),
        "ConfirmedPlan": object_schema(
            {
                "round_id": {"type": "integer"},
                "status": {"type": "string"},
                "exam_days": {"type": "array", "items": {"type": "object"}},
                "counts": {"type": "object"},
                "_links": link_map(),
            },
            required=("round_id", "status", "exam_days", "counts", "_links"),
        ),
        "SessionView": object_schema(
            {
                "authenticated": {"type": "boolean"},
                "account_id": {"type": "integer"},
                "person_id": {"type": ["integer", "null"]},
                "committee_member_id": {"type": ["integer", "null"]},
                "is_operator": {"type": "boolean"},
            },
            required=(
                "authenticated",
                "account_id",
                "person_id",
                "committee_member_id",
                "is_operator",
            ),
        ),
        "SessionRotated": object_schema(
            {"status": {"type": "string", "const": "rotated"}, "expires_at": {"type": "string"}},
            required=("status", "expires_at"),
        ),
        "OpenApiDocument": {"type": "object"},
        "CandidateCommitteeAssignment": resource_schema(
            "candidate-committee-assignments",
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            include_links=True,
        ),
        "CandidateCommitteeAssignmentCollection": object_schema(
            {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/CandidateCommitteeAssignment"},
                },
                "_links": link_map(),
            },
            required=("items", "_links"),
        ),
    }

    for resource_name, resource in REST_RESOURCES.items():
        schema_name = schema_ref_name(resource_name)
        schemas[schema_name] = resource_schema(resource_name, resource, include_links=True)
        schemas[f"{schema_name}Write"] = resource_write_schema(resource)
        schemas[f"{schema_name}Collection"] = object_schema(
            {
                "items": {
                    "type": "array",
                    "items": {"$ref": f"#/components/schemas/{schema_name}"},
                },
                "_links": link_map(),
            },
            required=("items", "_links"),
        )

    public_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/invitation/prepare",
        "/api/auth/invitation/activate",
        "/api/auth/recovery/prepare",
        "/api/auth/recovery/complete",
    }
    for path, operations in paths.items():
        if path in public_paths or path == "/api/docs":
            continue
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            operation.setdefault("security", [{"sessionCookie": []}])
            operation.setdefault("responses", {})["401"] = json_response("Error")
            if method in {"post", "patch", "delete"} and path not in {
                "/api/session",
            }:
                operation["security"] = [{"sessionCookie": [], "csrfHeader": []}]
                operation["responses"]["403"] = json_response("Error")

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "lzug API",
            "version": application_version(),
            "description": "JSON API fuer Pruefungsrunden mit HAL-nahen HATEOAS-Links.",
        },
        "servers": [{"url": "http://127.0.0.1:8000"}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "__Host-lzug_session"},
                "csrfHeader": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            },
            "schemas": schemas,
        },
    }


def json_response(schema_name: str) -> dict[str, Any]:
    return {
        "description": "JSON response",
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}
        },
    }


def json_request(schema_name: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}
        },
    }


def object_schema(
    properties: dict[str, Any],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": True,
    }


def link_map() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": {"$ref": "#/components/schemas/Link"},
    }


def resource_schema(resource_name: str, resource, include_links: bool) -> dict[str, Any]:
    readable_fields = resource.readable_fields
    if resource_name in {"members", "memberships"}:
        readable_fields = (
            "id",
            "person_id",
            "committee_id",
            "first_name",
            "last_name",
            "email",
            "mobile",
            "email_verified_at",
            "member_status",
            "committee_role",
            "representing_side",
            "is_active",
            "created_at",
            "updated_at",
        )
    properties = {field: field_schema(field) for field in readable_fields}
    if include_links:
        properties["_links"] = link_map()
    required = (*readable_fields, "_links") if include_links else readable_fields
    return object_schema(properties, required=required)


def resource_write_schema(resource) -> dict[str, Any]:
    properties = {field: field_schema(field) for field in resource.writable_fields}
    return object_schema(properties)


def field_schema(field: str) -> dict[str, Any]:
    explicit = REST_SCHEMA_FIELDS.get(field)
    if explicit:
        return explicit
    if field == "id" or field.endswith("_id"):
        return {"type": "integer"}
    if field.endswith("_at") or field.endswith("_deadline"):
        return {"type": ["string", "null"]}
    if field in {"attempt_number", "exams_per_day", "max_exam_days_per_week"}:
        return {"type": "integer"}
    return {"type": "string"}


def path_parameter(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
    }


def query_parameter(name: str, value_type: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "query",
        "required": False,
        "schema": {"type": value_type},
    }


def collection_parameters(resource) -> list[dict[str, Any]]:
    parameters = []
    if "exam_round_id" in resource.readable_fields:
        parameters.append(query_parameter("round_id", "integer"))
    return parameters


def schema_ref_name(resource_name: str) -> str:
    return "".join(part.capitalize() for part in resource_name.split("-"))


def operation_id(action: str, resource_name: str) -> str:
    return f"{action}{schema_ref_name(resource_name)}"
