"""FastAPI router for master data and organizational resources."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, Request

from . import hateoas
from .api_contracts import (
    DomainCollectionResponse,
    DomainResourceResponse,
    ExamRoomCreateRequest,
    ExamRoomResponse,
    ExamRoomUpdateRequest,
    ExamVenueCollectionResponse,
    ExamVenueContactCreateRequest,
    ExamVenueContactResponse,
    ExamVenueContactUpdateRequest,
    ExamVenueCreateRequest,
    ExamVenueDuplicateCheckRequest,
    ExamVenueGeocodeRequest,
    ExamVenueGeocodeResponse,
    ExamVenuePromotionDecisionRequest,
    ExamVenuePromotionRequest,
    ExamVenueResponse,
    ExamVenueUpdateRequest,
    LegacyLocationCollectionResponse,
    LegacyLocationResponse,
    RevisionDeleteRequest,
)
from .exam_venue_api import ExamVenueApi
from .fastapi_dependencies import (
    EmptyWriteContext,
    ReadContext,
    VenueAuditWriteContext,
    VenueItemReadContext,
    VenueItemWriteContext,
    VenueReadContext,
    VenueWriteContext,
    WriteContext,
)
from .fastapi_http import finish as _finish
from .fastapi_http import not_found as _not_found
from .fastapi_http import validated_payload
from .models import CANDIDATE_COMMITTEE_ASSIGNMENT, COMMITTEE
from .repositories import PLAN_AGGREGATE_RESOURCES, REST_RESOURCES
from .transport import RequestContext

if TYPE_CHECKING:
    from .fastapi_app import FastAPIConfig

__all__ = [
    "MIGRATED_DOMAIN_RESOURCES",
    "create_master_data_router",
    "register_master_data_routes",
]

MIGRATED_DOMAIN_RESOURCES = (
    "committees",
    "persons",
    "members",
    "memberships",
    "exam-half-years",
    "exam-rounds",
    "round-candidates",
    "candidates",
    "planning-settings",
    "member-availabilities",
)


def _resource_collection_route(resolved: FastAPIConfig, resource_name: str, resource):
    def get_collection(request: Request, context: ReadContext):
        params = request.query_params
        if resource_name in {"members", "memberships"}:
            rows = context.repository.member_list(
                context.resource_filters(resource, params), context.authorization_scope
            )
        elif resource_name == "candidates":
            rows = context.repository.candidate_list(context.authorization_scope)
        else:
            rows = context.repository.list_visible(
                resource,
                context.authorization_scope,
                context.resource_filters(resource, params),
            )
        return _finish(
            context,
            context.respond(
                hateoas.collection(
                    resource_name,
                    resource,
                    rows,
                    request.url.query,
                    allow_create=(
                        resource not in PLAN_AGGREGATE_RESOURCES and resource != COMMITTEE
                    ),
                    allow_item_mutation=resource not in PLAN_AGGREGATE_RESOURCES,
                )
            ),
        )

    return get_collection


def _resource_item_route(resolved: FastAPIConfig, resource_name: str, resource):
    def get_item(context: ReadContext, id: str):
        row = (
            context.repository.member_get(int(id), context.authorization_scope)
            if resource_name in {"members", "memberships"}
            else context.repository.get_visible(resource, int(id), context.authorization_scope)
        )
        return (
            _not_found()
            if row is None
            else _finish(
                context,
                context.respond(
                    hateoas.resource_item(
                        resource_name,
                        resource,
                        row,
                        allow_item_mutation=resource not in PLAN_AGGREGATE_RESOURCES,
                    )
                ),
            )
        )

    return get_item


def _resource_create_route(resolved: FastAPIConfig, resource_name: str, resource):
    def create(context: WriteContext):
        payload = context.authorize_resource_action(
            resource_name, None, context.read_json(), "create"
        )
        status = HTTPStatus.CREATED
        if resource_name == "candidates":
            row = context.repository.create_candidate(payload)
        elif resource_name == "planning-settings":
            row = context.repository.save_planning_settings(payload)
            status = HTTPStatus.OK
        elif resource_name == "member-availabilities":
            row = context.repository.save_member_availability(payload)
            status = HTTPStatus.OK
        elif resource_name in {"members", "memberships"}:
            row = context.repository.create_membership(payload)
        else:
            row = context.repository.create(resource, payload)
        return _finish(
            context,
            context.respond(hateoas.resource_item(resource_name, resource, row), status),
        )

    return create


def _resource_update_route(resolved: FastAPIConfig, resource_name: str, resource):
    def update(context: WriteContext, id: str):
        ident = int(id)
        payload = context.authorize_resource_action(
            resource_name, ident, context.read_json(), "update"
        )
        if resource_name == "planning-settings":
            row = context.repository.update_planning_settings(ident, payload)
        elif resource_name == "member-availabilities":
            row = context.repository.update_member_availability(ident, payload)
        elif resource_name == "candidates":
            row = context.repository.update_candidate(ident, payload)
        elif resource_name == "exam-rounds":
            row = context.repository.update_exam_round(ident, payload)
        elif resource_name in {"members", "memberships"}:
            row = context.repository.update_membership(ident, payload)
        else:
            row = context.repository.update(resource, ident, payload)
        return (
            _not_found()
            if row is None
            else _finish(
                context, context.respond(hateoas.resource_item(resource_name, resource, row))
            )
        )

    return update


def _resource_delete_route(resolved: FastAPIConfig, resource_name: str, resource):
    def delete(context: EmptyWriteContext, id: str):
        ident = int(id)
        context.authorize_resource_action(resource_name, ident, {}, "delete")
        if resource_name == "candidates":
            deleted = context.repository.delete_candidate(ident)
        elif resource_name == "exam-rounds":
            deleted = context.exam_round_lifecycle_service.delete_empty_draft(
                context.authorization_scope, ident
            )
        else:
            deleted = context.repository.delete(resource, ident)
        return (
            _not_found()
            if not deleted
            else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )

    return delete


def _resource_routes(resolved: FastAPIConfig, resource_name: str):
    resource = REST_RESOURCES[resource_name]
    return (
        _resource_collection_route(resolved, resource_name, resource),
        _resource_item_route(resolved, resource_name, resource),
        _resource_create_route(resolved, resource_name, resource),
        _resource_update_route(resolved, resource_name, resource),
        _resource_delete_route(resolved, resource_name, resource),
    )


def _register_exam_venue_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    venue_api = ExamVenueApi(resolved.db_path, resolved.map_provider)

    @app.get(
        "/api/exam-venues",
        response_model=ExamVenueCollectionResponse,
        openapi_extra=read_security,
    )
    def exam_venue_collection(context: VenueReadContext):
        return _finish(
            context,
            context.respond(
                hateoas.exam_venue_collection(
                    venue_api.list_venues(context.authorization_scope, context.auth_context),
                    allow_create=bool(
                        context.auth_context
                        and context.auth_context.is_operator
                        or context.authorization_scope.management_committee_ids
                    ),
                )
            ),
        )

    @app.post(
        "/api/exam-venues/duplicate-check",
        openapi_extra=venue_write_openapi("ExamVenueDuplicateCheckRequest"),
    )
    def exam_venue_duplicate_check(context: VenueWriteContext):
        payload = validated_payload(context, ExamVenueDuplicateCheckRequest)
        excluded_id = payload.pop("excluded_id", None)
        matches = venue_api.find_duplicates(
            payload,
            context.authorization_scope,
            context.auth_context,
            excluded_id=excluded_id,
        )
        return _finish(context, context.respond({"items": matches}))

    @app.get("/api/exam-venue-promotion-requests", openapi_extra=read_security)
    def exam_venue_promotion_requests(context: VenueReadContext):
        return _finish(
            context,
            context.respond({"items": venue_api.list_pending_promotions(context.auth_context)}),
        )

    @app.get("/api/exam-venues/{id}/change-impact", openapi_extra=read_security)
    def exam_venue_change_impact(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        impact = venue_api.future_impact(id, context.authorization_scope, context.auth_context)
        return _not_found() if impact is None else _finish(context, context.respond(impact))

    @app.post(
        "/api/exam-venues/{id}/change-impact",
        openapi_extra=venue_write_openapi("ExamVenueUpdateRequest"),
    )
    def preview_exam_venue_change(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        impact = venue_api.future_impact(
            id,
            context.authorization_scope,
            context.auth_context,
            payload=validated_payload(context, ExamVenueUpdateRequest),
        )
        return _not_found() if impact is None else _finish(context, context.respond(impact))

    @app.get("/api/exam-rooms/{id}/change-impact", openapi_extra=read_security)
    def exam_room_change_impact(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        room = venue_api.get_room(id, context.authorization_scope, context.auth_context)
        impact = (
            None
            if room is None
            else venue_api.future_impact(
                room["venue_id"],
                context.authorization_scope,
                context.auth_context,
                room_id=id,
            )
        )
        return _not_found() if impact is None else _finish(context, context.respond(impact))

    @app.post(
        "/api/exam-rooms/{id}/change-impact",
        openapi_extra=venue_write_openapi("ExamRoomUpdateRequest"),
    )
    def preview_exam_room_change(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        room = venue_api.get_room(id, context.authorization_scope, context.auth_context)
        impact = (
            None
            if room is None
            else venue_api.future_impact(
                room["venue_id"],
                context.authorization_scope,
                context.auth_context,
                room_id=id,
                payload=validated_payload(context, ExamRoomUpdateRequest),
            )
        )
        return _not_found() if impact is None else _finish(context, context.respond(impact))

    @app.post(
        "/api/exam-venue-changes/{audit_id}/consequences/retry",
        openapi_extra=write_security,
    )
    def retry_exam_venue_change_consequences(context: VenueAuditWriteContext):
        audit_id = int(context.request.path_params["audit_id"])
        result = venue_api.retry_consequences(
            audit_id, context.authorization_scope, context.auth_context
        )
        return _not_found() if result is None else _finish(context, context.respond(result))

    @app.post(
        "/api/exam-venues/{id}/promotion-requests",
        status_code=201,
        openapi_extra=venue_write_openapi("ExamVenuePromotionRequest"),
    )
    def request_exam_venue_promotion(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        result = venue_api.request_promotion(
            id,
            validated_payload(context, ExamVenuePromotionRequest),
            context.authorization_scope,
        )
        return (
            _not_found()
            if result is None
            else _finish(context, context.respond(result, HTTPStatus.CREATED))
        )

    @app.post(
        "/api/exam-venue-promotion-requests/{id}/decision",
        openapi_extra=venue_write_openapi("ExamVenuePromotionDecisionRequest"),
    )
    def decide_exam_venue_promotion(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        result = venue_api.decide_promotion(
            id,
            validated_payload(context, ExamVenuePromotionDecisionRequest),
            context.auth_context,
        )
        return _finish(context, context.respond(hateoas.exam_venue(result)))

    @app.get(
        "/api/exam-venues/{id}",
        response_model=ExamVenueResponse,
        openapi_extra=read_security,
    )
    def exam_venue_item(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        venue = venue_api.get_venue(id, context.authorization_scope, context.auth_context)
        return (
            _not_found()
            if venue is None
            else _finish(context, context.respond(hateoas.exam_venue(venue)))
        )

    @app.post(
        "/api/exam-venues",
        response_model=ExamVenueResponse,
        status_code=201,
        openapi_extra=venue_write_openapi("ExamVenueCreateRequest"),
    )
    def create_exam_venue(context: VenueWriteContext):
        venue = venue_api.create_venue(
            validated_payload(context, ExamVenueCreateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return _finish(context, context.respond(hateoas.exam_venue(venue), HTTPStatus.CREATED))

    @app.patch(
        "/api/exam-venues/{id}",
        response_model=ExamVenueResponse,
        openapi_extra=venue_write_openapi("ExamVenueUpdateRequest"),
    )
    def update_exam_venue(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        venue = venue_api.update_venue(
            id,
            validated_payload(context, ExamVenueUpdateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if venue is None
            else _finish(context, context.respond(hateoas.exam_venue(venue)))
        )

    @app.post(
        "/api/exam-venues/{id}/geocode",
        response_model=ExamVenueGeocodeResponse,
        openapi_extra=venue_write_openapi("ExamVenueGeocodeRequest"),
    )
    def geocode_exam_venue(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        candidate = venue_api.geocode_venue(
            id,
            validated_payload(context, ExamVenueGeocodeRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return _not_found() if candidate is None else _finish(context, context.respond(candidate))

    @app.delete(
        "/api/exam-venues/{id}",
        status_code=204,
        openapi_extra=venue_write_openapi("RevisionDeleteRequest"),
    )
    def delete_exam_venue(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        deleted = venue_api.delete_venue(
            id,
            validated_payload(context, RevisionDeleteRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if deleted is None
            else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )


def _register_exam_room_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    venue_api = ExamVenueApi(resolved.db_path)

    @app.post(
        "/api/exam-venues/{id}/rooms",
        response_model=ExamRoomResponse,
        status_code=201,
        openapi_extra=venue_write_openapi("ExamRoomCreateRequest"),
    )
    def create_exam_room(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        room = venue_api.create_room(
            id,
            validated_payload(context, ExamRoomCreateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if room is None
            else _finish(context, context.respond(hateoas.exam_room(room), HTTPStatus.CREATED))
        )

    @app.get(
        "/api/exam-rooms/{id}",
        response_model=ExamRoomResponse,
        openapi_extra=read_security,
    )
    def exam_room_item(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        room = venue_api.get_room(id, context.authorization_scope, context.auth_context)
        return (
            _not_found()
            if room is None
            else _finish(context, context.respond(hateoas.exam_room(room)))
        )

    @app.patch(
        "/api/exam-rooms/{id}",
        response_model=ExamRoomResponse,
        openapi_extra=venue_write_openapi("ExamRoomUpdateRequest"),
    )
    def update_exam_room(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        room = venue_api.update_room(
            id,
            validated_payload(context, ExamRoomUpdateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if room is None
            else _finish(context, context.respond(hateoas.exam_room(room)))
        )

    @app.delete(
        "/api/exam-rooms/{id}",
        status_code=204,
        openapi_extra=venue_write_openapi("RevisionDeleteRequest"),
    )
    def delete_exam_room(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        deleted = venue_api.delete_room(
            id,
            validated_payload(context, RevisionDeleteRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if deleted is None
            else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )


def _register_exam_venue_contact_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    venue_api = ExamVenueApi(resolved.db_path)

    @app.post(
        "/api/exam-venues/{id}/contacts",
        response_model=ExamVenueContactResponse,
        status_code=201,
        openapi_extra=venue_write_openapi("ExamVenueContactCreateRequest"),
    )
    def create_exam_venue_contact(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        contact = venue_api.create_contact(
            id,
            validated_payload(context, ExamVenueContactCreateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if contact is None
            else _finish(
                context, context.respond(hateoas.exam_venue_contact(contact), HTTPStatus.CREATED)
            )
        )

    @app.get(
        "/api/exam-venue-contacts/{id}",
        response_model=ExamVenueContactResponse,
        openapi_extra=read_security,
    )
    def exam_venue_contact_item(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        contact = venue_api.get_contact(id, context.authorization_scope, context.auth_context)
        return (
            _not_found()
            if contact is None
            else _finish(context, context.respond(hateoas.exam_venue_contact(contact)))
        )

    @app.patch(
        "/api/exam-venue-contacts/{id}",
        response_model=ExamVenueContactResponse,
        openapi_extra=venue_write_openapi("ExamVenueContactUpdateRequest"),
    )
    def update_exam_venue_contact(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        contact = venue_api.update_contact(
            id,
            validated_payload(context, ExamVenueContactUpdateRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if contact is None
            else _finish(context, context.respond(hateoas.exam_venue_contact(contact)))
        )

    @app.delete(
        "/api/exam-venue-contacts/{id}",
        status_code=204,
        openapi_extra=venue_write_openapi("RevisionDeleteRequest"),
    )
    def delete_exam_venue_contact(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        deleted = venue_api.delete_contact(
            id,
            validated_payload(context, RevisionDeleteRequest),
            context.authorization_scope,
            context.auth_context,
        )
        return (
            _not_found()
            if deleted is None
            else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )


def _register_legacy_location_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    venue_api = ExamVenueApi(resolved.db_path)

    @app.get(
        "/api/locations",
        response_model=LegacyLocationCollectionResponse,
        deprecated=True,
        openapi_extra=read_security,
    )
    def legacy_location_collection(context: VenueReadContext):
        return _finish(
            context,
            context.respond(
                hateoas.legacy_location_collection(
                    venue_api.list_legacy_locations(
                        context.authorization_scope, context.auth_context
                    )
                )
            ),
        )

    @app.get(
        "/api/locations/{id}",
        response_model=LegacyLocationResponse,
        deprecated=True,
        openapi_extra=read_security,
    )
    def legacy_location_item(context: VenueItemReadContext):
        id = int(context.request.path_params["id"])
        location = venue_api.get_legacy_location(
            id, context.authorization_scope, context.auth_context
        )
        return (
            _not_found()
            if location is None
            else _finish(context, context.respond(hateoas.legacy_location(location)))
        )

    def legacy_location_write(context: RequestContext, path_parts: list[str]):
        return _finish(
            context,
            context.respond(
                {
                    "error": (
                        "Location write endpoints are no longer available. "
                        "Use the exam venue, room, and contact endpoints."
                    )
                },
                HTTPStatus.GONE,
            ),
        )

    @app.post(
        "/api/locations",
        response_model=dict[str, object],
        status_code=410,
        deprecated=True,
        openapi_extra=write_security,
    )
    def create_legacy_location(context: VenueWriteContext):
        return legacy_location_write(context, ["locations"])

    @app.patch(
        "/api/locations/{id}",
        response_model=dict[str, object],
        status_code=410,
        deprecated=True,
        openapi_extra=write_security,
    )
    def update_legacy_location(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        return legacy_location_write(context, ["locations", str(id)])

    @app.delete(
        "/api/locations/{id}",
        response_model=dict[str, object],
        status_code=410,
        deprecated=True,
        openapi_extra=write_security,
    )
    def delete_legacy_location(context: VenueItemWriteContext):
        id = int(context.request.path_params["id"])
        return legacy_location_write(context, ["locations", str(id)])


def _register_venue_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    _register_exam_venue_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_exam_room_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_exam_venue_contact_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_legacy_location_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )


def _register_resource_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    for name in (
        resource_name
        for resource_name in MIGRATED_DOMAIN_RESOURCES
        if resource_name not in {"planning-settings", "member-availabilities"}
    ):
        get_collection, get_item, create, update, delete = _resource_routes(resolved, name)
        app.add_api_route(
            f"/api/{name}",
            get_collection,
            methods=["GET"],
            name=f"get_{name}",
            response_model=DomainCollectionResponse,
            openapi_extra=read_security,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            get_item,
            methods=["GET"],
            name=f"get_{name}_item",
            response_model=DomainResourceResponse,
            openapi_extra=read_security,
        )
        if name != "committees":
            app.add_api_route(
                f"/api/{name}",
                create,
                methods=["POST"],
                name=f"create_{name}",
                status_code=201,
                response_model=DomainResourceResponse,
                openapi_extra=venue_write_openapi("DomainResourceWrite"),
            )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            update,
            methods=["PATCH"],
            name=f"update_{name}",
            response_model=DomainResourceResponse,
            openapi_extra=venue_write_openapi("DomainResourceWrite"),
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            delete,
            methods=["DELETE"],
            status_code=204,
            name=f"delete_{name}",
            openapi_extra=write_security,
        )


def _register_assignment_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.get(
        "/api/candidate-committee-assignments",
        response_model=DomainCollectionResponse,
        openapi_extra=read_security,
    )
    def assignment_collection(request: Request, context: ReadContext):
        value = request.query_params.get("candidate_id")
        rows = context.repository.candidate_committee_assignments(
            int(value) if value is not None else None, context.authorization_scope
        )
        return _finish(
            context,
            context.respond(
                hateoas.collection(
                    "candidate-committee-assignments",
                    CANDIDATE_COMMITTEE_ASSIGNMENT,
                    rows,
                    request.url.query,
                    allow_create=False,
                    allow_item_mutation=False,
                )
            ),
        )

    @app.get(
        "/api/candidate-committee-assignments/{id}",
        response_model=DomainResourceResponse,
        openapi_extra=read_security,
    )
    def assignment_item(context: ReadContext, id: str):
        row = context.repository.get_visible(
            CANDIDATE_COMMITTEE_ASSIGNMENT, int(id), context.authorization_scope
        )
        return (
            _not_found()
            if row is None
            else _finish(
                context,
                context.respond(
                    hateoas.resource_item(
                        "candidate-committee-assignments",
                        CANDIDATE_COMMITTEE_ASSIGNMENT,
                        row,
                        allow_item_mutation=False,
                    )
                ),
            )
        )


def create_master_data_router(
    resolved: FastAPIConfig,
    read_security: dict[str, object],
    write_security: dict[str, object],
    venue_write_openapi,
) -> APIRouter:
    """Build the router that owns master data and organizational endpoints."""
    router = APIRouter()
    for registrar in (
        _register_venue_routes,
        _register_resource_routes,
        _register_assignment_routes,
    ):
        registrar(router, resolved, None, read_security, write_security, venue_write_openapi)
    return router


def register_master_data_routes(
    app: FastAPI,
    resolved: FastAPIConfig,
    application,
    read_security: dict[str, object],
    write_security: dict[str, object],
    venue_write_openapi,
) -> None:
    """Attach the master-data router to the assembled application."""
    app.include_router(
        create_master_data_router(
            resolved,
            read_security,
            write_security,
            venue_write_openapi,
        )
    )
