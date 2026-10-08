"""Resource-oriented persistence operations and business validation boundaries."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.application.resource_access import (
    ResourceAccessQueryFactory,
    ResourceKind,
    reference_changes,
)
from backend.identity.authorization import AuthorizationScope
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
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
    EXAM_ROOM,
    EXAM_ROUND,
    EXAM_SLOT,
    EXAM_VENUE,
    MEMBER_AVAILABILITY,
    MEMBER_EXAM_ATTENDANCE,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Resource,
)
from backend.persistence.resource_access import SQLiteResourceAccessQueryFactory
from backend.persistence.store import Store

EXECUTION_STATUS_SUMMARY_KEYS = (
    "open",
    "running",
    "completed",
    "cancelled",
    "needs_follow_up",
)
PLAN_AGGREGATE_RESOURCES = {EXAM_DAY, EXAM_SLOT, EXAM_DAY_ASSIGNMENT}
PLAN_AGGREGATE_STATUSES = {"plan_proposed", "plan_confirmed"}
PLAN_AGGREGATE_WRITE_ERROR = (
    "Exam days, slots, and assignments must be changed through the planning aggregate"
)
PLANNING_RESOURCE_WRITE_ERROR = "Planning resources must be changed through Planning services"
PLANNING_RESOURCE_WRITES = frozenset(
    {
        EXAM_HALF_YEAR,
        EXAM_ROUND,
        ROUND_CANDIDATE,
        CANDIDATE,
        CANDIDATE_COMMITTEE_ASSIGNMENT,
        PLANNING_SETTINGS,
        MEMBER_AVAILABILITY,
    }
)


class ResourceRepository:
    """Expose CRUD operations while applying resource-specific domain rules.

    One repository call creates one :func:`session_scope`; the method either
    completes and commits all of its related writes or rolls them back. Generic
    ``Store`` operations remain deliberately unaware of person memberships,
    candidate records, and cross-committee assignment conflicts.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        access_queries: ResourceAccessQueryFactory | None = None,
    ):
        self.db_path = db_path
        self.access_queries = access_queries or SQLiteResourceAccessQueryFactory(db_path)

    def _authorize_mutation(
        self,
        store: Store,
        resource: Resource,
        resource_id: int | None,
        payload: dict[str, Any],
        scope: AuthorizationScope | None,
    ) -> dict[str, Any]:
        """Recheck mutable ownership inside the write transaction when scoped."""
        if scope is None:
            return payload
        from backend.application.resource_authorization import ResourceAuthorizer

        authorizer = ResourceAuthorizer(self.access_queries, scope)
        return authorizer.authorize_with_queries(
            self.access_queries.for_transaction(store),
            ResourceKind(resource.table),
            resource_id,
            payload,
        )

    def _authorization_session_scope(
        self, scope: AuthorizationScope | None
    ) -> AbstractContextManager[Session]:
        return session_scope(self.db_path, begin_immediate=scope is not None)

    def list(self, resource: Resource) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            return Store(session).all(resource)

    def list_filtered(
        self,
        resource: Resource,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            return Store(session).where(resource, **filters)

    def list_visible(
        self,
        resource: Resource,
        scope: AuthorizationScope,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return only rows belonging to an active committee in ``scope``."""
        with self.access_queries.snapshot() as queries:
            return [
                dict(row)
                for row in queries.list_visible(ResourceKind(resource.table), scope, filters or {})
            ]

    def get(self, resource: Resource, resource_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            return Store(session).get(resource, resource_id)

    def get_visible(
        self,
        resource: Resource,
        resource_id: int,
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        with self.access_queries.snapshot() as queries:
            row = queries.get_visible(ResourceKind(resource.table), resource_id, scope)
            return dict(row) if row is not None else None

    def round_id_for_resource(
        self,
        resource: Resource,
        resource_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """Resolve the owning exam round for authorization, never for response data."""
        with self.access_queries.snapshot() as queries:
            return queries.ownership(
                ResourceKind(resource.table), resource_id, reference_changes(payload or {})
            ).round_id

    def committee_id_for_resource(
        self,
        resource: Resource,
        resource_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """Resolve the owning committee for authorization-only decisions."""
        with self.access_queries.snapshot() as queries:
            return queries.ownership(
                ResourceKind(resource.table), resource_id, reference_changes(payload or {})
            ).committee_id

    def create(
        self,
        resource: Resource,
        payload: dict[str, Any],
        *,
        authorization_scope: AuthorizationScope | None = None,
    ) -> dict[str, Any]:
        """Create a resource after applying its domain-specific write rules.

        Identity resources are intentionally excluded from this generic write
        boundary. Assignment conflicts are rejected before a row is written.

        Raises:
            ValueError: If the payload violates a resource invariant or names
                an unknown field.
        """
        with self._authorization_session_scope(authorization_scope) as session:
            store = Store(session)
            if resource in {COMMITTEE, PERSON, COMMITTEE_MEMBER}:
                raise ValueError("Identity resources must be changed through Identity services")
            payload = self._authorize_mutation(store, resource, None, payload, authorization_scope)
            if resource in PLANNING_RESOURCE_WRITES:
                raise ValueError(PLANNING_RESOURCE_WRITE_ERROR)
            if resource in PLAN_AGGREGATE_RESOURCES:
                raise ValueError(PLAN_AGGREGATE_WRITE_ERROR)
            if resource == EXAM_DAY_ASSIGNMENT:
                self._validate_assignment_conflict(store, payload)
            return store.create(resource, payload)

    def update(
        self,
        resource: Resource,
        resource_id: int,
        payload: dict[str, Any],
        *,
        authorization_scope: AuthorizationScope | None = None,
    ) -> dict[str, Any] | None:
        """Update a resource and return ``None`` only when it does not exist.

        Assignment writes reuse the same validation as creation. In particular,
        an assignment update cannot bypass person-wide conflict checks by
        changing only one of its fields.
        """
        with self._authorization_session_scope(authorization_scope) as session:
            store = Store(session)
            if resource in {COMMITTEE, PERSON, COMMITTEE_MEMBER}:
                raise ValueError("Identity resources must be changed through Identity services")
            payload = self._authorize_mutation(
                store, resource, resource_id, payload, authorization_scope
            )
            if resource in PLANNING_RESOURCE_WRITES:
                raise ValueError(PLANNING_RESOURCE_WRITE_ERROR)
            if resource in PLAN_AGGREGATE_RESOURCES:
                raise ValueError(PLAN_AGGREGATE_WRITE_ERROR)
            if resource == EXAM_DAY_ASSIGNMENT:
                existing = store.get(resource, resource_id)
                if existing is None:
                    return None
                self._validate_assignment_conflict(store, {**existing, **payload}, resource_id)
            return store.update(resource, resource_id, payload)

    def _validate_assignment_conflict(
        self,
        store: Store,
        payload: dict[str, Any],
        assignment_id: int | None = None,
    ) -> None:
        member = store.get(COMMITTEE_MEMBER, payload["committee_member_id"])
        target_day = store.get(EXAM_DAY, payload["exam_day_id"])
        if member is None or target_day is None:
            raise ValueError("Assignment member or exam day not found")
        target_round = store.get(EXAM_ROUND, target_day["exam_round_id"])
        if target_round is None:
            raise ValueError("Assignment exam round not found")
        target_part = payload.get("day_part", "full_day")
        for assignment in store.all(EXAM_DAY_ASSIGNMENT):
            if assignment_id is not None and assignment["id"] == assignment_id:
                continue
            other_member = store.get(COMMITTEE_MEMBER, assignment["committee_member_id"])
            other_day = store.get(EXAM_DAY, assignment["exam_day_id"])
            if other_member is None or other_day is None:
                continue
            if (
                other_member["person_id"] != member["person_id"]
                or other_day["date"] != target_day["date"]
            ):
                continue
            if other_day["exam_round_id"] == target_day["exam_round_id"]:
                continue
            other_round = store.get(EXAM_ROUND, other_day["exam_round_id"])
            if (
                other_round is None
                or other_round["exam_half_year_id"] != target_round["exam_half_year_id"]
            ):
                continue
            if (
                target_part == "full_day"
                or assignment["day_part"] == "full_day"
                or assignment["day_part"] == target_part
            ):
                other_committee = (
                    store.get(COMMITTEE, other_round["committee_id"]) if other_round else None
                )
                raise ValueError(
                    "Person is already assigned in "
                    f"{other_committee['name'] if other_committee else 'another committee'} "
                    f"on {other_day['date']} ({assignment['day_part']})"
                )

    def delete(
        self,
        resource: Resource,
        resource_id: int,
        *,
        authorization_scope: AuthorizationScope | None = None,
    ) -> bool:
        with self._authorization_session_scope(authorization_scope) as session:
            store = Store(session)
            if resource in {COMMITTEE, PERSON, COMMITTEE_MEMBER}:
                raise ValueError("Identity resources must be changed through Identity services")
            self._authorize_mutation(store, resource, resource_id, {}, authorization_scope)
            if resource in PLANNING_RESOURCE_WRITES:
                raise ValueError(PLANNING_RESOURCE_WRITE_ERROR)
            if resource in PLAN_AGGREGATE_RESOURCES:
                raise ValueError(PLAN_AGGREGATE_WRITE_ERROR)
            return store.delete(resource, resource_id)

    def scheduling_overview(self, scope: AuthorizationScope | None = None) -> list[dict[str, Any]]:
        """Return only active planning work, enriched for the overview.

        The detail links still point to the canonical exam-round resource.  This
        read model deliberately leaves day and slot data out: proposed plans
        must not leak into the confirmed exam-plan view.
        """
        groups = {
            "draft": "draft",
            "availability_requested": "coordination",
            "availability_closed": "coordination",
            "plan_proposed": "planning",
            "in_progress": "planning",
            "plan_confirmed": "confirmed",
        }
        with session_scope(self.db_path) as session:
            store = Store(session)
            half_years = {half_year["id"]: half_year for half_year in store.all(EXAM_HALF_YEAR)}
            committees = {committee["id"]: committee["name"] for committee in store.all(COMMITTEE)}
            settings_by_round = {
                settings["exam_round_id"]: settings for settings in store.all(PLANNING_SETTINGS)
            }
            overview = []
            for exam_round in store.all(EXAM_ROUND):
                if scope is not None and not self._round_visible(store, exam_round, scope):
                    continue
                status_group = groups.get(exam_round["status"])
                if status_group is None:
                    continue
                half_year = half_years.get(exam_round["exam_half_year_id"])
                committee_name = committees.get(exam_round["committee_id"], "Unbekannter Ausschuss")
                settings = settings_by_round.get(exam_round["id"])
                overview.append(
                    {
                        "id": exam_round["id"],
                        "name": exam_round["name"],
                        "status": exam_round["status"],
                        "status_group": status_group,
                        "committee_name": committee_name,
                        "exam_half_year": half_year,
                        "calendar_week_from": (
                            settings["calendar_week_from"] if settings else None
                        ),
                        "calendar_week_to": (settings["calendar_week_to"] if settings else None),
                        "can_continue": status_group != "confirmed",
                    }
                )
            return sorted(
                overview,
                key=lambda item: (item["status_group"], item["name"], item["id"]),
            )

    def confirmed_plans(self, scope: AuthorizationScope | None = None) -> list[dict[str, Any]]:
        """Return the published calendar read model, excluding every proposal.

        This deliberately performs the state check at the server boundary.  A
        client cannot obtain draft or proposed appointments by merely hiding a
        tab in the UI.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            context = self._confirmed_plan_context(store)
            plans = []
            for exam_round in store.where(EXAM_ROUND, status="plan_confirmed"):
                if scope is not None and not self._round_visible(store, exam_round, scope):
                    continue
                committee = context["committees"].get(exam_round["committee_id"])
                if committee is None:
                    continue
                plans.append(self._confirmed_plan_view(store, exam_round, committee, context))
            return sorted(
                plans, key=lambda plan: (plan["committee"]["name"], plan["name"], plan["id"])
            )

    def _confirmed_plan_context(self, store: Store) -> dict[str, dict[int, dict[str, Any]]]:
        return {
            "committees": {row["id"]: row for row in store.all(COMMITTEE)},
            "half_years": {row["id"]: row for row in store.all(EXAM_HALF_YEAR)},
            "rooms": {row["id"]: row for row in store.all(EXAM_ROOM)},
            "venues": {row["id"]: row for row in store.all(EXAM_VENUE)},
            "candidates": {row["id"]: row for row in store.all(CANDIDATE)},
            "round_candidates": {row["id"]: row for row in store.all(ROUND_CANDIDATE)},
            "members": {
                row["id"]: self._member_projection(store, row)
                for row in store.all(COMMITTEE_MEMBER)
            },
        }

    @staticmethod
    def _member_projection(store: Store, membership: dict[str, Any]) -> dict[str, Any]:
        person = store.get(PERSON, membership["person_id"])
        if person is None:
            raise ValueError("Membership person not found")
        return {
            **membership,
            **{key: person[key] for key in ("first_name", "last_name", "email", "mobile")},
            "email_verified_at": None,
        }

    def _confirmed_plan_view(
        self,
        store: Store,
        exam_round: dict[str, Any],
        committee: dict[str, Any],
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> dict[str, Any]:
        return {
            "id": exam_round["id"],
            "name": exam_round["name"],
            "committee": {"id": committee["id"], "name": committee["name"]},
            "exam_half_year": context["half_years"].get(exam_round["exam_half_year_id"]),
            "days": self._confirmed_plan_days(store, exam_round["id"], context),
        }

    def _confirmed_plan_days(
        self,
        store: Store,
        exam_round_id: int,
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        days = []
        exam_days = sorted(
            store.where(EXAM_DAY, exam_round_id=exam_round_id),
            key=lambda row: (row["date"], row["id"]),
        )
        for exam_day in exam_days:
            if exam_day["status"] in {"confirmed", "completed", "cancelled"}:
                days.append(self._confirmed_day_view(store, exam_day, context))
        return days

    def _confirmed_day_view(
        self,
        store: Store,
        exam_day: dict[str, Any],
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> dict[str, Any]:
        slots = self._confirmed_day_slots(store, exam_day["id"], context)
        room = context["rooms"].get(exam_day["room_id"])
        return {
            "id": exam_day["id"],
            "date": exam_day["date"],
            "revision": exam_day["revision"],
            "closure_status": exam_day["closure_status"],
            "location": self._confirmed_day_location(room, context["venues"]),
            "room_id": room["id"] if room else None,
            "slots": slots,
            "assignments": self._confirmed_day_assignments(store, exam_day["id"], context),
            "status_summary": self._execution_status_summary(slots),
        }

    def _confirmed_day_slots(
        self,
        store: Store,
        exam_day_id: int,
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        day_slots = store.where(EXAM_SLOT, exam_day_id=exam_day_id)
        day_slot_ids = {slot["id"] for slot in day_slots}
        attendance = {
            row["exam_slot_id"]: row
            for row in store.all(CANDIDATE_EXAM_ATTENDANCE)
            if row["exam_slot_id"] in day_slot_ids
        }
        slots = []
        for slot in sorted(
            day_slots,
            key=lambda row: (row["starts_at"], row["sequence_number"], row["id"]),
        ):
            if slot["status"] not in {"confirmed", "completed", "cancelled"}:
                continue
            candidate = self._confirmed_slot_candidate(slot, context)
            if candidate is not None:
                slots.append(self._confirmed_slot_view(slot, candidate, attendance.get(slot["id"])))
        return slots

    @staticmethod
    def _confirmed_slot_candidate(
        slot: dict[str, Any],
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        round_candidate = context["round_candidates"].get(slot["round_candidate_id"])
        return (
            context["candidates"].get(round_candidate["candidate_id"]) if round_candidate else None
        )

    def _confirmed_slot_view(
        self,
        slot: dict[str, Any],
        candidate: dict[str, Any],
        attendance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "id": slot["id"],
            "starts_at": slot["starts_at"],
            "ends_at": slot["ends_at"],
            "sequence_number": slot["sequence_number"],
            "slot_type": slot["slot_type"],
            "actual_started_at": slot["actual_started_at"],
            "execution_status": slot["execution_status"],
            "status_changed_at": slot["status_changed_at"],
            "actual_completed_at": slot["actual_completed_at"],
            "status_reason": slot["status_reason"],
            "candidate_attendance": self._attendance_view(attendance),
            "candidate": {
                "id": candidate["id"],
                "first_name": candidate["first_name"],
                "last_name": candidate["last_name"],
                "ihk_exam_number": candidate["ihk_exam_number"],
            },
        }

    def _confirmed_day_assignments(
        self,
        store: Store,
        exam_day_id: int,
        context: dict[str, dict[int, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        attendance = {
            row["committee_member_id"]: row
            for row in store.where(MEMBER_EXAM_ATTENDANCE, exam_day_id=exam_day_id)
        }
        assignments = []
        for assignment in store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=exam_day_id):
            member = context["members"].get(assignment["committee_member_id"])
            if member is not None:
                assignments.append(
                    self._confirmed_assignment_view(
                        assignment,
                        member,
                        attendance.get(assignment["committee_member_id"]),
                    )
                )
        return assignments

    def _confirmed_assignment_view(
        self,
        assignment: dict[str, Any],
        member: dict[str, Any],
        attendance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "id": assignment["id"],
            "assignment_role": assignment["assignment_role"],
            "day_part": assignment["day_part"],
            "fallback_status": assignment["fallback_status"],
            "attendance": self._attendance_view(attendance),
            "member": {
                "id": member["id"],
                "first_name": member["first_name"],
                "last_name": member["last_name"],
                "representing_side": member["representing_side"],
            },
        }

    @staticmethod
    def _confirmed_day_location(
        room: dict[str, Any] | None,
        venues: dict[int, dict[str, Any]],
    ) -> dict[str, Any] | None:
        venue = venues.get(room["venue_id"]) if room else None
        if venue is None or room is None:
            return None
        return {
            "id": venue["id"],
            "name": venue["name"],
            "room": room["name"],
            "city": venue["city"],
        }

    def confirmed_plan_day(
        self,
        day_id: int,
        scope: AuthorizationScope | None = None,
    ) -> dict[str, Any] | None:
        """Return one day from the published read model, or no result.

        Reusing the confirmed-plan read model keeps the server-side state
        boundary identical for the calendar and the operational day view.
        Unknown, proposed, and cancelled days therefore never become usable
        through the focused endpoint.
        """
        for plan in self.confirmed_plans(scope):
            for day in plan["days"]:
                if day["id"] == day_id:
                    return {
                        "plan": {
                            "id": plan["id"],
                            "name": plan["name"],
                            "committee": plan["committee"],
                            "exam_half_year": plan["exam_half_year"],
                        },
                        "day": day,
                    }
        return None

    @staticmethod
    def _attendance_view(row: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "status": row["status"] if row else "open",
            "arrived_at": row["arrived_at"] if row else None,
        }

    @staticmethod
    def _execution_status_summary(slots: list[dict[str, Any]]) -> dict[str, int]:
        summary = {status: 0 for status in EXECUTION_STATUS_SUMMARY_KEYS}
        for slot in slots:
            summary[slot["execution_status"]] += 1
        return summary

    def _first(
        self,
        store: Store,
        resource: Resource,
        **filters: Any,
    ) -> dict[str, Any] | None:
        return store.first(resource, **filters)

    @staticmethod
    def _round_visible(
        _store: Store,
        exam_round: dict[str, Any] | None,
        scope: AuthorizationScope,
    ) -> bool:
        return exam_round is not None and scope.can_read_committee(exam_round["committee_id"])


REST_RESOURCES = {
    "committees": COMMITTEE,
    "persons": PERSON,
    "members": COMMITTEE_MEMBER,
    "memberships": COMMITTEE_MEMBER,
    "exam-half-years": EXAM_HALF_YEAR,
    "exam-rounds": EXAM_ROUND,
    "round-candidates": ROUND_CANDIDATE,
    "candidates": CANDIDATE,
    "planning-settings": PLANNING_SETTINGS,
    "candidate-exam-days": CANDIDATE_EXAM_DAY,
    "member-availabilities": MEMBER_AVAILABILITY,
    "exam-days": EXAM_DAY,
    "exam-slots": EXAM_SLOT,
    "exam-day-assignments": EXAM_DAY_ASSIGNMENT,
}
