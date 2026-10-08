"""FastAPI router for exam execution, attendance, and protocol workflows."""

from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import Response

from backend.application import hateoas
from backend.application.transport import RequestContext
from backend.execution.protocol_ports import (
    ProtocolContentCommand,
    ProtocolCorrectionOpenCommand,
    ProtocolCorrectionRequestCommand,
    ProtocolResponseCommand,
    ProtocolRetentionCommand,
    ProtocolVersionCommand,
)
from backend.execution.slot_ports import AttendanceCommand, SlotStartCommand, SlotStatusCommand
from backend.persistence.models import EXAM_DAY, EXAM_DAY_ASSIGNMENT, EXAM_SLOT
from backend.presentation.exam_exports import render_protocol_export

from .api_contracts import (
    DomainResourceWrite,
    ExamAttendanceUpdateRequest,
    ExamProtocolContentRequest,
    ExamProtocolResponse,
    ExamProtocolResponseRequest,
    ExamSlotStartRequest,
    ExamSlotStatusUpdateRequest,
)
from .application import ForbiddenRequestError
from .fastapi_dependencies import BoundedBodyRoute, ReadContext, WriteContext
from .fastapi_http import payload_data
from .observability import emit_event

_OPTIONAL_OBJECT_BODY = Body(default_factory=DomainResourceWrite)


def _protocol_action(context: RequestContext, protocol_id: int, action: str, payload: dict) -> dict:
    service = context.exam_protocol_service
    version = _protocol_version_command(payload)
    actions = {
        "content": lambda: service.update_content(
            context.authorization_scope,
            protocol_id,
            ProtocolContentCommand(
                version=version["version"],
                expected_day_revision=version["expected_day_revision"],
                declaration=payload.get("declaration"),
                entries=payload.get("entries", []),
                change_reason=payload.get("change_reason"),
            ),
        ),
        "submit": lambda: service.submit(context.authorization_scope, protocol_id, version),
        "responses": lambda: service.respond(
            context.authorization_scope,
            protocol_id,
            ProtocolResponseCommand(
                version=version["version"],
                expected_day_revision=version["expected_day_revision"],
                response=payload.get("response"),
                entry_id=payload.get("entry_id"),
                statement=payload.get("statement"),
            ),
        ),
        "correction-requests": lambda: service.request_correction(
            context.authorization_scope,
            protocol_id,
            ProtocolCorrectionRequestCommand(
                version=version["version"],
                expected_day_revision=version["expected_day_revision"],
                reason=payload.get("reason"),
            ),
        ),
        "open-correction": lambda: service.open_correction(
            context.authorization_scope,
            protocol_id,
            ProtocolCorrectionOpenCommand(
                version=version["version"],
                expected_day_revision=version["expected_day_revision"],
                correction_request_id=payload.get("correction_request_id"),
                reason=payload.get("reason"),
                reopening_reference=payload.get("reopening_reference"),
            ),
        ),
        "retention": lambda: service.set_retention(
            context.authorization_scope,
            protocol_id,
            ProtocolRetentionCommand(
                rule_reference=payload.get("rule_reference"),
                retain_until=payload.get("retain_until"),
                legal_hold=payload.get("legal_hold", False),
                hold_reason=payload.get("hold_reason"),
                release_reason=payload.get("release_reason"),
            ),
        ),
    }
    try:
        return actions[action]()
    except KeyError as error:  # pragma: no cover - explicit routes supply every action
        raise ValueError("Unbekannte Protokollaktion") from error


def _protocol_write(
    context: RequestContext,
    protocol_id: int,
    action: str,
    finish,
    payload: dict,
):
    result = _protocol_action(context, protocol_id, action, payload)
    return finish(context, context.respond(result))


def _protocol_version_command(payload: dict) -> ProtocolVersionCommand:
    return {
        "version": payload.get("version"),
        "expected_day_revision": payload.get("day_revision"),
    }


def _attendance_command(payload: ExamAttendanceUpdateRequest) -> AttendanceCommand:
    data = payload.model_dump(exclude_unset=True)
    command: AttendanceCommand = {
        "status": data.get("status"),
        "expected_day_revision": data.get("day_revision"),
    }
    if "arrived_at" in data:
        command["arrived_at"] = data["arrived_at"]
    return command


def _slot_start_command(payload: ExamSlotStartRequest) -> SlotStartCommand:
    data = payload.model_dump(exclude_unset=True)
    command: SlotStartCommand = {"expected_day_revision": data.get("day_revision")}
    if "actual_started_at" in data:
        command["actual_started_at"] = data["actual_started_at"]
    return command


