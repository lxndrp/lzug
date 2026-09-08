"""FastAPI router for assessment models and exam result workflows."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from .api_contracts import AssessmentModelBindingRequest, IndividualAssessmentRequest
from .fastapi_dependencies import ReadContext, WriteContext
from .fastapi_http import request_body, validated_payload
from .models import EXAM_SLOT
from .transport import RequestContext


def _write_contract(write_security: dict[str, object], model: type[BaseModel]) -> dict[str, object]:
    return {**write_security, **request_body(model)}


def _result_action(
    context: RequestContext,
    result_id: int,
    action: str,
    nested_id: str | None,
    payload: dict,
) -> dict:
    service = context.exam_result_service
    actions = {
        ("individual-assessments", False): lambda: service.save_individual(
            context.authorization_scope, result_id, payload
        ),
        ("individual-assessments", True): lambda: service.withdraw_individual(
            context.authorization_scope, result_id, int(nested_id), payload
        ),
        ("disclosures", False): lambda: service.disclose(
            context.authorization_scope, result_id, payload
        ),
        ("committee-assessments", False): lambda: service.determine_component(
            context.authorization_scope, result_id, payload
        ),
        ("external-results", False): lambda: service.record_external(
            context.authorization_scope, result_id, payload
        ),
        ("external-results", True): lambda: service.confirm_external(
            context.authorization_scope, result_id, int(nested_id), payload
        ),
        ("determine", False): lambda: service.determine_result(
            context.authorization_scope, result_id, payload
        ),
        ("record-confirmations", False): lambda: service.confirm_record(
            context.authorization_scope, result_id, payload
        ),
        ("corrections", False): lambda: service.open_correction(
            context.authorization_scope, result_id, payload
        ),
        ("communications", False): lambda: service.communicate(
            context.authorization_scope, result_id, payload
        ),
        ("retention", False): lambda: service.set_retention(
            context.authorization_scope, result_id, payload
        ),
    }
    try:
        return actions[(action, nested_id is not None)]()
    except KeyError as error:  # pragma: no cover - explicit routes supply every action
        raise ValueError("Unbekannte Ergebnisaktion") from error


def _result_write(
    context: RequestContext,
    result_id: str,
    action: str,
    finish,
    *,
    nested_id: str | None = None,
    model: type[BaseModel] | None = None,
):
    payload = context.read_json() if model is None else validated_payload(context, model)
    result = _result_action(context, int(result_id), action, nested_id, payload)
    return finish(context, context.respond(result))


def _add_assessment_model_routes(router, *, finish, not_found, read_security, write_security):
    @router.get("/api/assessment-model-versions", openapi_extra=read_security)
    def assessment_model_versions(context: ReadContext):
        return finish(
            context,
            context.respond(context.exam_result_service.list_models(context.authorization_scope)),
        )

    @router.post(
        "/api/assessment-model-versions",
        status_code=201,
        openapi_extra=write_security,
    )
    def create_assessment_model_version(context: WriteContext):
        result = context.exam_result_service.create_model(
            context.authorization_scope, context.read_json()
        )
        return finish(context, context.respond(result, HTTPStatus.CREATED))

    @router.get(
        "/api/exam-rounds/{round_id}/assessment-model-binding",
        openapi_extra=read_security,
    )
    def assessment_model_binding(context: ReadContext, round_id: str):
        binding = context.exam_result_service.get_round_binding(
            context.authorization_scope, int(round_id)
        )
        return not_found() if binding is None else finish(context, context.respond(binding))

    @router.post(
        "/api/exam-rounds/{round_id}/assessment-model-binding",
        openapi_extra=_write_contract(write_security, AssessmentModelBindingRequest),
    )
    def bind_assessment_model(context: WriteContext, round_id: str):
        result = context.exam_result_service.bind_round(
            context.authorization_scope,
            int(round_id),
            validated_payload(context, AssessmentModelBindingRequest),
        )
        return finish(context, context.respond(result))


def _add_result_read_routes(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/result",
        openapi_extra=read_security,
    )
    def slot_result(context: ReadContext, day_id: str, slot_id: str):
        slot = context.repository.get(EXAM_SLOT, int(slot_id))
        if slot is None or slot["exam_day_id"] != int(day_id):
            return not_found()
        result = context.exam_result_service.get_by_slot(context.authorization_scope, int(slot_id))
        return not_found() if result is None else finish(context, context.respond(result))

    @router.get("/api/exam-results/{result_id}", openapi_extra=read_security)
    def exam_result(context: ReadContext, result_id: str):
        result = context.exam_result_service.get(context.authorization_scope, int(result_id))
        return not_found() if result is None else finish(context, context.respond(result))


def _add_individual_result_routes(router, *, finish, write_security):
    @router.post(
        "/api/exam-results/{result_id}/individual-assessments",
        openapi_extra=_write_contract(write_security, IndividualAssessmentRequest),
    )
    def save_individual_assessment(context: WriteContext, result_id: str):
        return _result_write(
            context,
            result_id,
            "individual-assessments",
            finish,
            model=IndividualAssessmentRequest,
        )

    @router.post(
        "/api/exam-results/{result_id}/individual-assessments/{assessment_id}/withdraw",
        openapi_extra=write_security,
    )
    def withdraw_individual_assessment(context: WriteContext, result_id: str, assessment_id: str):
        return _result_write(
            context,
            result_id,
            "individual-assessments",
            finish,
            nested_id=assessment_id,
        )

    @router.post("/api/exam-results/{result_id}/disclosures", openapi_extra=write_security)
    def disclose_individual_assessments(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "disclosures", finish)

    @router.post(
        "/api/exam-results/{result_id}/committee-assessments",
        openapi_extra=write_security,
    )
    def determine_committee_assessment(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "committee-assessments", finish)


def _add_final_result_routes(router, *, finish, write_security):
    @router.post("/api/exam-results/{result_id}/external-results", openapi_extra=write_security)
    def record_external_result(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "external-results", finish)

    @router.post(
        "/api/exam-results/{result_id}/external-results/{external_result_id}/confirm",
        openapi_extra=write_security,
    )
    def confirm_external_result(context: WriteContext, result_id: str, external_result_id: str):
        return _result_write(
            context,
            result_id,
            "external-results",
            finish,
            nested_id=external_result_id,
        )

    @router.post("/api/exam-results/{result_id}/determine", openapi_extra=write_security)
    def determine_exam_result(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "determine", finish)

    @router.post(
        "/api/exam-results/{result_id}/record-confirmations",
        openapi_extra=write_security,
    )
    def confirm_result_record(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "record-confirmations", finish)

    @router.post("/api/exam-results/{result_id}/corrections", openapi_extra=write_security)
    def open_result_correction(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "corrections", finish)

    @router.post("/api/exam-results/{result_id}/communications", openapi_extra=write_security)
    def communicate_exam_result(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "communications", finish)

    @router.put("/api/exam-results/{result_id}/retention", openapi_extra=write_security)
    def set_result_retention(context: WriteContext, result_id: str):
        return _result_write(context, result_id, "retention", finish)


def _add_result_export_routes(router, *, finish, plain_text, read_security):
    @router.get("/api/exam-results/{result_id}/export.json", openapi_extra=read_security)
    def export_exam_result_json(context: ReadContext, result_id: str):
        result = context.exam_result_service.machine_export(
            context.authorization_scope, int(result_id)
        )
        return finish(context, context.respond(result))

    @router.get(
        "/api/exam-results/{result_id}/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_result_text(context: ReadContext, result_id: str):
        result = context.exam_result_service.human_export(
            context.authorization_scope, int(result_id)
        )
        return plain_text(context, result, f"ergebnisniederschrift-{int(result_id)}.txt")


def _add_result_completion_route(router, *, finish, not_found, read_security):
    @router.get(
        "/api/confirmed-plan-days/{day_id}/result-completion",
        openapi_extra=read_security,
    )
    def result_completion(context: ReadContext, day_id: str):
        result = context.exam_result_service.completion_for_day(
            context.authorization_scope, int(day_id)
        )
        return not_found() if result is None else finish(context, context.respond(result))


def create_assessment_router(
    *,
    finish,
    not_found,
    plain_text,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> APIRouter:
    """Build the router that owns assessment and final-result contracts."""
    router = APIRouter()
    _add_assessment_model_routes(
        router,
        finish=finish,
        not_found=not_found,
        read_security=read_security,
        write_security=write_security,
    )
    _add_result_read_routes(
        router,
        finish=finish,
        not_found=not_found,
        read_security=read_security,
    )
    _add_individual_result_routes(
        router,
        finish=finish,
        write_security=write_security,
    )
    _add_final_result_routes(
        router,
        finish=finish,
        write_security=write_security,
    )
    _add_result_export_routes(
        router,
        finish=finish,
        plain_text=plain_text,
        read_security=read_security,
    )
    _add_result_completion_route(
        router,
        finish=finish,
        not_found=not_found,
        read_security=read_security,
    )
    return router
