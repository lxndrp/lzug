from __future__ import annotations

import os
import sqlite3
import unittest
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from threading import Event, Thread
from unittest.mock import MagicMock, patch
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from backend.auth import AuthenticationRepository
from backend.authorization import AuthorizationService
from backend.database import session_scope
from backend.models import ExamDay, ExamDayAssignment, NotificationDelivery
from backend.notifications import DELIVERY_CLAIM_TTL, NotificationService
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


def vapid_private_key() -> str:
    return (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )


class NotificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        self.service = NotificationService(self.db_path)
        self.authentication = AuthenticationRepository(self.db_path)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def scope(self, account_id: int):
        credentials = self.authentication.create_session(account_id)
        context = self.authentication.authenticate(credentials.token)
        assert context is not None
        return AuthorizationService(self.db_path).scope(context)

    def create_pending_sink(self) -> int:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO notification "
                "(committee_id, recipient_member_id, event_type, origin_key, "
                " title, message, action_path) "
                "VALUES (1, 1, 'synthetic_test', ?, 'Claim test', "
                "        'No external content', '/notifications')",
                (f"claim-test:{uuid4().hex}",),
            )
            notification_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO notification_delivery "
                "(notification_id, channel, target_key, status) "
                "VALUES (?, 'sink', 'operator-sink', 'pending')",
                (notification_id,),
            )
            connection.commit()
        return notification_id

    def assert_claim_is_committed_without_open_write_transaction(
        self, notification_id: int
    ) -> None:
        with sqlite3.connect(self.db_path, timeout=0.2) as connection:
            connection.execute("BEGIN IMMEDIATE")
            claim = connection.execute(
                "SELECT claim_token FROM notification_delivery WHERE notification_id = ?",
                (notification_id,),
            ).fetchone()
            connection.rollback()
        self.assertIsNotNone(claim)
        self.assertIsNotNone(claim[0])

    def test_event_recipients_are_idempotent_and_channel_neutral(self) -> None:
        first = self.service.create_for_event("availability_requested", 1)
        second = self.service.create_for_event("availability_requested", 1)

        self.assertEqual({"created": 8, "dispatched": 0, "problems": 8}, first)
        self.assertEqual(0, second["created"])
        self.assertEqual(1, len(self.service.list_own(self.scope(1))))
        self.assertEqual(1, len(self.service.list_own(self.scope(2))))
        problems = self.service.problems(self.scope(1))
        self.assertEqual(8, len(problems))
        self.assertTrue(all(problem["status"] == "unavailable" for problem in problems))
        self.assertNotIn("message", problems[0])
        overview = self.service.management_overview(self.scope(1))
        self.assertEqual(8, len(overview))
        self.assertNotIn("message", overview[0])

    def test_reminder_and_deadline_target_only_open_members_plus_management(self) -> None:
        reminder = self.service.create_for_event("availability_reminder", 1)
        deadline = self.service.create_for_event("availability_deadline_expired", 1)

        self.assertEqual(2, reminder["created"])
        self.assertEqual(4, deadline["created"])
        with sqlite3.connect(self.db_path) as connection:
            reminder_members = connection.execute(
                "SELECT recipient_member_id FROM notification "
                "WHERE event_type = 'availability_reminder' ORDER BY recipient_member_id"
            ).fetchall()
            deadline_members = connection.execute(
                "SELECT recipient_member_id FROM notification "
                "WHERE event_type = 'availability_deadline_expired' ORDER BY recipient_member_id"
            ).fetchall()
        self.assertEqual([(5,), (7,)], reminder_members)
        self.assertEqual([(1,), (2,), (5,), (7,)], deadline_members)

    def test_plan_confirmation_uses_actual_examiner_and_fallback_assignments(self) -> None:
        with session_scope(self.db_path) as session:
            day = ExamDay(
                exam_round_id=1,
                location_id=1,
                date="2026-11-23",
                status="confirmed",
            )
            session.add(day)
            session.flush()
            session.add_all(
                [
                    ExamDayAssignment(
                        exam_day_id=day.id,
                        committee_member_id=member_id,
                        assignment_role=role,
                        day_part="morning",
                        fallback_status="confirmed" if role == "fallback" else None,
                    )
                    for member_id, role in ((1, "examiner"), (3, "examiner"), (5, "fallback"))
                ]
            )

        result = self.service.create_for_event("plan_confirmed", 1)

        self.assertEqual(3, result["created"])
        with sqlite3.connect(self.db_path) as connection:
            recipients = connection.execute(
                "SELECT recipient_member_id FROM notification "
                "WHERE event_type = 'plan_confirmed' ORDER BY recipient_member_id"
            ).fetchall()
        self.assertEqual([(1,), (3,), (5,)], recipients)
        own = self.service.list_own(self.scope(1))[0]
        self.assertIn("2026-11-23", own["message"])
        self.assertIn("Prüfungszentrum Alpha", own["message"])

    def test_web_push_registration_confirmation_and_timeout_fallback_are_separate(self) -> None:
        private_key = vapid_private_key()
        with patch.dict(
            os.environ,
            {
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": private_key,
                "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
            },
            clear=False,
        ):
            registration = self.service.register_push(
                self.scope(1), "https://push.example.invalid/subscription"
            )
            with patch.object(self.service, "_send_web_push") as send:
                result = self.service.create_for_event("availability_requested", 1)

            self.assertEqual(8, result["created"])
            send.assert_called_once()
            own_notice = self.service.list_own(self.scope(1))[0]
            self.assertTrue(self.service.confirm_push(self.scope(1), int(own_notice["id"])))

            with session_scope(self.db_path) as session:
                delivery = (
                    session.query(NotificationDelivery)
                    .filter_by(notification_id=own_notice["id"], channel="web_push")
                    .one()
                )
                self.assertEqual("technically_confirmed", delivery.status)
                self.assertEqual(1, delivery.attempt_count)

            self.assertTrue(self.service.unregister_push(self.scope(1), int(registration["id"])))

    def test_web_push_uses_vapid_without_exposing_notification_content(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.status = 201
        with (
            patch.dict(
                os.environ,
                {
                    "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": vapid_private_key(),
                    "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
                },
                clear=False,
            ),
            patch("urllib.request.urlopen", return_value=response) as urlopen,
        ):
            self.service._send_web_push("https://push.example.invalid/subscription", 17)

        request = urlopen.call_args.args[0]
        self.assertEqual(b"", request.data)
        self.assertEqual("POST", request.method)
        self.assertTrue(request.get_header("Authorization").startswith("vapid t="))
        self.assertEqual("300", request.get_header("Ttl"))

    def test_invalid_push_is_disabled_and_configured_email_fallback_is_sent(self) -> None:
        private_key = vapid_private_key()
        smtp = MagicMock()
        smtp.return_value.__enter__.return_value = smtp
        with patch.dict(
            os.environ,
            {
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": private_key,
                "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
                "LZUG_SMTP_HOST": "smtp.example.invalid",
                "LZUG_EXTERNAL_URL": "https://lzug.example.invalid",
            },
            clear=False,
        ):
            registration = self.service.register_push(
                self.scope(1), "https://push.example.invalid/expired"
            )
            rejected = urllib.error.HTTPError(
                "https://push.example.invalid/expired", 410, "Gone", {}, None
            )
            with patch.object(self.service, "_send_web_push", side_effect=rejected):
                self.service.create_for_event("availability_requested", 1)
            with patch("smtplib.SMTP", smtp):
                self.service.process_deliveries()

        smtp.assert_called_once_with("smtp.example.invalid", 25, timeout=10)
        sent = smtp.send_message.call_args.args[0]
        self.assertEqual("testperson.alpha@example.invalid", sent["To"])
        self.assertNotIn("Testperson Beta", sent.get_content())
        with sqlite3.connect(self.db_path) as connection:
            invalidated_at = connection.execute(
                "SELECT invalidated_at FROM push_subscription WHERE id = ?",
                (registration["id"],),
            ).fetchone()[0]
            statuses = connection.execute(
                "SELECT channel, status FROM notification_delivery "
                "WHERE notification_id = (SELECT id FROM notification "
                "WHERE recipient_member_id = 1 AND event_type = 'availability_requested') "
                "ORDER BY channel"
            ).fetchall()
        self.assertIsNotNone(invalidated_at)
        self.assertEqual(
            [("email", "technically_confirmed"), ("web_push", "permanently_failed")],
            statuses,
        )

    def test_temporary_push_failures_retry_with_a_bound_and_no_duplicates(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": vapid_private_key(),
                "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
            },
            clear=False,
        ):
            self.service.register_push(self.scope(1), "https://push.example.invalid/temporary")
            with patch.object(self.service, "_send_web_push", side_effect=OSError("offline")):
                first = self.service.create_for_event("availability_requested", 1)
                for days in (1, 2, 3):
                    self.service.process_deliveries(now=datetime.now(UTC) + timedelta(days=days))

        self.assertEqual(8, first["created"])
        with sqlite3.connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM notification "
                "WHERE recipient_member_id = 1 AND event_type = 'availability_requested'"
            ).fetchone()[0]
            delivery = connection.execute(
                "SELECT status, attempt_count, next_attempt_at FROM notification_delivery "
                "WHERE channel = 'web_push' AND target_key != 'none'"
            ).fetchone()
        self.assertEqual(1, count)
        self.assertEqual(("permanently_failed", 4, None), delivery)

    def test_channel_access_runs_after_the_claim_transaction_commits(self) -> None:
        private_key = vapid_private_key()
        with patch.dict(
            os.environ,
            {
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": private_key,
                "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
            },
            clear=False,
        ):
            self.service.register_push(
                self.scope(1), "https://push.example.invalid/transaction-boundary"
            )
            with patch.object(self.service, "process_deliveries", return_value=0):
                web_push = self.service.synthetic_test(1, "web_push")
            with patch.object(
                self.service,
                "_send_web_push",
                side_effect=lambda _endpoint, notification_id: (
                    self.assert_claim_is_committed_without_open_write_transaction(notification_id)
                ),
            ):
                self.assertEqual(1, self.service.process_deliveries())

        with patch.dict(os.environ, {"LZUG_SMTP_HOST": "smtp.example.invalid"}, clear=False):
            with patch.object(self.service, "process_deliveries", return_value=0):
                email = self.service.synthetic_test(1, "email")
            with patch.object(
                self.service,
                "_send_email",
                side_effect=lambda delivery: (
                    self.assert_claim_is_committed_without_open_write_transaction(
                        delivery.notification_id
                    )
                ),
            ):
                self.assertEqual(1, self.service.process_deliveries())

        sink_id = self.create_pending_sink()
        with patch.object(
            self.service,
            "_send_sink",
            side_effect=lambda notification_id: (
                self.assert_claim_is_committed_without_open_write_transaction(notification_id)
            ),
        ):
            self.assertEqual(1, self.service.process_deliveries())

        self.assertIsInstance(web_push["notification_id"], int)
        self.assertIsInstance(email["notification_id"], int)
        self.assertIsInstance(sink_id, int)

    def test_parallel_workers_do_not_dispatch_the_same_active_claim(self) -> None:
        notification_id = self.create_pending_sink()
        started = Event()
        release = Event()
        calls: list[int] = []
        results: list[int] = []
        errors: list[BaseException] = []

        def send_sink(active_notification_id: int) -> None:
            calls.append(active_notification_id)
            self.assert_claim_is_committed_without_open_write_transaction(active_notification_id)
            if len(calls) == 1:
                started.set()
                release.wait(timeout=2)

        def process_first_worker() -> None:
            try:
                results.append(NotificationService(self.db_path).process_deliveries())
            except BaseException as error:  # pragma: no cover - asserted below
                errors.append(error)

        with patch.object(NotificationService, "_send_sink", side_effect=send_sink):
            worker = Thread(target=process_first_worker)
            worker.start()
            self.assertTrue(started.wait(timeout=2))
            second_result = NotificationService(self.db_path).process_deliveries()
            release.set()
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual([], errors)
        self.assertEqual([1], results)
        self.assertEqual(0, second_result)
        self.assertEqual([notification_id], calls)

    def test_expired_claim_is_reclaimed_and_stale_or_foreign_results_are_rejected(
        self,
    ) -> None:
        notification_id = self.create_pending_sink()
        first_started = datetime.now(UTC)
        first = self.service._claim_due_deliveries(first_started, "first-worker", batch_size=1)
        self.assertEqual(1, len(first))
        overview = self.service.management_overview(self.scope(1))
        active = next(row for row in overview if row["notification_id"] == notification_id)
        self.assertEqual("active", active["claim_state"])

        with patch.object(self.service, "_send_sink", side_effect=OSError("worker abort")):
            first_result = self.service._dispatch_claimed(first[0], first_started)
        self.assertEqual("temporarily_failed", first_result.status)
        foreign = replace(first[0], claim_token="foreign-worker")
        self.assertFalse(
            self.service._complete_claim(
                foreign, first_result, first_started + timedelta(seconds=1)
            )
        )
        self.assertEqual(
            [],
            self.service._claim_due_deliveries(
                first_started + DELIVERY_CLAIM_TTL - timedelta(seconds=1),
                "early-worker",
                batch_size=1,
            ),
        )

        second_started = first_started + DELIVERY_CLAIM_TTL + timedelta(seconds=1)
        restarted_service = NotificationService(self.db_path)
        second = restarted_service._claim_due_deliveries(
            second_started, "second-worker", batch_size=1
        )
        self.assertEqual(1, len(second))
        second_result = restarted_service._dispatch_claimed(second[0], second_started)
        self.assertTrue(
            restarted_service._complete_claim(
                second[0], second_result, second_started + timedelta(seconds=1)
            )
        )
        self.assertFalse(
            self.service._complete_claim(
                first[0], first_result, second_started + timedelta(seconds=2)
            )
        )

        with sqlite3.connect(self.db_path) as connection:
            delivery = connection.execute(
                "SELECT status, attempt_count, claim_token, claimed_at, claim_expires_at "
                "FROM notification_delivery WHERE notification_id = ?",
                (notification_id,),
            ).fetchone()
        self.assertEqual(("technically_confirmed", 1, None, None, None), delivery)

    def test_processing_batch_is_bounded(self) -> None:
        notification_id = self.create_pending_sink()
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                "INSERT INTO notification_delivery "
                "(notification_id, channel, target_key, status) "
                "VALUES (?, 'sink', ?, 'pending')",
                [(notification_id, f"operator-sink-{index}") for index in range(20)],
            )
            connection.commit()

        with patch.object(self.service, "_send_sink") as send:
            self.assertEqual(20, self.service.process_deliveries())
            self.assertEqual(20, send.call_count)
            self.assertEqual(1, self.service.process_deliveries())
            self.assertEqual(21, send.call_count)

    def test_due_events_retry_safely_and_retention_follows_round(self) -> None:
        processed = self.service.process_due_events(now=datetime(2026, 10, 3, tzinfo=UTC))
        repeated = self.service.process_due_events(
            now=datetime(2026, 10, 3, tzinfo=UTC) + timedelta(hours=1)
        )

        self.assertEqual(6, processed["created"])
        self.assertEqual(0, repeated["created"])
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript("""
                INSERT INTO committee (id, name) VALUES (2, 'Retention committee');
                INSERT INTO person (id, first_name, last_name, email)
                  VALUES (9, 'Retention', 'Member', 'retention@example.invalid');
                INSERT INTO committee_member
                  (id, person_id, committee_id, member_status, committee_role, representing_side)
                  VALUES (9, 9, 2, 'ordinary', 'chair', 'employer');
                INSERT INTO exam_round
                  (id, exam_half_year_id, committee_id, name, availability_deadline,
                   created_by_member_id)
                  VALUES (2, 1, 2, 'Retention round', '2026-10-10 18:00:00', 9);
                """)
            connection.commit()
        self.service.create_for_event("availability_requested", 2)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("DELETE FROM exam_round WHERE id = 2")
            connection.commit()
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM notification WHERE exam_round_id = 2"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM notification_delivery d "
                    "JOIN notification n ON n.id = d.notification_id "
                    "WHERE n.exam_round_id = 2"
                ).fetchone()[0],
            )

    def test_sink_prevents_real_recipient_channels(self) -> None:
        with patch.dict(os.environ, {"LZUG_NOTIFICATION_SINK": "true"}, clear=False):
            result = self.service.create_for_event("availability_requested", 1)

        self.assertEqual(8, result["created"])
        with sqlite3.connect(self.db_path) as connection:
            channels = connection.execute(
                "SELECT DISTINCT channel, status FROM notification_delivery"
            ).fetchall()
        self.assertEqual([("sink", "technically_confirmed")], channels)


