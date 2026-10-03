"""Ownership, nondisclosure, snapshots, and bounded visibility queries."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing, contextmanager
from dataclasses import replace
from threading import Event, Thread

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.application import ForbiddenRequestError
from backend.application.repositories import ResourceRepository
from backend.application.resource_access import ResourceKind, ResourceOwnership
from backend.application.resource_authorization import ResourceAuthorizer
from backend.composition import identity_service
from backend.identity.authorization import AuthorizationScope
from backend.persistence.database import session_scope
from backend.persistence.identity import SQLiteIdentityUnitOfWork
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_ATTENDANCE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    EXAM_VENUE,
    MEMBER_AVAILABILITY,
    MEMBER_EXAM_ATTENDANCE,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.persistence.resource_access import SQLiteResourceAccessQueryFactory
from backend.persistence.store import Store
from backend.tests.helpers import TempDatabase


@contextmanager
def database_activity():
    queries, sessions = [], []

    def query(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    def begin(session, _transaction, _connection):
        sessions.append(session)

    event.listen(Engine, "before_cursor_execute", query)
    event.listen(Session, "after_begin", begin)
    try:
        yield queries, sessions
    finally:
        event.remove(Engine, "before_cursor_execute", query)
        event.remove(Session, "after_begin", begin)


class ResourceAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = self.enterContext(TempDatabase())
        self.repository = ResourceRepository(self.db_path)
        self.identity = identity_service(self.db_path)
        self.scope = AuthorizationScope(
            1, frozenset({1}), frozenset({1}), frozenset({1}), frozenset({1}), {1: 1}
        )
        self.access_queries = SQLiteResourceAccessQueryFactory(self.db_path)
        self.authorizer = ResourceAuthorizer(self.access_queries, self.scope)
        with session_scope(self.db_path) as session:
            store = Store(session)
            self.foreign_committee = store.create(
                COMMITTEE,
                {"name": "Fremdausschuss", "occupation": "FI", "bootstrap_state": "ready"},
            )["id"]
            self.foreign_person = store.create(
                PERSON,
                {
                    "first_name": "Fremde",
                    "last_name": "Person",
                    "email": "foreign@demo.lzug.invalid",
                },
            )["id"]
            self.foreign_member = store.create(
                COMMITTEE_MEMBER,
                {
                    "committee_id": self.foreign_committee,
                    "person_id": self.foreign_person,
                    "member_status": "ordinary",
                    "committee_role": "chair",
                    "representing_side": "employer",
                    "is_active": 1,
                },
            )["id"]
            self.foreign_round = store.create(
                EXAM_ROUND,
                {
                    "committee_id": self.foreign_committee,
                    "exam_half_year_id": 1,
                    "name": "Fremde Runde",
                    "created_by_member_id": self.foreign_member,
                },
            )["id"]
        self.foreign_candidate = self.repository.create_candidate(
            {
                "first_name": "Fremder",
                "last_name": "Prüfling",
                "ihk_exam_number": "ACCESS-FOREIGN",
                "specialization": "application_development",
                "training_company": "Synthetisch",
                "exam_round_id": self.foreign_round,
            }
        )["id"]
        self.own = self.execution_rows(1, 1, 1)
        self.foreign = self.execution_rows(
            self.foreign_round, self.foreign_member, self.foreign_candidate
        )
        self.matrix = {
            COMMITTEE: (1, self.foreign_committee),
            PERSON: (1, self.foreign_person),
            COMMITTEE_MEMBER: (1, self.foreign_member),
            EXAM_ROUND: (1, self.foreign_round),
            CANDIDATE: (1, self.foreign_candidate),
            **{resource: (row_id, self.foreign[resource]) for resource, row_id in self.own.items()},
        }

    def execution_rows(self, round_id, member_id, candidate_id):
        with session_scope(self.db_path) as session:
            store = Store(session)
            candidate = store.first(
                ROUND_CANDIDATE, exam_round_id=round_id, candidate_id=candidate_id
            )
            responsibility = store.first(
                CANDIDATE_COMMITTEE_ASSIGNMENT, round_candidate_id=candidate["id"]
            )
            possible_day = store.create(
                CANDIDATE_EXAM_DAY, {"exam_round_id": round_id, "date": "2027-01-07"}
            )
            availability = store.create(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": round_id,
                    "committee_member_id": member_id,
                    "candidate_exam_day_id": possible_day["id"],
                },
            )
            day = store.create(
                EXAM_DAY, {"exam_round_id": round_id, "room_id": 1, "date": "2027-01-07"}
            )
            slot = store.create(
                EXAM_SLOT,
                {
                    "exam_day_id": day["id"],
                    "round_candidate_id": candidate["id"],
                    "slot_type": "regular",
                    "starts_at": "08:30",
                    "ends_at": "09:30",
                    "sequence_number": 1,
                },
            )
            assignment = store.create(
                EXAM_DAY_ASSIGNMENT,
                {
                    "exam_day_id": day["id"],
                    "committee_member_id": member_id,
                    "assignment_role": "examiner",
                    "day_part": "full_day",
                },
            )
            candidate_attendance = store.create(
                CANDIDATE_EXAM_ATTENDANCE, {"exam_slot_id": slot["id"]}
            )
            member_attendance = store.create(
                MEMBER_EXAM_ATTENDANCE, {"exam_day_id": day["id"], "committee_member_id": member_id}
            )
            settings = store.first(PLANNING_SETTINGS, exam_round_id=round_id)
            if settings is None:
                settings = store.create(
                    PLANNING_SETTINGS,
                    {
                        "exam_round_id": round_id,
                        "calendar_week_from": "2027-W01",
                        "calendar_week_to": "2027-W01",
                        "exams_per_day": 1,
                        "max_exam_days_per_week": 1,
                        "updated_by_member_id": member_id,
                    },
                )
            return {
                ROUND_CANDIDATE: candidate["id"],
                CANDIDATE_COMMITTEE_ASSIGNMENT: responsibility["id"],
                CANDIDATE_EXAM_DAY: possible_day["id"],
                MEMBER_AVAILABILITY: availability["id"],
                EXAM_DAY: day["id"],
                EXAM_SLOT: slot["id"],
                EXAM_DAY_ASSIGNMENT: assignment["id"],
                CANDIDATE_EXAM_ATTENDANCE: candidate_attendance["id"],
                MEMBER_EXAM_ATTENDANCE: member_attendance["id"],
                PLANNING_SETTINGS: settings["id"],
            }

    def test_lists_details_and_filters_preserve_every_resource_scope(self) -> None:
        for resource, (own_id, foreign_id) in self.matrix.items():
            with self.subTest(resource=resource.model.__tablename__):
                visible = self.repository.list_visible(resource, self.scope)
                ids = [row["id"] for row in visible]
                self.assertIn(own_id, ids)
                self.assertNotIn(foreign_id, ids)
                self.assertEqual(len(ids), len(set(ids)))
                if not resource.order_by:
                    self.assertEqual(sorted(ids), ids)
                self.assertEqual(
                    [row for row in visible if row["id"] == own_id],
                    self.repository.list_visible(resource, self.scope, {"id": own_id}),
                )
                self.assertEqual(
                    [], self.repository.list_visible(resource, self.scope, {"id": foreign_id})
                )
                self.assertEqual(
                    self.repository.get(resource, own_id),
                    self.repository.get_visible(resource, own_id, self.scope),
                )
                for hidden_id in (foreign_id, 999999):
                    self.assertIsNone(self.repository.get_visible(resource, hidden_id, self.scope))
        self.assertEqual([], self.repository.list_visible(EXAM_VENUE, self.scope))
        with self.assertRaisesRegex(ValueError, "Unknown field"):
            self.repository.list_visible(CANDIDATE, self.scope, {"unknown": 1})

    def test_empty_multi_committee_and_person_scopes(self) -> None:
        empty = AuthorizationScope(None, frozenset(), frozenset(), frozenset(), frozenset(), {})
        multi = replace(self.scope, committee_ids=frozenset({1, self.foreign_committee}))
        for resource in (*self.matrix, EXAM_HALF_YEAR):
            self.assertEqual([], self.repository.list_visible(resource, empty))
        self.assertEqual(
            self.repository.list(EXAM_HALF_YEAR),
            self.repository.list_visible(EXAM_HALF_YEAR, self.scope),
        )
        for resource, (_, foreign_id) in self.matrix.items():
            if resource == PERSON:
                self.assertIsNone(self.repository.get_visible(resource, foreign_id, multi))
            else:
                self.assertIsNotNone(self.repository.get_visible(resource, foreign_id, multi))

    def test_membership_write_rechecks_saved_actor_role_inside_write_uow(self) -> None:
        with session_scope(self.db_path) as session:
            Store(session).update(COMMITTEE_MEMBER, 1, {"committee_role": "member"})

        with self.assertRaises(PermissionError):
            self.identity.update_membership(
                2,
                {"member_status": "deputy"},
                actor_memberships=self.scope.member_by_committee,
            )

    def test_membership_write_rechecks_saved_actor_activity_inside_write_uow(self) -> None:
        with session_scope(self.db_path) as session:
            Store(session).update(COMMITTEE_MEMBER, 1, {"is_active": 0})

        with self.assertRaises(PermissionError):
            self.identity.update_membership(
                2,
                {"member_status": "deputy"},
                actor_memberships=self.scope.member_by_committee,
            )

    def test_history_inactive_members_and_mixed_availability_keep_distinct_rules(self) -> None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            store.update(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                self.own[CANDIDATE_COMMITTEE_ASSIGNMENT],
                {"ended_at": "2026-09-09"},
            )
            store.update(COMMITTEE_MEMBER, 2, {"is_active": 0})
            mixed = store.create(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": 1,
                    "committee_member_id": self.foreign_member,
                    "candidate_exam_day_id": self.own[CANDIDATE_EXAM_DAY],
                },
            )
        self.assertIsNone(self.repository.get_visible(CANDIDATE, 1, self.scope))
        for resource in (ROUND_CANDIDATE, CANDIDATE_COMMITTEE_ASSIGNMENT):
            self.assertIsNotNone(
                self.repository.get_visible(resource, self.own[resource], self.scope)
            )
        members = self.identity.members({}, self.scope)
        self.assertIn(2, [member["id"] for member in members])
        self.assertEqual(0, members[-1]["is_active"])
        self.assertIsNone(self.repository.get_visible(MEMBER_AVAILABILITY, mixed["id"], self.scope))

    def test_list_query_counts_do_not_grow_with_rows(self) -> None:
        def check_counts():
            sizes = {}
            for resource in self.matrix:
                with database_activity() as (queries, sessions):
                    rows = self.repository.list_visible(resource, self.scope)
                self.assertEqual(1, len(queries), resource.model.__tablename__)
                self.assertEqual(1, len(sessions))
                sizes[resource] = len(rows)
            for call, count in (
                (lambda: self.identity.members({}, self.scope), 2),
                (lambda: self.repository.candidate_list(self.scope), 1),
                (lambda: self.repository.candidate_committee_assignments(scope=self.scope), 1),
            ):
                with database_activity() as (queries, sessions):
                    call()
                self.assertEqual(count, len(queries))
                self.assertEqual(1, len(sessions))
            return sizes

        before = check_counts()
        for index in range(20):
            self.repository.create_candidate(
                {
                    "first_name": "Query",
                    "last_name": str(index),
                    "ihk_exam_number": f"QUERY-{index}",
                    "specialization": "system_integration",
                    "training_company": "Synthetisch",
                    "exam_round_id": 1,
                }
            )
            self.identity.create_membership(
                {
                    "first_name": "Query",
                    "last_name": str(index),
                    "email": f"query-{index}@demo.lzug.invalid",
                    "committee_id": 1,
                    "member_status": "ordinary",
                    "committee_role": "member",
                    "representing_side": "employer",
                },
                actor_memberships=self.scope.member_by_committee,
            )
        after = check_counts()
        for resource in (
            CANDIDATE,
            ROUND_CANDIDATE,
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            COMMITTEE_MEMBER,
        ):
            self.assertEqual(before[resource] + 20, after[resource])

    def test_ownership_and_authorization_never_open_nested_sessions(self) -> None:
        for resource, own_id in self.own.items():
            with self.subTest(resource=resource.model.__tablename__):
                with database_activity() as (_, sessions):
                    self.assertEqual(1, self.repository.committee_id_for_resource(resource, own_id))
                self.assertEqual(1, len(sessions))
                with database_activity() as (_, sessions):
                    self.assertEqual(1, self.repository.round_id_for_resource(resource, own_id))
                self.assertEqual(1, len(sessions))
                with database_activity() as (_, sessions):
                    self.authorizer.authorize(ResourceKind(resource.table), own_id, {})
                self.assertEqual(1, len(sessions))
        for call in (
            lambda: self.authorizer.require_round_access(1),
            lambda: self.authorizer.require_day_access(self.own[EXAM_DAY], member_id=1),
            lambda: self.authorizer.require_day_access(self.own[EXAM_DAY], manage=True),
            lambda: self.authorizer.authorize(ResourceKind.CANDIDATE, None, {"exam_round_id": 1}),
        ):
            with database_activity() as (_, sessions):
                call()
            self.assertEqual(1, len(sessions))

    def test_query_port_returns_typed_owner_values_and_materialized_projections(self) -> None:
        with self.access_queries.snapshot() as queries:
            owner = queries.ownership(ResourceKind.CANDIDATE_EXAM_DAY, self.own[CANDIDATE_EXAM_DAY])
            rows = queries.list_visible(ResourceKind.CANDIDATE_EXAM_DAY, self.scope)
            round_row = queries.ownership(ResourceKind.EXAM_ROUND, 1)
            half_year = queries.ownership(
                ResourceKind.EXAM_HALF_YEAR, round_row.references.exam_half_year_id
            )

        self.assertIsInstance(owner, ResourceOwnership)
        self.assertEqual((1, 1), (owner.committee_id, owner.round_id))
        self.assertTrue(owner.exists)
        self.assertIsNotNone(half_year.committee_id)
        self.assertIsNone(half_year.round_id)
        self.assertTrue(all(isinstance(row, dict) for row in rows))
        self.assertTrue(all(not hasattr(row, "_sa_instance_state") for row in rows))

    def test_resource_creation_ignores_client_actor_and_binds_session_member(self) -> None:
        result = self.authorizer.authorize(
            ResourceKind.EXAM_ROUND,
            None,
            {"committee_id": 1, "created_by_member_id": 999},
        )
        self.assertEqual(1, result["created_by_member_id"])

    def test_foreign_and_missing_owners_remain_forbidden_without_disclosure(self) -> None:
        for resource, (_, foreign_id) in self.matrix.items():
            for entity_id in (foreign_id, 999999):
                with self.subTest(resource=resource.model.__tablename__, entity_id=entity_id):
                    with self.assertRaisesRegex(ForbiddenRequestError, "^Forbidden\\.$"):
                        self.authorizer.authorize(ResourceKind(resource.table), entity_id, {})
        with self.assertRaises(ForbiddenRequestError):
            self.authorizer.authorize(ResourceKind.EXAM_HALF_YEAR, 1, {})
        for resource in (EXAM_DAY, EXAM_SLOT, CANDIDATE_EXAM_ATTENDANCE, CANDIDATE):
            self.assertIsNone(self.repository.committee_id_for_resource(resource))
            self.assertIsNone(self.repository.round_id_for_resource(resource))

    def test_updates_authorize_stored_source_before_payload_target(self) -> None:
        foreign_member_before = self.repository.get(COMMITTEE_MEMBER, self.foreign_member)
        with self.assertRaisesRegex(ForbiddenRequestError, "^Forbidden\\.$"):
            self.authorizer.authorize(
                ResourceKind.COMMITTEE_MEMBER,
                self.foreign_member,
                {"committee_id": 1, "person_id": 1},
            )
        self.assertEqual(
            foreign_member_before,
            self.repository.get(COMMITTEE_MEMBER, self.foreign_member),
        )
        with self.assertRaisesRegex(ForbiddenRequestError, "^Forbidden\\.$"):
            self.authorizer.authorize(
                ResourceKind.CANDIDATE,
                self.foreign_candidate,
                {"exam_round_id": 1},
            )

    def test_write_unit_rechecks_the_source_after_route_authorization(self) -> None:
        payload = self.authorizer.authorize(
            ResourceKind.COMMITTEE_MEMBER,
            1,
            {"member_status": "ordinary"},
        )
        moved_committee = self.repository.create(
            COMMITTEE,
            {"name": "Zwischenzuständigkeit", "occupation": "FI", "bootstrap_state": "ready"},
        )["id"]
        with session_scope(self.db_path) as session:
            Store(session).update(COMMITTEE_MEMBER, 1, {"committee_id": moved_committee})

        with database_activity() as (_, sessions):
            with self.assertRaisesRegex(PermissionError, "^Forbidden\\.$"):
                self.identity.update_membership(
                    1, payload, actor_memberships=self.scope.member_by_committee
                )
        self.assertEqual(1, len(sessions))

    def test_write_recheck_serializes_ownership_reads_with_mutation(self) -> None:
        destination_committee = self.repository.create(
            COMMITTEE,
            {"name": "Weiteres Komitee", "occupation": "FI", "bootstrap_state": "ready"},
        )["id"]
        authorization_complete = Event()
        allow_mutation = Event()
        writer_attempted_update = Event()
        writer_finished = Event()
        errors: list[BaseException] = []
        original_authorize = SQLiteIdentityUnitOfWork.require_membership_manager

        def track_competing_update(_connection, _cursor, statement, _parameters, _context, _many):
            if "update committee_member" in statement.lower():
                writer_attempted_update.set()

        def pause_after_authorization(unit_of_work, member_id, payload, actor_memberships):
            result = original_authorize(unit_of_work, member_id, payload, actor_memberships)
            authorization_complete.set()
            if not allow_mutation.wait(5):
                raise TimeoutError("timed out waiting to finish the authorized mutation")
            return result

        SQLiteIdentityUnitOfWork.require_membership_manager = pause_after_authorization

        def update_membership() -> None:
            try:
                self.identity.update_membership(
                    1,
                    {"member_status": "ordinary"},
                    actor_memberships=self.scope.member_by_committee,
                )
            except BaseException as error:
                errors.append(error)

        def move_membership() -> None:
            try:
                with session_scope(self.db_path) as session:
                    Store(session).update(
                        COMMITTEE_MEMBER, 1, {"committee_id": destination_committee}
                    )
            except BaseException as error:
                errors.append(error)
            finally:
                writer_finished.set()

        mutation = Thread(target=update_membership)
        move = Thread(target=move_membership)
        event.listen(Engine, "before_cursor_execute", track_competing_update)
        try:
            mutation.start()
            self.assertTrue(authorization_complete.wait(5))
            move.start()
            self.assertTrue(writer_attempted_update.wait(5))
            self.assertFalse(
                writer_finished.wait(0.2),
                "a competing ownership write committed after authorization but before mutation",
            )
        finally:
            allow_mutation.set()
            mutation.join(5)
            move.join(5)
            event.remove(Engine, "before_cursor_execute", track_competing_update)
            SQLiteIdentityUnitOfWork.require_membership_manager = original_authorize

        self.assertFalse(mutation.is_alive())
        self.assertFalse(move.is_alive())
        self.assertEqual([], errors)
        member = self.repository.get(COMMITTEE_MEMBER, 1)
        self.assertEqual(destination_committee, member["committee_id"])
        self.assertEqual("ordinary", member["member_status"])

    def test_allowed_candidate_round_change_checks_target_scope(self) -> None:
        with self.assertRaisesRegex(ForbiddenRequestError, "^Forbidden\\.$"):
            self.authorizer.authorize(
                ResourceKind.CANDIDATE,
                1,
                {"exam_round_id": self.foreign_round},
            )

    def test_availability_binds_actor_and_preserves_existing_owner(self) -> None:
        member_scope = replace(self.scope, management_committee_ids=frozenset())
        member = ResourceAuthorizer(self.access_queries, member_scope)
        payload = {
            "exam_round_id": 1,
            "committee_member_id": self.foreign_member,
            "created_by_member_id": 999,
        }
        result = member.authorize(ResourceKind.MEMBER_AVAILABILITY, None, payload)
        self.assertEqual({"exam_round_id": 1, "committee_member_id": 1}, result)
        self.assertEqual(999, payload["created_by_member_id"])
        result = member.authorize(
            ResourceKind.MEMBER_AVAILABILITY,
            self.own[MEMBER_AVAILABILITY],
            {"exam_round_id": self.foreign_round, "committee_member_id": self.foreign_member},
        )
        self.assertEqual(1, result["exam_round_id"])
        self.assertEqual(1, result["committee_member_id"])
        self.assertEqual(self.own[CANDIDATE_EXAM_DAY], result["candidate_exam_day_id"])
        with self.assertRaises(ForbiddenRequestError):
            self.authorizer.authorize(ResourceKind.MEMBER_AVAILABILITY, None, payload)
        with session_scope(self.db_path) as session:
            Store(session).update(COMMITTEE_MEMBER, 1, {"is_active": 0})
        with self.assertRaises(ForbiddenRequestError):
            member.authorize(ResourceKind.MEMBER_AVAILABILITY, self.own[MEMBER_AVAILABILITY], {})

    def test_owner_reads_use_one_snapshot_during_a_concurrent_commit(self) -> None:
        target_committee = self.repository.create(
            COMMITTEE, {"name": "Neue Zuständigkeit", "occupation": "FI"}
        )["id"]
        changed = False

        def move_round(_connection, _cursor, statement, _parameters, _context, _executemany):
            nonlocal changed
            if not changed and "FROM candidate_exam_day" in statement:
                changed = True
                with closing(sqlite3.connect(self.db_path)) as writer, writer:
                    writer.execute(
                        "UPDATE exam_round SET committee_id = ? WHERE id = 1",
                        (target_committee,),
                    )

        event.listen(Engine, "after_cursor_execute", move_round)
        try:
            self.assertEqual(
                1,
                self.repository.committee_id_for_resource(
                    CANDIDATE_EXAM_DAY, self.own[CANDIDATE_EXAM_DAY]
                ),
            )
        finally:
            event.remove(Engine, "after_cursor_execute", move_round)
        self.assertTrue(changed)
        self.assertEqual(
            target_committee,
            self.repository.committee_id_for_resource(
                CANDIDATE_EXAM_DAY, self.own[CANDIDATE_EXAM_DAY]
            ),
        )
        with self.assertRaises(ForbiddenRequestError):
            self.authorizer.require_round_access(1)
