from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.routing import APIRoute
from pydantic import ValidationError

from backend.api_contracts import CalendarFeedActivationRequest
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.fastapi_integration_routes import (
    create_absence_router,
    create_calendar_router,
    create_integration_router,
    create_notification_router,
)


def _operations(router) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


class FastAPIIntegrationRouterTests(unittest.TestCase):
    def test_calendar_feed_rotation_keeps_compatible_boolean_forms(self) -> None:
        for value in (True, 1, 2, "true", "yes", "on", "1"):
            with self.subTest(value=value):
                self.assertTrue(
                    CalendarFeedActivationRequest.model_validate({"rotate": value}).rotate
                )
        for value in (False, 0, "false", "no", "off", "0"):
            with self.subTest(value=value):
                self.assertFalse(
                    CalendarFeedActivationRequest.model_validate({"rotate": value}).rotate
                )
        with self.assertRaises(ValidationError):
            CalendarFeedActivationRequest.model_validate({"rotate": "sometimes"})

    def test_integration_router_composes_owned_route_groups(self) -> None:
        calendar = _operations(create_calendar_router())
        notifications = _operations(create_notification_router())
        absences = _operations(create_absence_router())

        self.assertEqual(
            {
                ("GET", "/api/round-summary"),
                ("GET", "/api/calendar"),
                ("GET", "/api/calendar/feed"),
                ("POST", "/api/calendar/feed"),
                ("DELETE", "/api/calendar/feed"),
                ("GET", "/api/calendar/events"),
                ("GET", "/api/calendar/feed/{token}.ics"),
                ("GET", "/api/calendar/events/{id}.ics"),
            },
            calendar,
        )
        self.assertEqual(
            {
                ("GET", "/api/notifications"),
                ("GET", "/api/notification-problems"),
                ("GET", "/api/notification-overview"),
                ("GET", "/api/notification-channels"),
                ("POST", "/api/push-subscriptions"),
                ("DELETE", "/api/push-subscriptions/{id}"),
                ("POST", "/api/notifications/{id}/push-confirmation"),
            },
            notifications,
        )
        self.assertEqual(
            {
                ("GET", "/api/absence-reports"),
                ("GET", "/api/absence-reports/{id}"),
                ("POST", "/api/absence-reports"),
                ("POST", "/api/absence-reports/{report_id}/select-replacement"),
                ("POST", "/api/absence-reports/{report_id}/withdraw"),
                ("POST", "/api/absence-reports/{report_id}/reopen"),
                ("POST", "/api/absence-reports/{report_id}/cancel"),
                ("PATCH", "/api/replacement-responses/{response_id}"),
                ("POST", "/api/replacement-responses/{response_id}/respond"),
            },
            absences,
        )
        self.assertEqual(
            calendar | notifications | absences,
            _operations(create_integration_router()),
        )

    def test_calendar_and_push_contracts_reference_declarative_models(self) -> None:
        with TemporaryDirectory() as directory:
            config = FastAPIConfig(
                db_path=Path(directory) / "integrations.sqlite", session_cookie_name="session"
            )
            document = create_app(config).openapi()

        requests = {
            ("/api/calendar/feed", "CalendarFeedActivationRequest"),
            ("/api/push-subscriptions", "PushSubscriptionRequest"),
        }
        for path, model in requests:
            with self.subTest(path=path):
                schema = document["paths"][path]["post"]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(model, schema["title"])

        responses = {
            ("get", "/api/calendar", "200", "CalendarStatusResponse"),
            ("post", "/api/calendar/feed", "201", "CalendarFeedActivationResponse"),
            ("delete", "/api/calendar/feed", "200", "CalendarFeedRevocationResponse"),
            ("get", "/api/calendar/events", "200", "CalendarEventCollectionResponse"),
            ("get", "/api/notifications", "200", "NotificationCollectionResponse"),
            ("get", "/api/notification-channels", "200", "NotificationChannelsResponse"),
            ("post", "/api/push-subscriptions", "201", "PushSubscriptionResponse"),
            (
                "post",
                "/api/notifications/{id}/push-confirmation",
                "200",
                "PushConfirmationResponse",
            ),
        }
        for method, path, status, model in responses:
            with self.subTest(path=path, method=method):
                schema = document["paths"][path][method]["responses"][status]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(f"#/components/schemas/{model}", schema["$ref"])


if __name__ == "__main__":
    unittest.main()