class NotificationApiTests(unittest.TestCase):
    def test_domain_transition_returns_a_warning_instead_of_rolling_back(self) -> None:
        class BrokenNotifications:
            def create_for_event(self, _event_type: str, _round_id: int):
                raise OSError("synthetic delivery failure")

        with (
            TempDatabase() as db_path,
            patch(
                "backend.notifications.NotificationService.create_for_event",
                BrokenNotifications().create_for_event,
            ),
            ApiServer(db_path) as api,
        ):
            status, result = api.request("POST", "/api/exam-rounds/1/request-availabilities", {})

        assert_status(status, HTTPStatus.OK)
        self.assertEqual("availability_requested", result["status"])
        self.assertIn("Fachvorgang wurde gespeichert", result["notification_warning"])

    def test_members_only_read_own_content_and_management_gets_metadata(self) -> None:
        with TempDatabase() as db_path:
            service = NotificationService(db_path)
            service.create_for_event("availability_requested", 1)
            authentication = AuthenticationRepository(db_path)
            chair = authentication.create_session(1)
            member = authentication.create_session(2)

            with ApiServer(db_path) as api:
                status, own = api.request("GET", "/api/notifications", credentials=member)
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(1, len(own["items"]))

                status, problems = api.request(
                    "GET", "/api/notification-problems", credentials=chair
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(8, len(problems["items"]))
                self.assertNotIn("message", problems["items"][0])

                status, overview = api.request(
                    "GET", "/api/notification-overview", credentials=chair
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(8, len(overview["items"]))
                self.assertNotIn("message", overview["items"][0])

                status, member_problems = api.request(
                    "GET", "/api/notification-problems", credentials=member
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual([], member_problems["items"])

                status, member_overview = api.request(
                    "GET", "/api/notification-overview", credentials=member
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual([], member_overview["items"])

    def test_push_registration_is_csrf_protected_and_bound_to_person(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, _body = api.request(
                "POST",
                "/api/push-subscriptions",
                {"endpoint": "https://push.example.invalid/one"},
                authenticated=False,
            )
            assert_status(status, HTTPStatus.UNAUTHORIZED)

            status, registration = api.request(
                "POST",
                "/api/push-subscriptions",
                {"endpoint": "https://push.example.invalid/one"},
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertTrue(registration["active"])
