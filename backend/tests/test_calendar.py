from __future__ import annotations

import hashlib
import unittest
from contextlib import contextmanager
from dataclasses import fields, replace
from threading import Event, Thread, current_thread
from time import monotonic, sleep
from unittest.mock import patch

from icalendar import Calendar
from sqlalchemy import select, text

from backend.calendar.feed_lifecycle import (
    CalendarFeedCoordinator,
    FeedConflictError,
    FeedRevocationPendingError,
)
from backend.calendar.ports import CalendarEventSnapshot, CalendarScope
from backend.calendar.service import CalendarService
from backend.composition import (
    authorization_service,
    identity_service,
    planning_service,
)
from backend.composition import (
    calendar_service as create_calendar_service,
)
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.calendar import SQLiteCalendarPersistence
from backend.persistence.database import apply_migrations, connect, connection_scope, session_scope
from backend.persistence.identity import SQLiteIdentityUnitOfWork
from backend.persistence.models import (
    CalendarEvent,
    CalendarFeedLifecycle,
    Committee,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamSlot,
)
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class CalendarServiceTests(unittest.TestCase):
    def _scope(self, db_path):
        authentication = SQLiteAuthenticationRepository(db_path)
        credentials = authentication.create_session(1)
        context = authentication.authenticate(credentials.token)
        assert context is not None
        scope = authorization_service(db_path).scope(context)
        return CalendarScope(person_id=scope.person_id, member_ids=frozenset(scope.member_ids))

    def _confirmed_database(self):
        database = TempDatabase()
        db_path = database.__enter__()
        planning_service(db_path).generate_proposal(1)
        planning_service(db_path).confirm_plan(1)
        return database, db_path

    def test_activation_is_opaque_and_repeated_sync_is_idempotent(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            events = service.list_events(scope)
            with connect(db_path) as connection:
                (token_hash,) = connection.execute(
                    text("SELECT token_hash FROM calendar_feed WHERE person_id = 1")
                ).one()

            token = activation.token
            self.assertNotEqual(token, token_hash)
            self.assertEqual(64, len(token_hash))
            self.assertGreater(len(events), 0)
            before = {event.id: event for event in events}

            self.assertEqual(0, service.sync_person(scope.person_id))
            after = {event.id: event for event in service.list_events(scope)}
            self.assertEqual(
                {event_id: event.version for event_id, event in before.items()},
                {event_id: event.version for event_id, event in after.items()},
            )
        finally:
            database.__exit__(None, None, None)

    def test_activation_pending_survives_sync_error_and_explicit_retry(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            with patch.object(service, "sync_person", side_effect=RuntimeError("sync failed")):
                with self.assertRaisesRegex(RuntimeError, "sync failed"):
                    service.activate(scope)
            pending = service._feed_for_person(scope.person_id)
            self.assertIsNotNone(pending)
            self.assertIsNone(pending.token_hash)
            self.assertIsNotNone(pending.pending_generation)
            self.assertFalse(service.status(scope).active)

            activation = service.activate(scope)
            self.assertTrue(service.status(scope).active)
            self.assertEqual(
                1,
                service._feed_for_person(scope.person_id).generation,
            )
            self.assertIsNotNone(service.feed_ics(activation.token))
        finally:
            database.__exit__(None, None, None)

    def test_parallel_activation_refresh_and_finalization_do_not_deadlock(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            coordinator = service._feed_coordinator
            original_lifecycle = coordinator.lifecycle
            original_run_sync = coordinator.run_sync
            original_serialized_commit = coordinator.serialized_commit
            second_sync_entered = Event()
            allow_second_sync = Event()
            first_sync_finished = Event()
            allow_first_finalize = Event()
            first_finalizer_waiting = Event()
            second_refresh_lifecycle_entered = Event()
            second_inside_refresh = Event()
            results = []
            errors = []

            @contextmanager
            def observed_lifecycle(database_id, person_id):
                if current_thread().name == "second-activation" and second_inside_refresh.is_set():
                    second_refresh_lifecycle_entered.set()
                with original_lifecycle(database_id, person_id) as state:
                    yield state

            def observed_run_sync(database_id, person_id, key, operation, **kwargs):
                if current_thread().name == "second-activation":
                    original_operation = operation

                    def paused_operation(state, cancellation):
                        second_sync_entered.set()
                        if not allow_second_sync.wait(timeout=5):
                            raise TimeoutError("Second activation sync was not released")
                        second_inside_refresh.set()
                        try:
                            return original_operation(state, cancellation)
                        finally:
                            second_inside_refresh.clear()

                    operation = paused_operation
                result = original_run_sync(database_id, person_id, key, operation, **kwargs)
                if current_thread().name == "first-activation":
                    first_sync_finished.set()
                    if not allow_first_finalize.wait(timeout=5):
                        raise TimeoutError("First activation finalizer was not released")
                return result

            def observed_serialized_commit(database_id, person_id):
                if current_thread().name == "first-activation":
                    first_finalizer_waiting.set()
                return original_serialized_commit(database_id, person_id)

            def activate():
                try:
                    results.append(service.activate(scope))
                except BaseException as error:
                    errors.append(error)

            with (
                patch.object(coordinator, "lifecycle", observed_lifecycle),
                patch.object(coordinator, "run_sync", observed_run_sync),
                patch.object(coordinator, "serialized_commit", observed_serialized_commit),
            ):
                first = Thread(target=activate, name="first-activation", daemon=True)
                second = Thread(target=activate, name="second-activation", daemon=True)
                first.start()
                self.assertTrue(first_sync_finished.wait(timeout=5), repr(errors))
                second.start()
                self.assertTrue(second_sync_entered.wait(timeout=5), repr(errors))
                allow_first_finalize.set()
                self.assertTrue(first_finalizer_waiting.wait(timeout=5), repr(errors))
                allow_second_sync.set()
                first.join(timeout=5)
                second.join(timeout=5)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(1, len(results))
            self.assertEqual(1, len(errors))
            self.assertIsInstance(errors[0], FeedConflictError)
            self.assertFalse(second_refresh_lifecycle_entered.is_set())
        finally:
            database.__exit__(None, None, None)

    def test_rotation_error_keeps_old_token_revoked_and_retryable(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            original = service.activate(scope)
            original_generation = service._feed_for_person(scope.person_id).generation
            with patch.object(service, "sync_person", side_effect=RuntimeError("sync failed")):
                with self.assertRaisesRegex(RuntimeError, "sync failed"):
                    service.activate(scope, rotate=True)
            self.assertIsNone(service.feed_ics(original.token))
            pending = service._feed_for_person(scope.person_id)
            self.assertIsNotNone(pending.pending_generation)
            self.assertGreater(pending.revocation_generation, 0)

            rotated = service.activate(scope, rotate=False)
            self.assertNotEqual(original.token, rotated.token)
            self.assertEqual(
                original_generation + 1,
                service._feed_for_person(scope.person_id).generation,
            )
            self.assertIsNone(service.feed_ics(original.token))
            self.assertIsNotNone(service.feed_ics(rotated.token))
        finally:
            database.__exit__(None, None, None)

    def test_feed_ics_discards_entire_result_when_identity_scope_changes(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            with session_scope(db_path) as session:
                original_membership = session.scalars(
                    select(CommitteeMember).where(CommitteeMember.person_id == 1)
                ).first()
                assert original_membership is not None
                second_committee = Committee(name="Calendar scope test", bootstrap_state="ready")
                session.add(second_committee)
                session.flush()
                second_membership = CommitteeMember(
                    person_id=1,
                    committee_id=second_committee.id,
                    member_status=original_membership.member_status,
                    committee_role=original_membership.committee_role,
                    representing_side=original_membership.representing_side,
                    is_active=1,
                )
                session.add(second_membership)
                session.flush()
                second_member_id = second_membership.id
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            original_scope = service._identity_scope(scope.person_id)
            original_member_id = next(
                member for member, _ in original_scope if member != second_member_id
            )
            changed_scope = original_scope - frozenset(
                pair for pair in original_scope if pair[0] == original_member_id
            )
            self.assertTrue(changed_scope)
            with patch.object(
                service,
                "_identity_scope",
                side_effect=(original_scope, original_scope, changed_scope),
            ):
                self.assertIsNone(service.feed_ics(activation.token))
        finally:
            database.__exit__(None, None, None)

    def test_feed_ics_discards_result_when_committee_is_deactivated_during_render(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            with session_scope(db_path) as session:
                member = session.get(CommitteeMember, next(iter(scope.member_ids)))
                assert member is not None
                committee_id = member.committee_id

            from backend.calendar.ics import render_calendar as render

            def deactivate_committee(events, title):
                with session_scope(db_path) as session:
                    committee = session.get(Committee, committee_id)
                    assert committee is not None
                    committee.is_active = 0
                return render(events, title)

            with patch(
                "backend.calendar.service.render_calendar", side_effect=deactivate_committee
            ):
                self.assertIsNone(service.feed_ics(activation.token))
        finally:
            database.__exit__(None, None, None)

    def test_membership_revocation_serializes_with_final_feed_validation(self) -> None:
        database, db_path = self._confirmed_database()
        self.addCleanup(database.__exit__, None, None, None)
        service = create_calendar_service(db_path)
        scope = self._scope(db_path)
        activation = service.activate(scope)
        member_id = next(iter(scope.member_ids))
        identities = identity_service(db_path)
        coordinator = service._identity_scope_coordinator
        original_guard = coordinator.guard
        guard_attempts = 0
        final_guard_attempted = Event()
        render_entered = Event()
        allow_render = Event()
        delete_entered = Event()
        allow_delete = Event()
        feed_finished = Event()
        delete_finished = Event()
        feed_result = []
        errors = []

        @contextmanager
        def observed_guard():
            nonlocal guard_attempts
            guard_attempts += 1
            if guard_attempts == 2:
                final_guard_attempted.set()
            with original_guard():
                yield

        from backend.calendar.ics import render_calendar as render

        def paused_render(events, title):
            render_entered.set()
            if not allow_render.wait(timeout=5):
                raise TimeoutError("Feed render was not released")
            return render(events, title)

        update = SQLiteIdentityUnitOfWork.update_membership

        def paused_update(work, current_member_id, values):
            delete_entered.set()
            if not allow_delete.wait(timeout=5):
                raise TimeoutError("Membership update was not released")
            return update(work, current_member_id, values)

        def download():
            try:
                feed_result.append(service.feed_ics(activation.token))
            except BaseException as error:
                errors.append(error)
            finally:
                feed_finished.set()

        def revoke_membership():
            try:
                identities.update_membership(member_id, {"is_active": False})
            except BaseException as error:
                errors.append(error)
            finally:
                delete_finished.set()

        with (
            patch.object(coordinator, "guard", observed_guard),
            patch("backend.calendar.service.render_calendar", side_effect=paused_render),
            patch.object(SQLiteIdentityUnitOfWork, "update_membership", paused_update),
        ):
            feed_thread = Thread(target=download)
            delete_thread = Thread(target=revoke_membership)
            feed_thread.start()
            self.assertTrue(render_entered.wait(timeout=3))
            delete_thread.start()
            self.assertTrue(delete_entered.wait(timeout=3))
            allow_render.set()
            self.assertTrue(final_guard_attempted.wait(timeout=3))
            self.assertFalse(feed_finished.is_set())
            allow_delete.set()
            feed_thread.join(timeout=5)
            delete_thread.join(timeout=5)

        self.assertFalse(feed_thread.is_alive())
        self.assertFalse(delete_thread.is_alive())
        self.assertTrue(delete_finished.is_set())
        self.assertEqual([], errors)
        self.assertEqual([None], feed_result)

    def test_parallel_feed_reads_share_one_sync(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            started = Event()
            release = Event()
            original = service.sync_person
            calls = 0

            def delayed_sync(person_id, **kwargs):
                nonlocal calls
                calls += 1
                started.set()
                self.assertTrue(release.wait(5))
                return original(person_id, **kwargs)

            results: list[str | None] = []
            with patch.object(service, "sync_person", side_effect=delayed_sync):
                first = Thread(target=lambda: results.append(service.feed_ics(activation.token)))
                second = Thread(target=lambda: results.append(service.feed_ics(activation.token)))
                first.start()
                self.assertTrue(started.wait(5))
                second.start()
                sleep(0.05)
                release.set()
                first.join(5)
                second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(1, calls)
            self.assertEqual(2, len(results))
            self.assertTrue(all(result is not None for result in results))
        finally:
            database.__exit__(None, None, None)

    def test_delete_fences_and_rolls_back_an_active_feed_refresh(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            with session_scope(db_path) as session:
                event = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert event is not None
                event_id = event.id
                original_version = event.version

            started = Event()
            release = Event()
            original_sync_round = service._sync_round

            def mutate_then_pause(work, snapshot, **kwargs):
                result = original_sync_round(work, snapshot, **kwargs)
                events = work.events_for_round(snapshot.id, person_id=scope.person_id)
                if events:
                    work.save_event(replace(events[0], version=events[0].version + 10))
                started.set()
                self.assertTrue(release.wait(5))
                return result

            read_results: list[str | None] = []
            errors: list[BaseException] = []

            def read_feed():
                try:
                    read_results.append(service.feed_ics(activation.token))
                except BaseException as error:
                    errors.append(error)

            with patch.object(service, "_sync_round", side_effect=mutate_then_pause):
                reader = Thread(target=read_feed)
                reader.start()
                self.assertTrue(started.wait(5))
                revoke_result: list[bool] = []
                revoker = Thread(target=lambda: revoke_result.append(service.revoke(scope)))
                revoker.start()
                deadline = monotonic() + 5
                while (
                    not service._feed_coordinator.is_fenced(service._database_id, scope.person_id)
                    and monotonic() < deadline
                ):
                    sleep(0.01)
                self.assertTrue(
                    service._feed_coordinator.is_fenced(service._database_id, scope.person_id)
                )
                release.set()
                reader.join(5)
                revoker.join(5)

            self.assertFalse(reader.is_alive())
            self.assertFalse(revoker.is_alive())
            self.assertEqual([], errors)
            self.assertEqual([True], revoke_result)
            self.assertEqual([None], read_results)
            with session_scope(db_path) as session:
                self.assertEqual(original_version, session.get(CalendarEvent, event_id).version)
        finally:
            database.__exit__(None, None, None)

    def test_failed_delete_commit_stays_fenced_until_retry(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            activation = service.activate(scope)
            with connect(db_path) as connection:
                connection.execute(text("""CREATE TRIGGER fail_feed_revocation
                    BEFORE UPDATE ON calendar_feed_lifecycle
                    BEGIN SELECT RAISE(ABORT, 'injected revocation failure'); END"""))
            with self.assertRaises(FeedRevocationPendingError):
                service.revoke(scope)
            self.assertTrue(
                service._feed_coordinator.is_fenced(service._database_id, scope.person_id)
            )
            with connect(db_path) as connection:
                connection.execute(text("DROP TRIGGER fail_feed_revocation"))
            listed = service.list_events(scope)
            self.assertTrue(listed)
            self.assertIsNotNone(service.event_ics(listed[0].id, scope))
            self.assertTrue(service.revoke(scope))
            self.assertFalse(
                service._feed_coordinator.is_fenced(service._database_id, scope.person_id)
            )
            self.assertIsNone(service.feed_ics(activation.token))
        finally:
            database.__exit__(None, None, None)

    def test_pending_rotation_can_resume_with_a_fresh_process_coordinator(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            original = service.activate(scope)
            with patch.object(service, "sync_person", side_effect=RuntimeError("sync failed")):
                with self.assertRaisesRegex(RuntimeError, "sync failed"):
                    service.activate(scope, rotate=True)

            restarted = create_calendar_service(db_path)
            restarted._feed_coordinator = CalendarFeedCoordinator()
            self.assertIsNone(restarted.feed_ics(original.token))
            resumed = restarted.activate(scope, rotate=False)
            self.assertNotEqual(original.token, resumed.token)
            self.assertIsNotNone(restarted.feed_ics(resumed.token))
        finally:
            database.__exit__(None, None, None)

    def test_lifecycle_migration_backfills_existing_credentials_and_is_repeatable(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            with connection_scope(db_path) as connection, connection.begin():
                connection.execute(
                    text("""INSERT INTO calendar_feed(person_id, token_hash, created_at)
                    VALUES (1, :token_hash, '2026-10-01T00:00:00Z')"""),
                    {"token_hash": "a" * 64},
                )
                connection.execute(text("DROP TABLE calendar_feed_lifecycle"))
                connection.execute(
                    text("DELETE FROM schema_migration_checksum WHERE name = :name"),
                    {"name": "030_calendar_feed_lifecycle.sql"},
                )
                connection.execute(
                    text("DELETE FROM schema_migration WHERE name = :name"),
                    {"name": "030_calendar_feed_lifecycle.sql"},
                )

            apply_migrations(db_path)
            with session_scope(db_path) as session:
                migrated = session.get(CalendarFeedLifecycle, 1)
                self.assertIsNotNone(migrated)
                self.assertEqual(1, migrated.generation)
                self.assertEqual(0, migrated.revocation_generation)
                self.assertIsNone(migrated.pending_generation)

            apply_migrations(db_path)
            with connection_scope(db_path) as connection:
                self.assertEqual(
                    1,
                    connection.execute(
                        text("""SELECT COUNT(*) FROM calendar_feed_lifecycle WHERE person_id = 1
                        AND generation = 1""")
                    ).scalar_one(),
                )
        finally:
            database.__exit__(None, None, None)

    def test_execution_origin_reservation_is_monotone_and_retryable(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            with session_scope(db_path) as session:
                assignment_id = session.scalars(select(ExamDayAssignment.id)).first()
            assert assignment_id is not None
            unit_of_work_factory = SQLiteCalendarPersistence(db_path)
            with unit_of_work_factory() as work:
                self.assertEqual(
                    "apply", work.reserve_execution_origin(assignment_id, "a", 2, "update")
                )
            with unit_of_work_factory() as work:
                self.assertEqual(
                    "apply", work.reserve_execution_origin(assignment_id, "a", 2, "update")
                )
            with unit_of_work_factory() as work:
                self.assertEqual(
                    "conflict", work.reserve_execution_origin(assignment_id, "b", 2, "update")
                )
            with unit_of_work_factory() as work:
                self.assertEqual(
                    "superseded", work.reserve_execution_origin(assignment_id, "c", 1, "update")
                )
            with unit_of_work_factory() as work:
                self.assertEqual(
                    "apply", work.reserve_execution_origin(assignment_id, "c", 3, "cancel")
                )
        finally:
            database.__exit__(None, None, None)

    def test_ics_uses_rfc5545_serialization_for_text_and_timezones(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
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
                expected_description = (
                    f"Rolle: {event.role}\nDetails: /api/confirmed-plan-days/{event.exam_day_id}"
                )
                expected_version = event.version
                ics = service._calendar(
                    [
                        CalendarEventSnapshot(
                            **{
                                field.name: getattr(event, field.name)
                                for field in fields(CalendarEventSnapshot)
                            }
                        )
                    ],
                    "Persönlicher Prüfungskalender",
                )

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

    def test_deleted_exam_day_does_not_leave_an_invalid_ics_detail_reference(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            with session_scope(db_path) as session:
                event = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert event is not None and event.exam_day_id is not None
                event_id = event.id
                day = session.get(ExamDay, event.exam_day_id)
                assert day is not None
                session.delete(day)

            ics = service.event_ics(event_id, scope)
            assert ics is not None
            component = Calendar.from_ical(ics).walk("VEVENT")[0]

            self.assertTrue(str(component["DESCRIPTION"]).startswith("Rolle: "))
            self.assertNotIn("/None", str(component["DESCRIPTION"]))
            self.assertNotIn("Details:", str(component["DESCRIPTION"]))
        finally:
            database.__exit__(None, None, None)

    def test_time_change_keeps_uid_and_increments_version(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            event = service.list_events(scope)[0]
            with session_scope(db_path) as session:
                calendar_event = session.get(CalendarEvent, event.id)
                assert calendar_event is not None
                slot = session.scalars(select(ExamSlot).order_by(ExamSlot.id)).first()
                assert slot is not None
                slot.starts_at = "2026-11-16 09:15:00"

            service.sync_round(1)
            changed = next(item for item in service.list_events(scope) if item.id == event.id)
            self.assertEqual(event.external_event_id, changed.external_event_id)
            self.assertEqual(event.version + 1, changed.version)
            self.assertEqual("updated", changed.status)
            service.sync_round(1)
            stable = next(item for item in service.list_events(scope) if item.id == event.id)
            self.assertEqual(changed.version, stable.version)
        finally:
            database.__exit__(None, None, None)

    def test_sync_preserves_existing_content_hashes_for_unchanged_events(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            service.sync_round(1)
            legacy_hash_fields = (
                "exam_half_year_id",
                "exam_round_id",
                "exam_day_id",
                "exam_day_assignment_id",
                "recipient_member_id",
                "date",
                "starts_at",
                "ends_at",
                "time_zone",
                "location",
                "role",
                "round_name",
                "secure_reference",
                "source_key",
                "status",
            )
            with session_scope(db_path) as session:
                event = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert event is not None
                legacy_payload = {field: getattr(event, field) for field in legacy_hash_fields}
                event.content_hash = hashlib.sha256(
                    repr(sorted(legacy_payload.items())).encode("utf-8")
                ).hexdigest()
                event_id = event.id
                version = event.version

            self.assertEqual(0, service.sync_round(1))

            with session_scope(db_path) as session:
                event = session.get(CalendarEvent, event_id)
                assert event is not None
                self.assertEqual(version, event.version)
                self.assertEqual("sent", event.status)
        finally:
            database.__exit__(None, None, None)

    def test_cancellation_is_kept_in_current_half_year_feed(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
            scope = self._scope(db_path)
            service.sync_round(1)
            event = service.list_events(scope)[0]
            with session_scope(db_path) as session:
                calendar_event = session.get(CalendarEvent, event.id)
                assert calendar_event is not None
                day = session.get(ExamDay, calendar_event.exam_day_id)
                assert day is not None
                day.status = "cancelled"

            service.sync_round(1)
            cancelled = next(item for item in service.list_events(scope) if item.id == event.id)
            self.assertEqual("cancelled", cancelled.status)
            self.assertEqual(event.external_event_id, cancelled.external_event_id)
        finally:
            database.__exit__(None, None, None)

    def test_partial_cancellation_updates_only_the_affected_day_part(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
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
            changed = next(item for item in service.list_events(scope) if item.id == event_id)
            self.assertEqual(before + 1, changed.version)
            self.assertEqual("updated", changed.status)
        finally:
            database.__exit__(None, None, None)

    def test_assignment_replacement_cancels_old_recipient_and_creates_new_uid(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = create_calendar_service(db_path)
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
                    select(CalendarEvent).where(
                        (CalendarEvent.source_key == source_key)
                        | CalendarEvent.source_key.like(f"{source_key}:%")
                    )
                ).all()
                self.assertEqual(2, len(events))
                old = next(item for item in events if item.id == original_id)
                new = next(item for item in events if item.id != original_id)
                self.assertEqual("cancelled", old.status)
                self.assertEqual("sent", new.status)
                self.assertNotEqual(old.external_event_id, new.external_event_id)
        finally:
            database.__exit__(None, None, None)

    def test_reactivated_assignment_gets_one_new_generation_without_touching_other_events(
        self,
    ) -> None:
        database, db_path = self._confirmed_database()
        self.addCleanup(database.__exit__, None, None, None)
        service = create_calendar_service(db_path)
        service.sync_round(1)
        with session_scope(db_path) as session:
            original = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
            assignment_id = original.exam_day_assignment_id
            old_id, old_uid = original.id, original.external_event_id
            day = session.get(ExamDay, original.exam_day_id)
            day_id = day.id
            day.status = "cancelled"
            untouched = {
                event.id: (event.status, event.version, event.content_hash)
                for event in session.scalars(select(CalendarEvent))
                if event.id != old_id
            }
        service.sync_assignment(assignment_id)
        with session_scope(db_path) as session:
            self.assertEqual("cancelled", session.get(CalendarEvent, old_id).status)
            session.get(ExamDay, day_id).status = "confirmed"
        service.sync_assignment(assignment_id)
        service.sync_assignment(assignment_id)
        with session_scope(db_path) as session:
            events = list(session.scalars(select(CalendarEvent)))
            generations = [e for e in events if e.exam_day_assignment_id == assignment_id]
            self.assertEqual(2, len(generations))
            new = next(e for e in generations if e.id != old_id)
            self.assertNotEqual(old_uid, new.external_event_id)
            self.assertEqual(("sent", 1), (new.status, new.version))
            self.assertEqual(
                untouched,
                {e.id: (e.status, e.version, e.content_hash) for e in events if e.id in untouched},
            )

    def test_round_sync_rolls_back_earlier_event_updates_on_payload_failure(self) -> None:
        database, db_path = self._confirmed_database()
        self.addCleanup(database.__exit__, None, None, None)
        service = create_calendar_service(db_path)
        service.sync_round(1)
        with session_scope(db_path) as session:
            before = {
                event.id: (event.status, event.version, event.content_hash)
                for event in session.scalars(select(CalendarEvent))
            }
            self.assertGreater(len(before), 1)
            for day in session.scalars(select(ExamDay).where(ExamDay.exam_round_id == 1)):
                day.status = "cancelled"
        real_payload = service._event_payload
        calls = 0

        def fail_after_first_event(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("synthetic payload failure")
            return real_payload(*args)

        with patch.object(service, "_event_payload", side_effect=fail_after_first_event):
            with self.assertRaisesRegex(ValueError, "synthetic payload failure"):
                service.sync_round(1)
        with session_scope(db_path) as session:
            self.assertEqual(
                before,
                {
                    e.id: (e.status, e.version, e.content_hash)
                    for e in session.scalars(select(CalendarEvent))
                },
            )
        self.assertGreater(service.sync_round(1), 0)
        self.assertEqual(0, service.sync_round(1))

    def test_generation_allocator_advances_past_gaps_without_reusing_origin(self) -> None:
        from types import SimpleNamespace

        events = (
            SimpleNamespace(source_key="assignment:17:1"),
            SimpleNamespace(source_key="assignment:17:4"),
            SimpleNamespace(source_key="assignment:170:9"),
            SimpleNamespace(source_key="assignment:17:legacy"),
        )

        self.assertEqual(5, CalendarService._next_generation("assignment:17", events))


class CalendarApiTests(unittest.TestCase):
    def test_authenticated_lifecycle_and_public_feed_are_personal(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            planning_service(db_path).generate_proposal(1)
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

    def test_revocation_storage_failure_has_stable_retryable_http_contract(self) -> None:
        with TempDatabase() as db_path:
            with patch.object(
                CalendarService,
                "revoke",
                side_effect=FeedRevocationPendingError("internal database detail"),
            ):
                with ApiServer(db_path) as api:
                    status, payload = api.request("DELETE", "/api/calendar/feed")

        self.assertEqual(503, status)
        self.assertEqual(
            {
                "error": {
                    "code": "calendar_feed_revocation_pending",
                    "message": "Calendar feed revocation is pending; retry the request.",
                }
            },
            payload,
        )

    def test_other_member_cannot_download_an_event(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            planning_service(db_path).generate_proposal(1)
            planning_service(db_path).confirm_plan(1)
            status, events = api.request("GET", "/api/calendar/events")
            assert_status(status, 200)
            event_id = events["items"][0]["id"]
            other_credentials = SQLiteAuthenticationRepository(db_path).create_session(2)
            status, _headers, _body = api.request_raw(
                "GET",
                f"/api/calendar/events/{event_id}.ics",
                credentials=other_credentials,
            )
            assert_status(status, 404)
