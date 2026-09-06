from __future__ import annotations

import unittest

from icalendar import Calendar
from sqlalchemy import select, text

from backend.auth import AuthenticationRepository
from backend.authorization import AuthorizationService
from backend.calendar import CalendarService
from backend.database import connect, session_scope
from backend.models import CalendarEvent, CommitteeMember, ExamDay, ExamDayAssignment, ExamSlot
from backend.planning import PlanningService
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class CalendarServiceTests(unittest.TestCase):
    def _scope(self, db_path):
        authentication = AuthenticationRepository(db_path)
        credentials = authentication.create_session(1)
        context = authentication.authenticate(credentials.token)
        assert context is not None
        return AuthorizationService(db_path).scope(context)

    def _confirmed_database(self):
        database = TempDatabase()
        db_path = database.__enter__()
        PlanningService(db_path).generate_proposal(1)
        PlanningService(db_path).confirm_plan(1)
        return database, db_path

    def test_activation_is_opaque_and_repeated_sync_is_idempotent(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path, external_url="https://app.example.invalid")
            scope = self._scope(db_path)
            activation = service.activate(scope)
            events = service.list_events(scope)
            with connect(db_path) as connection:
                (token_hash,) = connection.execute(
                    text("SELECT token_hash FROM calendar_feed WHERE person_id = 1")
                ).one()

            self.assertTrue(activation["feed_url"].startswith("https://app.example.invalid/"))
            token = activation["feed_url"].rsplit("/", 1)[-1][:-4]
            self.assertNotEqual(token, token_hash)
            self.assertEqual(64, len(token_hash))
            self.assertGreater(len(events), 0)
            before = {event["id"]: event for event in events}

            self.assertEqual(0, service.sync_person(scope.person_id))
            after = {event["id"]: event for event in service.list_events(scope)}
            self.assertEqual(
                {event_id: event["version"] for event_id, event in before.items()},
                {event_id: event["version"] for event_id, event in after.items()},
            )
        finally:
            database.__exit__(None, None, None)

    def test_ics_uses_rfc5545_serialization_for_text_and_timezones(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path)
            service.sync_round(1)
            with session_scope(db_path) as session:
                event = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert event is not None
                event.round_name = "Prüfung,;\\ " + ("Lange Runde " * 12)
                event.role = "Regulärer Prüfer\nmit Zusatz"
                event.location = "Ort,;\\\n" + ("Zusatzinformation " * 12)
                expected_uid = f"{event.external_event_id}@lzug"
                expected_summary = event.round_name + " – " + event.role
                expected_location = event.location
                expected_description = f"Rolle: {event.role}\nDetails: {event.secure_reference}"
                expected_version = event.version
                ics = service._calendar([event], "Persönlicher Prüfungskalender")

            encoded = ics.encode("utf-8")
            self.assertTrue(ics.endswith("\r\n"))
            self.assertNotIn(b"\n", encoded.replace(b"\r\n", b""))
            self.assertTrue(all(len(line) <= 75 for line in encoded.split(b"\r\n") if line))

            calendar = Calendar.from_ical(encoded)
            parsed = calendar.walk("VEVENT")[0]
            self.assertEqual(expected_uid, str(parsed["UID"]))
            self.assertEqual(expected_version, int(parsed["SEQUENCE"]))
            self.assertEqual("CONFIRMED", str(parsed["STATUS"]))
            self.assertEqual(expected_summary, str(parsed["SUMMARY"]))
            self.assertEqual(expected_location, str(parsed["LOCATION"]))
            self.assertEqual(expected_description, str(parsed["DESCRIPTION"]))
            self.assertEqual("Europe/Berlin", parsed["DTSTART"].params["TZID"])
            self.assertEqual("Europe/Berlin", parsed["DTEND"].params["TZID"])
            self.assertEqual(
                service.time_zone,
                parsed.decoded("DTSTART").tzinfo,
            )
        finally:
            database.__exit__(None, None, None)

    def test_time_change_keeps_uid_and_increments_version(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            event = service.list_events(scope)[0]
            with session_scope(db_path) as session:
                calendar_event = session.get(CalendarEvent, event["id"])
                assert calendar_event is not None
                slot = session.scalars(select(ExamSlot).order_by(ExamSlot.id)).first()
                assert slot is not None
                slot.starts_at = "2026-11-16 09:15:00"

            service.sync_round(1)
            changed = next(item for item in service.list_events(scope) if item["id"] == event["id"])
            self.assertEqual(event["external_event_id"], changed["external_event_id"])
            self.assertEqual(event["version"] + 1, changed["version"])
            self.assertEqual("updated", changed["status"])
            service.sync_round(1)
            stable = next(item for item in service.list_events(scope) if item["id"] == event["id"])
            self.assertEqual(changed["version"], stable["version"])
        finally:
            database.__exit__(None, None, None)

    def test_cancellation_is_kept_in_current_half_year_feed(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            event = service.list_events(scope)[0]
            with session_scope(db_path) as session:
                calendar_event = session.get(CalendarEvent, event["id"])
                assert calendar_event is not None
                day = session.get(ExamDay, calendar_event.exam_day_id)
                assert day is not None
                day.status = "cancelled"

            service.sync_round(1)
            cancelled = next(
                item for item in service.list_events(scope) if item["id"] == event["id"]
            )
            self.assertEqual("cancelled", cancelled["status"])
            self.assertEqual(event["external_event_id"], cancelled["external_event_id"])
        finally:
            database.__exit__(None, None, None)

    def test_partial_cancellation_updates_only_the_affected_day_part(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            with session_scope(db_path) as session:
                events = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).all()
                target = None
                for candidate in events:
                    assignment = session.get(ExamDayAssignment, candidate.exam_day_assignment_id)
                    assert assignment is not None
                    slots = session.scalars(
                        select(ExamSlot)
                        .where(ExamSlot.exam_day_id == candidate.exam_day_id)
                        .order_by(ExamSlot.starts_at, ExamSlot.sequence_number)
                    ).all()
                    section = service._section_slots(slots, assignment.day_part)
                    if len(section) > 1:
                        target = (candidate, section[0])
                        break
                self.assertIsNotNone(target)
                event, slot = target
                event_id = event.id
                before = event.version
                slot.status = "cancelled"

            service.sync_round(1)
            changed = next(item for item in service.list_events(scope) if item["id"] == event_id)
            self.assertEqual(before + 1, changed["version"])
            self.assertEqual("updated", changed["status"])
        finally:
            database.__exit__(None, None, None)

    def test_assignment_replacement_cancels_old_recipient_and_creates_new_uid(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = CalendarService(db_path)
            service.sync_round(1)
            with session_scope(db_path) as session:
                original = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert original is not None
                assignment = session.get(ExamDayAssignment, original.exam_day_assignment_id)
                assert assignment is not None
                replacement = None
                for candidate in session.scalars(
                    select(CommitteeMember)
                    .where(CommitteeMember.id != original.recipient_member_id)
                    .order_by(CommitteeMember.id)
                ):
                    occupied = session.scalars(
                        select(ExamDayAssignment.id).where(
                            ExamDayAssignment.exam_day_id == assignment.exam_day_id,
                            ExamDayAssignment.committee_member_id == candidate.id,
                            ExamDayAssignment.assignment_role == assignment.assignment_role,
                            ExamDayAssignment.day_part == assignment.day_part,
                        )
                    ).first()
                    if occupied is None:
                        replacement = candidate
                        break
                assert replacement is not None
                original_id = original.id
                assignment.committee_member_id = replacement.id
                source_key = original.source_key.rsplit(":", 1)[0]

            service.sync_round(1)
            with session_scope(db_path) as session:
                events = session.scalars(
                    select(CalendarEvent).where(CalendarEvent.source_key.like(f"{source_key}%"))
                ).all()
                self.assertEqual(2, len(events))
                old = next(item for item in events if item.id == original_id)
                new = next(item for item in events if item.id != original_id)
                self.assertEqual("cancelled", old.status)
                self.assertEqual("sent", new.status)
                self.assertNotEqual(old.external_event_id, new.external_event_id)
        finally:
            database.__exit__(None, None, None)


class CalendarApiTests(unittest.TestCase):
    def test_authenticated_lifecycle_and_public_feed_are_personal(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            PlanningService(db_path).generate_proposal(1)
            status, confirmed = api.request("POST", "/api/exam-rounds/1/confirm-plan", {})
            assert_status(status, 200)
            self.assertEqual("plan_confirmed", confirmed["status"])

            status, activation = api.request("POST", "/api/calendar/feed", {})
            assert_status(status, 201)
            feed_path = activation["feed_url"].replace("https://app.example.invalid", "")

            status, events = api.request("GET", "/api/calendar/events")
            assert_status(status, 200)
            self.assertTrue(events["items"])
            event_id = events["items"][0]["id"]

            status, headers, body = api.request_raw("GET", feed_path, authenticated=False)
            assert_status(status, 200)
            self.assertEqual("text/calendar", headers["content-type"].split(";", 1)[0])
            ics = body.decode("utf-8")
            self.assertIn("BEGIN:VCALENDAR", ics)
            self.assertIn("UID:", ics)
            self.assertNotIn("Prüfling", ics)

            status, headers, body = api.request_raw("GET", f"/api/calendar/events/{event_id}.ics")
            assert_status(status, 200)
            self.assertEqual("text/calendar", headers["content-type"].split(";", 1)[0])
            self.assertIn("BEGIN:VEVENT", body.decode("utf-8"))

            status, _ = api.request("DELETE", "/api/calendar/feed")
            assert_status(status, 200)
            status, _headers, _body = api.request_raw("GET", feed_path, authenticated=False)
            assert_status(status, 404)

    def test_other_member_cannot_download_an_event(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            PlanningService(db_path).generate_proposal(1)
            PlanningService(db_path).confirm_plan(1)
            status, events = api.request("GET", "/api/calendar/events")
            assert_status(status, 200)
            event_id = events["items"][0]["id"]
            other_credentials = AuthenticationRepository(db_path).create_session(2)
            status, _headers, _body = api.request_raw(
                "GET",
                f"/api/calendar/events/{event_id}.ics",
                credentials=other_credentials,
            )
            assert_status(status, 404)
