from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from backend.auth import AuthenticationRepository
from backend.calendar import CalendarService
from backend.database import session_scope
from backend.models import (
    CalendarEvent,
    CommitteeMember,
    ExamRoom,
    ExamVenue,
    MemberAvailability,
    Notification,
    PlanConsequence,
)
from backend.plan_consequences import PlanConsequenceService
from backend.planning import ConfirmedPlanChange, PlanningService
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class PlanConsequenceServiceTests(unittest.TestCase):
    @staticmethod
    def _create_active_room(session, *, name: str, street: str, room_name: str) -> int:
        venue = ExamVenue(
            scope="committee",
            committee_id=1,
            name=name,
            normalized_name=name.casefold(),
            street=street,
            postal_code="00000",
            city="Teststadt",
            country="Deutschland",
            is_accessible=1,
            accessibility_status="confirmed",
            is_active=0,
        )
        session.add(venue)
        session.flush()
        room = ExamRoom(
            venue_id=venue.id,
            name=room_name,
            normalized_name=room_name.casefold(),
            is_active=1,
        )
        session.add(room)
        session.flush()
        venue.is_active = 1
        session.flush()
        return room.id

    def _confirmed_plan(self, db_path):
        planning = PlanningService(db_path)
        planning.generate_proposal(1)
        planning.confirm_plan(1)
        CalendarService(db_path).sync_round(1)
        return planning, planning.get_confirmed_plan(1)

    def test_room_change_updates_stable_events_and_creates_one_notice_per_recipient(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            first_day = original.days[0]
            with session_scope(db_path) as session:
                room_id = self._create_active_room(
                    session,
                    name="Synthetischer Ausweichort",
                    street="Testweg 2",
                    room_name="2.01",
                )
                before_events = {
                    event.exam_day_assignment_id: (event.id, event.external_event_id, event.version)
                    for event in session.scalars(
                        select(CalendarEvent).where(CalendarEvent.exam_day_id == first_day.id)
                    )
                }
            changed = replace(
                original,
                days=(
                    replace(first_day, room_id=room_id),
                    *original.days[1:],
                ),
            )
            saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Synthetischen Raum wechseln"),
                actor_member_id=1,
            )

            service = PlanConsequenceService(db_path)
            first = service.process_revision(revision["id"])
            second = service.process_revision(revision["id"])

            with session_scope(db_path) as session:
                after_events = {
                    event.exam_day_assignment_id: (event.id, event.external_event_id, event.version)
                    for event in session.scalars(
                        select(CalendarEvent).where(CalendarEvent.exam_day_id == first_day.id)
                    )
                    if event.status != "cancelled"
                }
                notices = [
                    (notice.id, notice.recipient_member_id)
                    for notice in session.scalars(
                        select(Notification).where(Notification.event_type == "plan_changed")
                    ).all()
                ]
                consequence_count = len(session.scalars(select(PlanConsequence)).all())

        self.assertEqual(saved.revision, revision["resulting_revision"])
        self.assertEqual("succeeded", first["derivation_status"])
        self.assertEqual(first, second)
        self.assertEqual(set(before_events), set(after_events))
        for assignment_id, before in before_events.items():
            after = after_events[assignment_id]
            self.assertEqual(before[:2], after[:2])
            self.assertEqual(before[2] + 1, after[2])
        notice_recipients = {recipient_id for _notice_id, recipient_id in notices}
        self.assertNotIn(1, notice_recipients)
        self.assertEqual(
            len(notice_recipients),
            len(notices),
        )
        self.assertEqual(first["processed"], consequence_count)

    def test_non_calendar_reordering_derives_no_consequence(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            regular = [slot for slot in day.slots if slot.slot_type == "regular"]
            mep = [slot for slot in day.slots if slot.slot_type == "mep"]
            changed = replace(
                original,
                days=(
                    replace(day, slots=tuple([*reversed(regular), *mep])),
                    *original.days[1:],
                ),
            )
            _saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Reihenfolge korrigieren"),
                actor_member_id=1,
            )

            result = PlanConsequenceService(db_path).process_revision(revision["id"])

        self.assertEqual(0, result["processed"])
        self.assertEqual(0, result["problems"])

    def test_person_swap_cancels_old_event_and_creates_a_new_identity(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            target = day.assignments[0]
            assigned_members = {item.committee_member_id for item in day.assignments}
            with session_scope(db_path) as session:
                old_member = session.get(CommitteeMember, target.committee_member_id)
                assert old_member is not None
                replacement = session.scalars(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == old_member.committee_id,
                        CommitteeMember.representing_side == old_member.representing_side,
                        CommitteeMember.is_active == 1,
                        CommitteeMember.id.not_in(assigned_members),
                    )
                ).first()
                assert replacement is not None
                availability = session.scalars(
                    select(MemberAvailability).where(
                        MemberAvailability.candidate_exam_day_id == day.candidate_exam_day_id,
                        MemberAvailability.committee_member_id == replacement.id,
                    )
                ).first()
                assert availability is not None
                availability.availability = "full_day"
                availability.responded_at = "2026-01-01T00:00:00+00:00"
                old_event = session.scalars(
                    select(CalendarEvent).where(
                        CalendarEvent.exam_day_assignment_id == target.id,
                        CalendarEvent.recipient_member_id == target.committee_member_id,
                    )
                ).first()
                assert old_event is not None
                old_event_id = old_event.id
                old_external_id = old_event.external_event_id
                replacement_id = replacement.id

            changed_assignments = tuple(
                replace(item, committee_member_id=replacement_id) if item.id == target.id else item
                for item in day.assignments
            )
            changed = replace(
                original,
                days=(
                    replace(day, assignments=changed_assignments),
                    *original.days[1:],
                ),
            )
            _saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Synthetischen Personentausch abbilden"),
                actor_member_id=1,
            )

            PlanConsequenceService(db_path).process_revision(revision["id"])
            with session_scope(db_path) as session:
                old = session.get(CalendarEvent, old_event_id)
                new = session.scalars(
                    select(CalendarEvent).where(
                        CalendarEvent.exam_day_assignment_id == target.id,
                        CalendarEvent.recipient_member_id == replacement_id,
                    )
                ).first()
                assert old is not None
                assert new is not None
                old_status = old.status
                old_identity = old.external_event_id
                new_status = new.status
                new_identity = new.external_event_id

        self.assertEqual("cancelled", old_status)
        self.assertNotEqual("cancelled", new_status)
        self.assertEqual(old_external_id, old_identity)
        self.assertNotEqual(old_identity, new_identity)

    def test_calendar_failure_is_independent_and_a_retry_finishes_only_failed_effects(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            with session_scope(db_path) as session:
                room_id = self._create_active_room(
                    session,
                    name="Synthetischer Fehlerort",
                    street="Testweg 3",
                    room_name="3.01",
                )
            changed = replace(
                original,
                days=(replace(day, room_id=room_id), *original.days[1:]),
            )
            saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Unabhängige Fehlergrenze prüfen"),
                actor_member_id=1,
            )
            service = PlanConsequenceService(db_path)

            with patch.object(service.calendar, "sync_round", side_effect=OSError("offline")):
                failed = service.process_revision(revision["id"])
            retried = service.retry_revision(revision["id"])
            persisted = planning.get_confirmed_plan(1)

        self.assertEqual(saved, persisted)
        self.assertGreater(failed["processed"], 0)
        self.assertGreater(failed["problems"], 0)
        self.assertEqual(0, retried["problems"])
        self.assertGreater(retried["processed"], failed["processed"])

    def test_older_unsent_notices_are_superseded_by_the_latest_revision(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            with session_scope(db_path) as session:
                room_ids = []
                for index in (4, 5):
                    room_ids.append(
                        self._create_active_room(
                            session,
                            name=f"Synthetischer Revisionsort {index}",
                            street=f"Testweg {index}",
                            room_name=f"{index}.01",
                        )
                    )
            first_change = replace(
                original,
                days=(replace(day, room_id=room_ids[0]), *original.days[1:]),
            )
            _first_saved, first_revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(first_change, "Erste schnelle Änderung"),
                actor_member_id=1,
            )
            service = PlanConsequenceService(db_path)
            service_now = datetime.now(UTC)
            first = service.process_revision(first_revision["id"], now=service_now)
            current = planning.get_confirmed_plan(1)
            second_day = current.days[0]
            second_change = replace(
                current,
                days=(
                    replace(second_day, room_id=room_ids[1]),
                    *current.days[1:],
                ),
            )
            _second_saved, second_revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(second_change, "Zweite schnelle Änderung"),
                actor_member_id=1,
            )

            latest = service.process_revision(second_revision["id"], now=service_now)
            older = service.process_revision(first_revision["id"], now=service_now)

        self.assertEqual(0, first["problems"])
        self.assertEqual(0, latest["problems"])
        self.assertGreater(older["superseded"], 0)
        self.assertEqual(0, older["pending"])

    def test_non_calendar_revision_keeps_a_still_relevant_older_retry(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            with session_scope(db_path) as session:
                room_id = self._create_active_room(
                    session,
                    name="Synthetischer Zielort",
                    street="Testweg 6",
                    room_name="6.01",
                )
            changed = replace(
                original,
                days=(replace(day, room_id=room_id), *original.days[1:]),
            )
            _saved, first_revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Kalenderfolge zunächst verzögern"),
                actor_member_id=1,
            )
            service = PlanConsequenceService(db_path)
            with patch.object(service.calendar, "sync_round", side_effect=OSError("offline")):
                first = service.process_revision(first_revision["id"])

            current = planning.get_confirmed_plan(1)
            _saved, second_revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(current, "Nur Begründung ergänzen"),
                actor_member_id=1,
            )
            second = service.process_revision(second_revision["id"])
            retried = service.retry_revision(first_revision["id"])

            with session_scope(db_path) as session:
                active_locations = {
                    event.location
                    for event in session.scalars(
                        select(CalendarEvent).where(
                            CalendarEvent.exam_day_id == day.id,
                            CalendarEvent.status != "cancelled",
                        )
                    )
                }

        self.assertGreater(first["problems"], 0)
        self.assertEqual(0, second["processed"])
        self.assertEqual(0, retried["problems"])
        self.assertTrue(any("Synthetischer Zielort" in item for item in active_locations))

    def test_due_processing_reaches_a_permanent_failure_with_bounded_backoff(self) -> None:
        with TempDatabase() as db_path:
            planning, original = self._confirmed_plan(db_path)
            day = original.days[0]
            with session_scope(db_path) as session:
                room_id = self._create_active_room(
                    session,
                    name="Synthetischer Dauerfehlerort",
                    street="Testweg 7",
                    room_name="7.01",
                )
            changed = replace(
                original,
                days=(replace(day, room_id=room_id), *original.days[1:]),
            )
            _saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(changed, "Dauerfehler nachvollziehen"),
                actor_member_id=1,
            )
            service = PlanConsequenceService(db_path)
            started = datetime.now(UTC)
            with patch.object(service.calendar, "sync_round", side_effect=OSError("offline")):
                service.process_revision(revision["id"], now=started)
                service.process_due(now=started + timedelta(minutes=1))
                service.process_due(now=started + timedelta(minutes=3))
                service.process_due(now=started + timedelta(minutes=7))

            status = service.operator_status(revision["id"])

        failed = [
            item for item in status["technical_items"] if item["status"] == "permanently_failed"
        ]
        self.assertGreater(len(failed), 0)
        self.assertTrue(all(item["attempt_count"] == 4 for item in failed))
        self.assertTrue(all(item["error_code"] == "calendar_processing_failed" for item in failed))
        self.assertNotIn("Synthetischer Dauerfehlerort", str(status))


