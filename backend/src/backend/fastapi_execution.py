"""FastAPI router for exam execution, attendance, and protocol workflows."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from . import hateoas
from .api_contracts import (
    ExamAttendanceUpdateRequest,
    ExamProtocolContentRequest,
    ExamProtocolResponseRequest,
    ExamSlotStartRequest,
    ExamSlotStatusUpdateRequest,
)
from .application import ForbiddenRequestError
from .fastapi_dependencies import ReadContext, WriteContext
from .models import EXAM_DAY, EXAM_DAY_ASSIGNMENT, EXAM_SLOT
from .observability import emit_event
from .transport import RequestContext


def _write_contract(write_security: dict[str, object], model: type[BaseModel]) -> dict[str, object]:
    return {
        **write_security,
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}
            },
        },
    }


def _protocol_action(context: RequestContext, protocol_id: int, action: str, payload: dict) -> dict:
    service = context.exam_protocol_service
    actions = {
        "content": lambda: service.update_content(
            context.authorization_scope, protocol_id, payload
        ),
        "submit": lambda: service.submit(context.authorization_scope, protocol_id, payload),
        "responses": lambda: service.respond(context.authorization_scope, protocol_id, payload),
        "correction-requests": lambda: service.request_correction(
            context.authorization_scope, protocol_id, payload
        ),
        "open-correction": lambda: service.open_correction(
            context.authorization_scope, protocol_id, payload
        ),
        "retention": lambda: service.set_retention(
            context.authorization_scope, protocol_id, payload
        ),
    }
    try:
        return actions[action]()
    except KeyError as error:  # pragma: no cover - explicit routes supply every action
        raise ValueError("Unbekannte Protokollaktion") from error


def _protocol_write(context: RequestContext, protocol_id: str, action: str, finish):
    result = _protocol_action(context, int(protocol_id), action, context.read_json())
    return finish(context, context.respond(result))


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
        openapi_extra=_write_contract(write_security, ExamSlotStartRequest),
    )
    def start_slot(context: WriteContext, day_id: str, slot_id: str):
        day_int = int(day_id)
        context.require_day_access(day_int, manage=True)
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_int)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        context.repository.start_exam_slot(
            day_int,
            int(slot_id),
            context.read_json(),
            actor_member_id=actor_member_id,
        )
        return _confirmed_day(context, day_int, finish=finish, not_found=not_found)


def _add_protocol_read_routes(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/protocol",
        openapi_extra=read_security,
    )
    def slot_protocol(context: ReadContext, day_id: str, slot_id: str):
        slot = context.repository.get(EXAM_SLOT, int(slot_id))
        if slot is None or slot["exam_day_id"] != int(day_id):
            return not_found()
        protocol = context.exam_protocol_service.get_by_slot(
            context.authorization_scope, int(slot_id)
        )
        return not_found() if protocol is None else finish(context, context.respond(protocol))

    @router.get("/api/exam-protocols/{protocol_id}", openapi_extra=read_security)
    def exam_protocol(context: ReadContext, protocol_id: str):
        protocol = context.exam_protocol_service.get(context.authorization_scope, int(protocol_id))
        return not_found() if protocol is None else finish(context, context.respond(protocol))


def _add_protocol_write_routes(router, *, finish, write_security):
    @router.patch(
        "/api/exam-protocols/{protocol_id}",
        openapi_extra=_write_contract(write_security, ExamProtocolContentRequest),
    )
    def update_exam_protocol(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "content", finish)

    @router.post("/api/exam-protocols/{protocol_id}/submit", openapi_extra=write_security)
    def submit_exam_protocol(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "submit", finish)

    @router.post(
        "/api/exam-protocols/{protocol_id}/responses",
        openapi_extra=_write_contract(write_security, ExamProtocolResponseRequest),
    )
    def respond_to_exam_protocol(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "responses", finish)

    @router.post(
        "/api/exam-protocols/{protocol_id}/correction-requests",
        openapi_extra=write_security,
    )
    def request_exam_protocol_correction(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "correction-requests", finish)

    @router.post(
        "/api/exam-protocols/{protocol_id}/open-correction",
        openapi_extra=write_security,
    )
    def open_exam_protocol_correction(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "open-correction", finish)

    @router.put("/api/exam-protocols/{protocol_id}/retention", openapi_extra=write_security)
    def set_exam_protocol_retention(context: WriteContext, protocol_id: str):
        return _protocol_write(context, protocol_id, "retention", finish)


def _add_protocol_export_routes(router, *, finish, plain_text, read_security):
    @router.get("/api/exam-protocols/{protocol_id}/export.json", openapi_extra=read_security)
    def export_exam_protocol_json(context: ReadContext, protocol_id: str):
        result = context.exam_protocol_service.machine_export(
            context.authorization_scope, int(protocol_id)
        )
        return finish(context, context.respond(result))

    @router.get(
        "/api/exam-protocols/{protocol_id}/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_protocol_text(context: ReadContext, protocol_id: str):
        result = context.exam_protocol_service.human_export(
            context.authorization_scope, int(protocol_id)
        )
        return plain_text(context, result, f"pruefungsprotokoll-{int(protocol_id)}.txt")


def _add_protocol_completion_route(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/protocol-completion",
        openapi_extra=read_security,
    )
    def protocol_completion(context: ReadContext, day_id: str):
        result = context.exam_protocol_service.completion_for_day(
            context.authorization_scope, int(day_id)
        )
        return not_found() if result is None else finish(context, context.respond(result))


def _add_attendance_routes(router, *, finish, not_found, write_security):
    def attendance(context: RequestContext, day_id: str, entity_id: str, kind: str):
        day_int = int(day_id)
        entity_int = int(entity_id)
        member_id = None
        if kind == "assignments":
            assignment = context.repository.get(EXAM_DAY_ASSIGNMENT, entity_int)
            member_id = assignment.get("committee_member_id") if assignment else None
        context.require_day_access(day_int, manage=kind == "slots", member_id=member_id)
        payload = context.read_json()
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_int)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        if kind == "slots":
            context.repository.save_candidate_attendance(
                day_int, entity_int, payload, actor_member_id=actor_member_id
            )
        else:
            context.repository.save_member_attendance(
                day_int, entity_int, payload, actor_member_id=actor_member_id
            )
        return _confirmed_day(context, day_int, finish=finish, not_found=not_found)

    @router.patch(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
        openapi_extra=_write_contract(write_security, ExamAttendanceUpdateRequest),
    )
    def slot_attendance(context: WriteContext, day_id: str, slot_id: str):
        return attendance(context, day_id, slot_id, "slots")

    @router.patch(
        "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
        openapi_extra=_write_contract(write_security, ExamAttendanceUpdateRequest),
    )
    def assignment_attendance(context: WriteContext, day_id: str, assignment_id: str):
        return attendance(context, day_id, assignment_id, "assignments")


def _add_slot_status_route(router, *, finish, not_found, write_security):
    @router.patch(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
        openapi_extra=_write_contract(write_security, ExamSlotStatusUpdateRequest),
    )
    def slot_status(context: WriteContext, day_id: str, slot_id: str):
        day_int = int(day_id)
        context.require_day_access(day_int, manage=True)
        payload = context.read_json()
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_int)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        context.repository.update_exam_slot_status(
            day_int,
            int(slot_id),
            payload,
            actor_member_id=actor_member_id,
        )
        day_record = context.repository.get(EXAM_DAY, day_int)
        if day_record and day_record.get("closure_status") == "open":
            try:
                context.calendar_service.sync_round(int(day_record["exam_round_id"]))
            except Exception:
                emit_event("backend_error", severity="error", category="calendar_processing")
        return _confirmed_day(context, day_int, finish=finish, not_found=not_found)


def create_execution_router(
    *,
    finish,
    not_found,
    plain_text,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> APIRouter:
    """Build the router that owns operational exam execution contracts."""
    router = APIRouter()
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
