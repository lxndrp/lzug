"""FastAPI router for planning proposals, confirmed plans, and planning resources."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.application import hateoas
from backend.application.repositories import REST_RESOURCES
from backend.application.transport import (
    RequestContext,
    confirmed_plan_change_from_payload,
    planning_proposal_from_payload,
)
from backend.persistence.models import EXAM_ROUND

from .api_contracts import (
    ConfirmedPlanChangeRequest,
    PlanningProposalResponse,
    PlanningProposalResultResponse,
    PlanningProposalWriteRequest,
    PlanningRoundRequest,
)
from .application import ApplicationResult, ForbiddenRequestError
from .fastapi_dependencies import (
    EmptyWriteContext,
    ManageBodyRoundContext,
    ManageRoundContext,
    ManageRoundEmptyWriteContext,
    ManageRoundWriteContext,
    ReadContext,
    WriteContext,
)
from .fastapi_http import request_body, validated_payload
from .observability import emit_event

MIGRATED_PLANNING_RESOURCES = (
    "candidate-exam-days",
    "exam-days",
    "exam-slots",
    "exam-day-assignments",
)
PLANNING_DOMAIN_RESOURCES = ("planning-settings", "member-availabilities")

type Finish = Callable[[RequestContext, ApplicationResult | None], Response]
type NotFound = Callable[[], Response]


def _body_openapi(security: dict[str, object], model: type[BaseModel]) -> dict[str, object]:
    return {**security, **request_body(model)}


def _register_schedule_routes(router: APIRouter, finish: Finish, not_found: NotFound) -> None:
    @router.get("/api/scheduling-overview")
    def scheduling(context: ReadContext):
        return finish(
            context,
            context.respond(
                hateoas.scheduling_overview(
                    context.repository.scheduling_overview(context.authorization_scope)
                )
            ),
        )

    @router.get("/api/confirmed-plans")
    def confirmed_plans(context: ReadContext):
        return finish(
            context,
            context.respond(
                hateoas.confirmed_plans(
                    context.repository.confirmed_plans(context.authorization_scope)
                )
            ),
        )

    @router.get("/api/confirmed-plan-days/{id}")
    def confirmed_day(context: ReadContext, id: str):
        day = context.repository.confirmed_plan_day(int(id), context.authorization_scope)
        if day is not None:
            day["day"]["closure"] = context.exam_day_closure_service.get(
                context.authorization_scope, int(id)
            )
        return (
            not_found()
            if day is None
            else finish(context, context.respond(hateoas.confirmed_plan_day(day)))
        )


def _register_proposal_routes(
    router: APIRouter,
    finish: Finish,
    write_security: dict[str, object],
) -> None:
    @router.post(
        "/api/planning-proposals",
        response_model=PlanningProposalResultResponse,
        status_code=201,
        openapi_extra=_body_openapi(write_security, PlanningRoundRequest),
    )
    def generate_proposal(context: ManageBodyRoundContext):
        round_id = validated_payload(context, PlanningRoundRequest, exclude_unset=False)["round_id"]
        return finish(
            context,
            context.respond(
                hateoas.planning_proposal(context.planning_service.generate_proposal(round_id)),
                HTTPStatus.CREATED,
            ),
        )

    @router.get(
        "/api/exam-rounds/{id}/planning-proposal",
        response_model=PlanningProposalResponse,
    )
    def get_proposal(context: ManageRoundContext, id: str):
        proposal = context.planning_service.get_proposal(int(id))
        return finish(
            context,
            context.respond(
                hateoas.editable_planning_proposal(
                    context.planning_service.proposal_payload(proposal)
                )
            ),
        )

    @router.put(
        "/api/exam-rounds/{id}/planning-proposal",
        response_model=PlanningProposalResponse,
        openapi_extra=_body_openapi(write_security, PlanningProposalWriteRequest),
    )
    def save_proposal(context: ManageRoundWriteContext, id: str):
        round_id = int(id)
        payload = validated_payload(context, PlanningProposalWriteRequest)
        saved = context.planning_service.save_proposal(
            planning_proposal_from_payload(round_id, payload)
        )
        return finish(
            context,
            context.respond(
                hateoas.editable_planning_proposal(context.planning_service.proposal_payload(saved))
            ),
        )

    @router.post("/api/exam-rounds/{id}/confirm-plan")
    def confirm_plan(context: ManageRoundEmptyWriteContext, id: str):
        round_id = int(id)
        confirmed = context.planning_service.confirm_plan(round_id)
        try:
            context.calendar_service.sync_round(round_id)
        except Exception:
            emit_event("backend_error", severity="error", category="calendar_processing")
            confirmed["calendar_warning"] = (
                "Der Plan wurde bestätigt, aber die persönlichen Kalender konnten nicht "
                "vollständig vorbereitet werden."
            )
        warning = context.create_notifications_best_effort("plan_confirmed", round_id)
        if warning:
            confirmed["notification_warning"] = warning
        return finish(context, context.respond(hateoas.confirmed_plan(confirmed)))


def _register_confirmed_plan_routes(
    router: APIRouter,
    finish: Finish,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> None:
    @router.get(
        "/api/exam-rounds/{id}/confirmed-plan",
        response_model=PlanningProposalResponse,
        openapi_extra=read_security,
    )
    def get_confirmed_plan(context: ManageRoundContext, id: str):
        round_id = int(id)
        plan = context.planning_service.get_confirmed_plan(round_id)
        return finish(
            context,
            context.respond(
                hateoas.editable_confirmed_plan(
                    context.planning_service.confirmed_plan_payload(plan)
                )
            ),
        )

    @router.put(
        "/api/exam-rounds/{id}/confirmed-plan",
        response_model=PlanningProposalResponse,
        openapi_extra=_body_openapi(write_security, ConfirmedPlanChangeRequest),
    )
    def save_confirmed_plan(context: ManageRoundWriteContext, id: str):
        round_id = int(id)
        committee_id = context.repository.committee_id_for_resource(EXAM_ROUND, round_id)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        payload = validated_payload(context, ConfirmedPlanChangeRequest)
        saved, revision = context.planning_service.save_confirmed_plan(
            confirmed_plan_change_from_payload(round_id, payload),
            actor_member_id=actor_member_id,
        )
        try:
            consequence_status = context.plan_consequence_service.process_revision(revision["id"])
        except Exception:
            emit_event("backend_error", severity="error", category="plan_consequence_processing")
            consequence_status = {
                "revision_id": revision["id"],
                "derivation_status": "missing",
                "processed": 0,
                "problems": 1,
                "pending": 0,
                "superseded": 0,
            }
        response = hateoas.editable_confirmed_plan(
            context.planning_service.confirmed_plan_payload(saved),
            latest_revision=revision,
        )
        response["consequence_status"] = consequence_status
        if consequence_status["problems"] or consequence_status["derivation_status"] != "succeeded":
            response["consequence_warning"] = (
                "Die Planänderung wurde bestätigt, aber mindestens eine Benachrichtigungs- "
                "oder Kalenderfolge konnte nicht vollständig verarbeitet werden."
            )
        return finish(context, context.respond(response))

    @router.get(
        "/api/exam-rounds/{id}/confirmed-plan/revisions",
        openapi_extra=read_security,
    )
    def confirmed_plan_revisions(context: ManageRoundContext, id: str):
        round_id = int(id)
        return finish(
            context,
            context.respond(
                hateoas.confirmed_plan_revisions(
                    round_id,
                    context.planning_service.confirmed_plan_revisions(round_id),
                )
            ),
        )


def _register_plan_consequence_routes(
    router: APIRouter,
    finish: Finish,
    not_found: NotFound,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> None:
    @router.get(
        "/api/exam-rounds/{id}/confirmed-plan/consequences",
        openapi_extra=read_security,
    )
    def confirmed_plan_consequences(context: ManageRoundContext, id: str):
        round_id = int(id)
        return finish(
            context,
            context.respond(
                hateoas.plan_consequences(
                    round_id,
                    context.plan_consequence_service.list_for_round(round_id),
                )
            ),
        )

    @router.post(
        "/api/exam-rounds/{id}/confirmed-plan/revisions/{revision_id}/consequences/retry",
        openapi_extra=write_security,
    )
    def retry_confirmed_plan_consequences(context: EmptyWriteContext, id: str, revision_id: str):
        round_id = int(id)
        parsed_revision_id = int(revision_id)
        context.require_round_access(round_id, manage=True)
        known_revision_ids = {
            item["id"] for item in context.planning_service.confirmed_plan_revisions(round_id)
        }
        if parsed_revision_id not in known_revision_ids:
            return not_found()
        return finish(
            context,
            context.respond(context.plan_consequence_service.retry_revision(parsed_revision_id)),
        )


def _register_availability_routes(
    router: APIRouter,
    finish: Finish,
    write_security: dict[str, object],
) -> None:
    @router.post(
        "/api/candidate-exam-days/generate",
        openapi_extra=_body_openapi(write_security, PlanningRoundRequest),
    )
    def generate_days(context: ManageBodyRoundContext):
        round_id = validated_payload(context, PlanningRoundRequest, exclude_unset=False)["round_id"]
        return finish(
            context,
            context.respond(
                hateoas.candidate_day_generation(context.candidate_day_service.generate(round_id)),
                HTTPStatus.OK,
            ),
        )

    @router.post("/api/exam-rounds/{id}/request-availabilities")
    def request_availabilities(context: ManageRoundEmptyWriteContext, id: str):
        round_id = int(id)
        exam_round = context.planning_service.request_availabilities(round_id)
        warning = context.create_notifications_best_effort("availability_requested", round_id)
        if warning:
            exam_round["notification_warning"] = warning
        return finish(
            context,
            context.respond(
                hateoas.resource_item("exam-rounds", REST_RESOURCES["exam-rounds"], exam_round)
            ),
        )


def _planning_collection(
    resource_name: str,
    finish: Finish,
    *,
    allow_create: bool,
    allow_item_mutation: bool,
):
    resource = REST_RESOURCES[resource_name]

    def get_collection(request: Request, context: ReadContext):
        rows = context.repository.list_visible(
            resource,
            context.authorization_scope,
            context.resource_filters(resource, request.query_params),
        )
        return finish(
            context,
            context.respond(
                hateoas.collection(
                    resource_name,
                    resource,
                    rows,
                    request.url.query,
                    allow_create=allow_create,
                    allow_item_mutation=allow_item_mutation,
                )
            ),
        )

    return get_collection


def _planning_item(resource_name: str, finish: Finish, not_found: NotFound, *, mutable: bool):
    resource = REST_RESOURCES[resource_name]

    def get_item(context: ReadContext, id: str):
        row = context.repository.get_visible(resource, int(id), context.authorization_scope)
        return (
            not_found()
            if row is None
            else finish(
                context,
                context.respond(
                    hateoas.resource_item(
                        resource_name,
                        resource,
                        row,
                        allow_item_mutation=mutable,
                    )
                ),
            )
        )

    return get_item


def _planning_create(resource_name: str, finish: Finish):
    resource = REST_RESOURCES[resource_name]

    def create(context: WriteContext):
        payload = context.authorize_resource_action(
            resource_name, None, context.read_json(), "create"
        )
        status = HTTPStatus.CREATED
        if resource_name == "planning-settings":
            row = context.repository.save_planning_settings(payload)
            status = HTTPStatus.OK
        elif resource_name == "member-availabilities":
            row = context.repository.save_member_availability(payload)
            status = HTTPStatus.OK
        else:
            row = context.repository.create(resource, payload)
        return finish(
            context,
            context.respond(hateoas.resource_item(resource_name, resource, row), status),
        )

    return create


def _planning_update(
    resource_name: str,
    finish: Finish,
    not_found: NotFound,
):
    resource = REST_RESOURCES[resource_name]

    def update(context: WriteContext, id: str):
        ident = int(id)
        payload = context.authorize_resource_action(
            resource_name, ident, context.read_json(), "update"
        )
        if resource_name == "planning-settings":
            row = context.repository.update_planning_settings(ident, payload)
        elif resource_name == "member-availabilities":
            row = context.repository.update_member_availability(ident, payload)
        else:
            row = context.repository.update(resource, ident, payload)
        return (
            not_found()
            if row is None
            else finish(
                context,
                context.respond(hateoas.resource_item(resource_name, resource, row)),
            )
        )

    return update


def _planning_delete(
    resource_name: str,
    finish: Finish,
    not_found: NotFound,
):
    resource = REST_RESOURCES[resource_name]

    def delete(context: EmptyWriteContext, id: str):
        ident = int(id)
        context.authorize_resource_action(resource_name, ident, {}, "delete")
        deleted = context.repository.delete(resource, ident)
        return (
            not_found()
            if not deleted
            else finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )

    return delete


def _register_resource_routes(
    router: APIRouter,
    finish: Finish,
    not_found: NotFound,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> None:
    for name in PLANNING_DOMAIN_RESOURCES:
        router.add_api_route(
            f"/api/{name}",
            _planning_collection(name, finish, allow_create=True, allow_item_mutation=True),
            methods=["GET"],
            name=f"get_{name}",
            openapi_extra=read_security,
        )
        router.add_api_route(
            f"/api/{name}/{{id}}",
            _planning_item(name, finish, not_found, mutable=True),
            methods=["GET"],
            name=f"get_{name}_item",
            openapi_extra=read_security,
        )
        router.add_api_route(
            f"/api/{name}",
            _planning_create(name, finish),
            methods=["POST"],
            name=f"create_{name}",
            openapi_extra=write_security,
        )
        router.add_api_route(
            f"/api/{name}/{{id}}",
            _planning_update(name, finish, not_found),
            methods=["PATCH"],
            name=f"update_{name}",
            openapi_extra=write_security,
        )
        router.add_api_route(
            f"/api/{name}/{{id}}",
            _planning_delete(name, finish, not_found),
            methods=["DELETE"],
            status_code=204,
            name=f"delete_{name}",
            openapi_extra=write_security,
        )

    for name in MIGRATED_PLANNING_RESOURCES:
        router.add_api_route(
            f"/api/{name}",
            _planning_collection(name, finish, allow_create=False, allow_item_mutation=False),
            methods=["GET"],
            name=f"get_planning_{name}",
            openapi_extra=read_security,
        )
        router.add_api_route(
            f"/api/{name}/{{id}}",
            _planning_item(name, finish, not_found, mutable=False),
            methods=["GET"],
            name=f"get_planning_{name}_item",
            openapi_extra=read_security,
        )

    candidate_name = "candidate-exam-days"
    router.add_api_route(
        f"/api/{candidate_name}",
        _planning_create(candidate_name, finish),
        methods=["POST"],
        name="create_candidate_exam_days",
        status_code=201,
        openapi_extra=write_security,
    )
    router.add_api_route(
        f"/api/{candidate_name}/{{id}}",
        _planning_update(candidate_name, finish, not_found),
        methods=["PATCH"],
        name="update_candidate_exam_days",
        openapi_extra=write_security,
    )
    router.add_api_route(
        f"/api/{candidate_name}/{{id}}",
        _planning_delete(candidate_name, finish, not_found),
        methods=["DELETE"],
        status_code=204,
        name="delete_candidate_exam_days",
        openapi_extra=write_security,
    )

    def aggregate_write(context: WriteContext, id: str | None = None):
        raise ValueError(
            "Exam days, slots, and assignments must be changed through the planning aggregate"
        )

    for name in ("exam-days", "exam-slots", "exam-day-assignments"):
        router.add_api_route(
            f"/api/{name}",
            aggregate_write,
            methods=["POST"],
            name=f"reject_create_{name}",
            include_in_schema=False,
        )
        router.add_api_route(
            f"/api/{name}/{{id}}",
            aggregate_write,
            methods=["PATCH", "DELETE"],
            name=f"reject_write_{name}",
            include_in_schema=False,
        )


def register_planning_router(
    app: FastAPI,
    read_security: dict[str, object],
    write_security: dict[str, object],
    *,
    finish: Finish,
    not_found: NotFound,
) -> None:
    """Build and include the complete planning-owned FastAPI router."""
    router = APIRouter()
    _register_schedule_routes(router, finish, not_found)
    _register_proposal_routes(router, finish, write_security)
    _register_confirmed_plan_routes(router, finish, read_security, write_security)
    _register_plan_consequence_routes(router, finish, not_found, read_security, write_security)
    _register_availability_routes(router, finish, write_security)
    _register_resource_routes(router, finish, not_found, read_security, write_security)
    app.include_router(router)