def _slot_status_command(payload: ExamSlotStatusUpdateRequest) -> SlotStatusCommand:
    data = payload.model_dump(exclude_unset=True)
    command: SlotStatusCommand = {
        "status": data.get("status"),
        "expected_day_revision": data.get("day_revision"),
    }
    for field in ("reason", "actual_started_at", "actual_completed_at"):
        if field in data:
            command[field] = data[field]
    return command


def _confirmed_day(context: RequestContext, day_id: int, *, finish, not_found):
    day = context.repository.confirmed_plan_day(day_id, context.authorization_scope)
    if day is None:
        return not_found()
    day["day"]["closure"] = context.exam_day_closure_service.get(
        context.authorization_scope, day_id
    )
    return finish(context, context.respond(hateoas.confirmed_plan_day(day)))


def _add_slot_start_route(router, *, finish, not_found, write_security):
    @router.post(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
        openapi_extra=write_security,
    )
    def start_slot(
        context: WriteContext,
        day_id: int,
        slot_id: int,
        payload: ExamSlotStartRequest,
    ):
        context.require_day_access(day_id, manage=True)
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_id)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        context.execution_service.start_slot(
            day_id,
            slot_id,
            _slot_start_command(payload),
            actor_member_id=actor_member_id,
        )
        return _confirmed_day(context, day_id, finish=finish, not_found=not_found)


def _add_protocol_read_routes(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/protocol",
        response_model=ExamProtocolResponse,
        openapi_extra=read_security,
    )
    def slot_protocol(context: ReadContext, day_id: int, slot_id: int):
        slot = context.repository.get(EXAM_SLOT, slot_id)
        if slot is None or slot["exam_day_id"] != day_id:
            return not_found()
        protocol = context.exam_protocol_service.get_by_slot(context.authorization_scope, slot_id)
        return not_found() if protocol is None else finish(context, context.respond(protocol))

    @router.get(
        "/api/exam-protocols/{protocol_id}",
        response_model=ExamProtocolResponse,
        openapi_extra=read_security,
    )
    def exam_protocol(context: ReadContext, protocol_id: int):
        protocol = context.exam_protocol_service.get(context.authorization_scope, protocol_id)
        return not_found() if protocol is None else finish(context, context.respond(protocol))


