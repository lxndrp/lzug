"""FastAPI routers for calendars, notifications, and absence integrations."""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Query

from .api_contracts import (
    CalendarEventCollectionResponse,
    CalendarFeedActivationRequest,
    CalendarFeedActivationResponse,
    CalendarFeedRevocationResponse,
    CalendarStatusResponse,
    NotificationChannelsResponse,
    NotificationCollectionResponse,
    PushConfirmationResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
)
from .fastapi_dependencies import BodyMutationContext, Context, MutationContext, ReadContext
from .fastapi_http import calendar_text, finish, not_found, request_body, validated_payload


def create_round_summary_router() -> APIRouter:
    """Build the round summary used by the calendar integration."""
    router = APIRouter()

    @router.get(
        "/api/round-summary",
        response_model=dict[str, object],
    )
    def round_summary(context: ReadContext, round_id: str | None = Query(default=None)):
        try:
            parsed_round_id = int(round_id or "1")
        except ValueError:
            return finish(
                context, context.respond({"error": "Invalid request"}, HTTPStatus.BAD_REQUEST)
            )
        return finish(
            context,
            context.read_application.round_summary(context.authorization_scope, parsed_round_id),
        )

    return router


def create_public_calendar_router() -> APIRouter:
    """Build token and event based public iCalendar routes."""
    router = APIRouter()

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
        if not id.isdigit():
            return not_found()
        calendar = context.calendar_service.event_ics(int(id), context.authorization_scope)
        return not_found() if calendar is None else calendar_text(context, calendar)

    return router


def create_calendar_management_router() -> APIRouter:
    """Build personal calendar status, lifecycle, and event routes."""
    router = APIRouter()

    @router.get("/api/calendar", response_model=CalendarStatusResponse)
    @router.get("/api/calendar/feed", response_model=CalendarStatusResponse)
    def calendar_status(context: ReadContext):
        result = {
            **context.calendar_service.status(context.authorization_scope),
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
                    "items": context.calendar_service.list_events(context.authorization_scope),
                    "_links": {"self": {"href": "/api/calendar/events"}},
                }
            ),
        )

    @router.post(
        "/api/calendar/feed",
        status_code=201,
        response_model=CalendarFeedActivationResponse,
        openapi_extra=request_body(CalendarFeedActivationRequest),
    )
    def activate_feed(context: BodyMutationContext):
        payload = validated_payload(context, CalendarFeedActivationRequest, exclude_unset=False)
        result = context.calendar_service.activate(
            context.authorization_scope,
            rotate=payload["rotate"],
        )
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
        context.calendar_service.revoke(context.authorization_scope)
        result = {
            **context.calendar_service.status(context.authorization_scope),
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
    router = APIRouter()
    for owned_router in (
        create_round_summary_router(),
        create_public_calendar_router(),
        create_calendar_management_router(),
    ):
        router.routes.extend(owned_router.routes)
    return router


def create_notification_router() -> APIRouter:
    """Build notification reads and push-subscription lifecycle routes."""
    router = APIRouter()

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
        openapi_extra=request_body(PushSubscriptionRequest),
    )
    def register_push(context: BodyMutationContext):
        endpoint = validated_payload(context, PushSubscriptionRequest)["endpoint"]
        return finish(
            context,
            context.respond(
                context.notification_service.register_push(context.authorization_scope, endpoint),
                HTTPStatus.CREATED,
            ),
        )

    @router.delete("/api/push-subscriptions/{id}", status_code=204)
    def unregister_push(context: MutationContext, id: str):
        return (
            not_found()
            if not context.notification_service.unregister_push(
                context.authorization_scope, int(id)
            )
            else finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )

    @router.post(
        "/api/notifications/{id}/push-confirmation",
        response_model=PushConfirmationResponse,
    )
    def confirm_push(context: MutationContext, id: str):
        return (
            not_found()
            if not context.notification_service.confirm_push(context.authorization_scope, int(id))
            else finish(context, context.respond({"status": "technically_confirmed"}))
        )

    return router


def create_absence_router() -> APIRouter:
    """Build the absence and replacement integration routes."""
    router = APIRouter()

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
    def absence_report(context: ReadContext, id: str):
        report = context.absence_service.get(context.authorization_scope, int(id))
        return not_found() if report is None else finish(context, context.respond(report))

    @router.post("/api/absence-reports", status_code=201)
    def create_absence(context: BodyMutationContext):
        return finish(
            context,
            context.respond(
                context.absence_service.report(context.authorization_scope, context.read_json()),
                HTTPStatus.CREATED,
            ),
        )

    def absence_action(action: str):
        def endpoint(context: BodyMutationContext, report_id: str):
            payload = context.read_json()
            ident = int(report_id)
            service = context.absence_service
            result = {
                "select-replacement": lambda: service.select_replacement(
                    context.authorization_scope, ident, payload
                ),
                "withdraw": lambda: service.withdraw(context.authorization_scope, ident),
                "reopen": lambda: service.reopen(context.authorization_scope, ident, payload),
                "cancel": lambda: service.cancel(context.authorization_scope, ident, payload),
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
    def patch_response(context: BodyMutationContext, response_id: str):
        return finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope, int(response_id), context.read_json()
                )
            ),
        )

    @router.post("/api/replacement-responses/{response_id}/respond")
    def post_response(context: BodyMutationContext, response_id: str):
        return finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope, int(response_id), context.read_json()
                )
            ),
        )

    return router


def create_integration_router() -> APIRouter:
    """Compose the routers owned by the integration HTTP boundary."""
    router = APIRouter()
    for owned_router in (
        create_calendar_router(),
        create_notification_router(),
        create_absence_router(),
    ):
        router.routes.extend(owned_router.routes)
    return router