class PlanConsequenceApiTests(unittest.TestCase):
    def test_only_committee_management_can_inspect_and_restart_revision_effects(self) -> None:
        with TempDatabase() as db_path:
            planning = PlanningService(db_path)
            planning.generate_proposal(1)
            planning.confirm_plan(1)
            original = planning.get_confirmed_plan(1)
            _saved, revision = planning.save_confirmed_plan(
                ConfirmedPlanChange(original, "Technischen Wiederanlauf prüfen"),
                actor_member_id=1,
            )
            PlanConsequenceService(db_path).process_revision(revision["id"])
            authentication = AuthenticationRepository(db_path)
            examiner = authentication.create_session(2)
            deputy = authentication.create_session(3)

            with ApiServer(db_path) as api:
                path = "/api/exam-rounds/1/confirmed-plan/consequences"
                status, _chair_view = api.request("GET", path)
                assert_status(status, 200)
                status, _deputy_view = api.request("GET", path, credentials=deputy)
                assert_status(status, 200)
                status, _forbidden = api.request("GET", path, credentials=examiner)
                assert_status(status, 403)

                retry = (
                    "/api/exam-rounds/1/confirmed-plan/revisions/"
                    f"{revision['id']}/consequences/retry"
                )
                status, _retried = api.request("POST", retry, {}, credentials=deputy)
                assert_status(status, 200)
                status, _forbidden = api.request("POST", retry, {}, credentials=examiner)
                assert_status(status, 403)


if __name__ == "__main__":
    unittest.main()