def _add_protocol_write_routes(router, *, finish, write_security):
    @router.patch(
        "/api/exam-protocols/{protocol_id}",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def update_exam_protocol(
        context: WriteContext,
        protocol_id: int,
        payload: ExamProtocolContentRequest,
    ):
        return _protocol_write(
            context, protocol_id, "content", finish, payload_data(context, payload)
        )

    @router.post(
        "/api/exam-protocols/{protocol_id}/submit",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def submit_exam_protocol(
        context: WriteContext,
        protocol_id: int,
        payload: DomainResourceWrite = _OPTIONAL_OBJECT_BODY,
    ):
        return _protocol_write(
            context, protocol_id, "submit", finish, payload_data(context, payload)
        )

    @router.post(
        "/api/exam-protocols/{protocol_id}/responses",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def respond_to_exam_protocol(
        context: WriteContext,
        protocol_id: int,
        payload: ExamProtocolResponseRequest,
    ):
        return _protocol_write(
            context, protocol_id, "responses", finish, payload_data(context, payload)
        )

    @router.post(
        "/api/exam-protocols/{protocol_id}/correction-requests",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def request_exam_protocol_correction(
        context: WriteContext,
        protocol_id: int,
        payload: DomainResourceWrite = _OPTIONAL_OBJECT_BODY,
    ):
        return _protocol_write(
            context, protocol_id, "correction-requests", finish, payload_data(context, payload)
        )

    @router.post(
        "/api/exam-protocols/{protocol_id}/open-correction",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def open_exam_protocol_correction(
        context: WriteContext,
        protocol_id: int,
        payload: DomainResourceWrite = _OPTIONAL_OBJECT_BODY,
    ):
        return _protocol_write(
            context, protocol_id, "open-correction", finish, payload_data(context, payload)
        )

    @router.put(
        "/api/exam-protocols/{protocol_id}/retention",
        response_model=ExamProtocolResponse,
        openapi_extra=write_security,
    )
    def set_exam_protocol_retention(
        context: WriteContext,
        protocol_id: int,
        payload: DomainResourceWrite = _OPTIONAL_OBJECT_BODY,
    ):
        return _protocol_write(
            context, protocol_id, "retention", finish, payload_data(context, payload)
        )


def _add_protocol_export_routes(router, *, finish, plain_text, read_security):
    @router.get("/api/exam-protocols/{protocol_id}/export.json", openapi_extra=read_security)
    def export_exam_protocol_json(context: ReadContext, protocol_id: int):
        result = context.exam_protocol_service.machine_export(
            context.authorization_scope, protocol_id
        )
        return finish(context, context.respond(result))

    @router.get(
        "/api/exam-protocols/{protocol_id}/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_protocol_text(context: ReadContext, protocol_id: int):
        snapshot = context.exam_protocol_service.machine_export(
            context.authorization_scope, protocol_id
        )
        result = render_protocol_export(snapshot["protocol"], snapshot["references"])
        return plain_text(context, result, f"pruefungsprotokoll-{protocol_id}.txt")


def _add_protocol_completion_route(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/protocol-completion",
        openapi_extra=read_security,
    )
    def protocol_completion(context: ReadContext, day_id: int):
        result = context.exam_protocol_service.completion_for_day(
            context.authorization_scope, day_id
        )
        return not_found() if result is None else finish(context, context.respond(result))


def _add_attendance_routes(router, *, finish, not_found, write_security):
    def attendance(
        context: RequestContext,
        day_id: int,
        entity_id: int,
        kind: str,
        payload: ExamAttendanceUpdateRequest,
    ):
        member_id = None
        if kind == "assignments":
            assignment = context.repository.get(EXAM_DAY_ASSIGNMENT, entity_id)
            member_id = assignment.get("committee_member_id") if assignment else None
        context.require_day_access(day_id, manage=kind == "slots", member_id=member_id)
        command = _attendance_command(payload)
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_id)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        if kind == "slots":
            context.execution_service.save_candidate_attendance(
                day_id, entity_id, command, actor_member_id=actor_member_id
            )
        else:
            context.execution_service.save_member_attendance(
                day_id, entity_id, command, actor_member_id=actor_member_id
            )
        return _confirmed_day(context, day_id, finish=finish, not_found=not_found)

    @router.patch(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
        openapi_extra=write_security,
    )
    def slot_attendance(
        context: WriteContext,
        day_id: int,
        slot_id: int,
        payload: ExamAttendanceUpdateRequest,
    ):
        return attendance(context, day_id, slot_id, "slots", payload)

    @router.patch(
        "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
        openapi_extra=write_security,
    )
    def assignment_attendance(
        context: WriteContext,
        day_id: int,
        assignment_id: int,
        payload: ExamAttendanceUpdateRequest,
    ):
        return attendance(context, day_id, assignment_id, "assignments", payload)


def _add_slot_status_route(router, *, finish, not_found, write_security):
    @router.patch(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
        openapi_extra=write_security,
    )
    def slot_status(
        context: WriteContext,
        day_id: int,
        slot_id: int,
        payload: ExamSlotStatusUpdateRequest,
    ):
        context.require_day_access(day_id, manage=True)
        command = _slot_status_command(payload)
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_id)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        context.execution_service.update_slot_status(
            day_id,
            slot_id,
            command,
            actor_member_id=actor_member_id,
        )
        day_record = context.repository.get(EXAM_DAY, day_id)
        if day_record and day_record.get("closure_status") == "open":
            try:
                context.calendar_service.sync_round(int(day_record["exam_round_id"]))
            except Exception:
                emit_event("backend_error", severity="error", category="calendar_processing")
        return _confirmed_day(context, day_id, finish=finish, not_found=not_found)


def create_execution_router(
    *,
    finish,
    not_found,
    plain_text,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> APIRouter:
    """Build the router that owns operational exam execution contracts."""
    router = APIRouter(route_class=BoundedBodyRoute)
    _add_slot_start_route(
        router,
        finish=finish,
        not_found=not_found,
        write_security=write_security,
    )
    _add_protocol_read_routes(
        router,
        finish=finish,
        not_found=not_found,
        read_security=read_security,
    )
    _add_protocol_write_routes(
        router,
        finish=finish,
        write_security=write_security,
    )
    _add_protocol_export_routes(
        router,
        finish=finish,
        plain_text=plain_text,
        read_security=read_security,
    )
    _add_protocol_completion_route(
        router,
        finish=finish,
        not_found=not_found,
        read_security=read_security,
    )
    _add_attendance_routes(
        router,
        finish=finish,
        not_found=not_found,
        write_security=write_security,
    )
    _add_slot_status_route(
        router,
        finish=finish,
        not_found=not_found,
        write_security=write_security,
    )
    return router
