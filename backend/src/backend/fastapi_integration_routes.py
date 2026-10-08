"""FastAPI routers for calendars, notifications, and absence integrations."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Body, Query

from backend.calendar.ports import CalendarFeedStatus, CalendarScope

from .api_contracts import (
    CalendarEventCollectionResponse,
    CalendarFeedActivationRequest,
    CalendarFeedActivationResponse,
    CalendarFeedRevocationResponse,
    CalendarStatusResponse,
    DomainResourceWrite,
    NotificationChannelsResponse,
    NotificationCollectionResponse,
    PushConfirmationResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
)
from .fastapi_dependencies import (
    BodyMutationContext,
    BoundedBodyRoute,
    Context,
    MutationContext,
    ReadContext,
)
from .fastapi_http import calendar_text, finish, not_found, payload_data
from .settings import RuntimeSettings

_OPTIONAL_OBJECT_BODY = Body(default_factory=DomainResourceWrite)


def _calendar_scope(context: ReadContext) -> CalendarScope:
    scope = context.authorization_scope
    return CalendarScope(person_id=scope.person_id, member_ids=frozenset(scope.member_ids))


def _calendar_status_payload(status: CalendarFeedStatus) -> dict[str, object]:
    return {
        "active": status.active,
        "activated_at": status.activated_at,
        "revoked_at": status.revoked_at,
        "time_zone": status.time_zone,
    }


def _calendar_feed_url(context: ReadContext, token: str) -> str:
    settings = context.runtime_settings or RuntimeSettings.from_environment()
    path = f"/api/calendar/feed/{token}.ics"
    external_url = settings.integrations.external_url or ""
    return f"{external_url.rstrip('/')}{path}"


def create_round_summary_router() -> APIRouter:
    """Build the round summary used by the calendar integration."""
    router = APIRouter(route_class=BoundedBodyRoute)

    @router.get(
        "/api/round-summary",
        response_model=dict[str, object],
    )
    def round_summary(context: ReadContext, round_id: int | None = Query(default=None)):
        parsed_round_id = round_id or 1
        return finish(
            context,
            context.read_application.round_summary(context.authorization_scope, parsed_round_id),
        )

    return router


def create_public_calendar_router() -> APIRouter:
    """Build token and event based public iCalendar routes."""
    router = APIRouter(route_class=BoundedBodyRoute)

    @router.get("/api/calendar/feed/{token}.ics", include_in_schema=False)
    def personal_feed(context: Context, token: str):
        if not token or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in token
        ):
            return not_found()
        calendar = context.calendar_service.feed_ics(token)
        return not_found() if calendar is None else calendar_text(context, calendar)

    @router.get("/api/calendar/events/{id}.ics", include_in_schema=False)
    def event_feed(context: ReadContext, id: str):
        """Keep the private token-like URL indistinguishable from a missing feed."""
        if not id.isdigit():
            return not_found()
        calendar = context.calendar_service.event_ics(int(id), _calendar_scope(context))
        return not_found() if calendar is None else calendar_text(context, calendar)

    return router


def create_calendar_management_router() -> APIRouter:
    """Build personal calendar status, lifecycle, and event routes."""
    router = APIRouter(route_class=BoundedBodyRoute)

    @router.get("/api/calendar", response_model=CalendarStatusResponse)
    @router.get("/api/calendar/feed", response_model=CalendarStatusResponse)
    def calendar_status(context: ReadContext):
        result = {
            **_calendar_status_payload(context.calendar_service.status(_calendar_scope(context))),
            "_links": {
                "self": {"href": "/api/calendar"},
                "feed": {"href": "/api/calendar/feed", "method": "POST"},
            },
        }
        return finish(context, context.respond(result))

    @router.get("/api/calendar/events", response_model=CalendarEventCollectionResponse)
    def calendar_events(context: ReadContext):
        return finish(
            context,
            context.respond(
                {
                    "items": [
                        {
                            "id": event.id,
                            "external_event_id": event.external_event_id,
                            "date": event.date,
                            "starts_at": event.starts_at,
                            "ends_at": event.ends_at,
                            "time_zone": event.time_zone,
                            "location": event.location,
                            "role": event.role,
                            "round_name": event.round_name,
                            "status": event.status,
                            "version": event.version,
                            "download_url": f"/api/calendar/events/{event.id}.ics",
                        }
                        for event in context.calendar_service.list_events(_calendar_scope(context))
                    ],
                    "_links": {"self": {"href": "/api/calendar/events"}},
                }
            ),
        )

    @router.post(
        "/api/calendar/feed",
        status_code=201,
        response_model=CalendarFeedActivationResponse,
    )
    def activate_feed(context: BodyMutationContext, payload: CalendarFeedActivationRequest):
        data = payload_data(context, payload, exclude_unset=False)
        activation = context.calendar_service.activate(
            _calendar_scope(context),
            rotate=data["rotate"],
        )
        result = {
            **_calendar_status_payload(activation.status),
            "feed_url": _calendar_feed_url(context, activation.token),
        }
        result.update(
            {
                "_links": {
                    "self": {"href": "/api/calendar"},
                    "feed": {"href": "/api/calendar/feed"},
                    "events": {"href": "/api/calendar/events"},
                },
                "notice": (
                    "Der Feed-Zugang ist persönlich. Bereits extern gespeicherte Termine können "
                    "nach Widerruf oder Neuerzeugung nicht zuverlässig entfernt werden."
                ),
            }
        )
        return finish(context, context.respond(result, HTTPStatus.CREATED))

    @router.delete(
        "/api/calendar/feed",
        response_model=CalendarFeedRevocationResponse,
    )
    def revoke_feed(context: MutationContext):
        context.calendar_service.revoke(_calendar_scope(context))
        result = {
            **_calendar_status_payload(context.calendar_service.status(_calendar_scope(context))),
            "_links": {
                "self": {"href": "/api/calendar"},
                "feed": {"href": "/api/calendar/feed"},
                "events": {"href": "/api/calendar/events"},
            },
            "notice": (
                "Der Feed wurde widerrufen. Bereits extern gespeicherte Termine können nicht "
                "zuverlässig entfernt werden."
            ),
        }
        return finish(context, context.respond(result))

    return router


def create_calendar_router() -> APIRouter:
    """Compose the round summary and personal calendar integration routes."""
    router = APIRouter(route_class=BoundedBodyRoute)
    for owned_router in (
        create_round_summary_router(),
        create_public_calendar_router(),
        create_calendar_management_router(),
    ):
        router.include_router(owned_router)
    return router


def create_notification_router() -> APIRouter:
    """Build notification reads and push-subscription lifecycle routes."""
    router = APIRouter(route_class=BoundedBodyRoute)

    @router.get("/api/notifications", response_model=NotificationCollectionResponse)
    def notifications(context: ReadContext):
        return finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.list_own(context.authorization_scope),
                    "_links": {
                        "self": {"href": "/api/notifications"},
                        "channels": {"href": "/api/notification-channels"},
                        "problems": {"href": "/api/notification-problems"},
                    },
                }
            ),
        )

    @router.get("/api/notification-problems", response_model=NotificationCollectionResponse)
    def notification_problems(context: ReadContext):
        return finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.problems(context.authorization_scope),
                    "_links": {"self": {"href": "/api/notification-problems"}},
                }
            ),
        )

    @router.get("/api/notification-overview", response_model=NotificationCollectionResponse)
    def notification_overview(context: ReadContext):
        return finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.management_overview(
                        context.authorization_scope
                    ),
                    "_links": {"self": {"href": "/api/notification-overview"}},
                }
            ),
        )

    @router.get("/api/notification-channels", response_model=NotificationChannelsResponse)
    def notification_channels(context: ReadContext):
        channels = context.notification_service.channels()
        return finish(
            context,
            context.respond(
                {
                    "web_push": {
                        "available": channels.push_public_key is not None,
                        "public_key": channels.push_public_key,
                    },
                    "email_fallback_configured": channels.email_configured,
                    "sink_enabled": channels.sink_enabled,
                }
            ),
        )

    @router.post(
        "/api/push-subscriptions",
        status_code=201,
        response_model=PushSubscriptionResponse,
    )
    def register_push(context: BodyMutationContext, payload: PushSubscriptionRequest):
        endpoint = payload_data(context, payload)["endpoint"]
        return finish(
            context,
            context.respond(
                context.notification_service.register_push(context.authorization_scope, endpoint),
                HTTPStatus.CREATED,
            ),
        )

    @router.delete("/api/push-subscriptions/{id}", status_code=204)
    def unregister_push(context: MutationContext, id: int):
        return (
            not_found()
            if not context.notification_service.unregister_push(context.authorization_scope, id)
            else finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )

    @router.post(
        "/api/notifications/{id}/push-confirmation",
        response_model=PushConfirmationResponse,
    )
    def confirm_push(context: MutationContext, id: int):
        return (
            not_found()
            if not context.notification_service.confirm_push(context.authorization_scope, id)
            else finish(context, context.respond({"status": "technically_confirmed"}))
        )

    return router


def create_absence_router() -> APIRouter:
    """Build the absence and replacement integration routes."""
    router = APIRouter(route_class=BoundedBodyRoute)

    @router.get("/api/absence-reports")
    def absence_reports(context: ReadContext):
        return finish(
            context,
            context.respond(
                {
                    "items": context.absence_service.list(context.authorization_scope),
                    "_links": {"self": {"href": "/api/absence-reports"}},
                }
            ),
        )

    @router.get("/api/absence-reports/{id}")
    def absence_report(context: ReadContext, id: int):
        report = context.absence_service.get(context.authorization_scope, id)
        return not_found() if report is None else finish(context, context.respond(report))

    @router.post("/api/absence-reports", status_code=201)
    def create_absence(context: BodyMutationContext, payload: DomainResourceWrite):
        return finish(
            context,
            context.respond(
                context.absence_service.report(
                    context.authorization_scope, payload_data(context, payload)
                ),
                HTTPStatus.CREATED,
            ),
        )

    def absence_action(action: str):
        def endpoint(
            context: BodyMutationContext,
            report_id: int,
            payload: DomainResourceWrite = _OPTIONAL_OBJECT_BODY,
        ):
            data = payload_data(context, payload)
            service = context.absence_service
            result = {
                "select-replacement": lambda: service.select_replacement(
                    context.authorization_scope, report_id, data
                ),
                "withdraw": lambda: service.withdraw(context.authorization_scope, report_id),
                "reopen": lambda: service.reopen(context.authorization_scope, report_id, data),
                "cancel": lambda: service.cancel(context.authorization_scope, report_id, data),
            }[action]()
            return finish(context, context.respond(result))

        return endpoint

    for action in ("select-replacement", "withdraw", "reopen", "cancel"):
        router.add_api_route(
            f"/api/absence-reports/{{report_id}}/{action}",
            absence_action(action),
            methods=["POST"],
            name=f"absence_{action}",
        )

    @router.patch("/api/replacement-responses/{response_id}")
    def patch_response(
        context: BodyMutationContext,
        response_id: int,
        payload: DomainResourceWrite,
    ):
        return finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope,
                    response_id,
                    payload_data(context, payload),
                )
            ),
        )

    @router.post("/api/replacement-responses/{response_id}/respond")
    def post_response(
        context: BodyMutationContext,
        response_id: int,
        payload: DomainResourceWrite,
    ):
        return finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope,
                    response_id,
                    payload_data(context, payload),
                )
            ),
        )

    return router


def create_integration_router() -> APIRouter:
    """Compose the routers owned by the integration HTTP boundary."""
    router = APIRouter(route_class=BoundedBodyRoute)
    for owned_router in (
        create_calendar_router(),
        create_notification_router(),
        create_absence_router(),
    ):
        router.include_router(owned_router)
    return router
