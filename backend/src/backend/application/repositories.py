"""Resource-oriented persistence operations and business validation boundaries."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.application.resource_access import (
    ResourceAccessQueryFactory,
    ResourceKind,
    reference_changes,
)
from backend.execution.exam_day_closures import complete_day_mutation, guard_day_mutation
from backend.execution.exam_protocols import create_protocol_for_started_slot
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

ATTENDANCE_VALUES = {"open", "present", "late", "absent"}
REPRESENTING_SIDES = {"employer", "employee", "school"}
EXECUTION_STATUS_VALUES = {"open", "running", "completed", "cancelled", "needs_follow_up"}
EXECUTION_STATUS_TRANSITIONS = {
    "open": {"cancelled"},
    "running": {"completed", "needs_follow_up"},
    "needs_follow_up": {"completed"},
}
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

    def save_candidate_attendance(
        self,
        day_id: int,
        slot_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            self._confirmed_slot(store, day_id, slot_id)
            existing = store.first(CANDIDATE_EXAM_ATTENDANCE, exam_slot_id=slot_id)
            values = self._attendance_payload(payload, existing)
            values["exam_slot_id"] = slot_id
            if existing is not None and all(
                existing[key] == value for key, value in values.items()
            ):
                return existing
            day = session.get(EXAM_DAY.model, day_id)
            guard = guard_day_mutation(
                session,
                day=day,
                kind="candidate_attendance",
                entity_id=slot_id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
            if existing is None:
                result = store.create(CANDIDATE_EXAM_ATTENDANCE, values)
            else:
                result = store.update(CANDIDATE_EXAM_ATTENDANCE, existing["id"], values) or existing
            complete_day_mutation(session, guard, actor_member_id=actor_member_id)
            return result

    def save_member_attendance(
        self,
        day_id: int,
        assignment_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            assignment = self._confirmed_assignment(store, day_id, assignment_id)
            member_id = assignment["committee_member_id"]
            existing = store.first(
                MEMBER_EXAM_ATTENDANCE,
                exam_day_id=day_id,
                committee_member_id=member_id,
            )
            values = self._attendance_payload(payload, existing)
            values.update({"exam_day_id": day_id, "committee_member_id": member_id})
            if existing is not None and all(
                existing[key] == value for key, value in values.items()
            ):
                return existing
            day = session.get(EXAM_DAY.model, day_id)
            guard = guard_day_mutation(
                session,
                day=day,
                kind="member_attendance",
                entity_id=assignment_id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
            if existing is None:
                result = store.create(MEMBER_EXAM_ATTENDANCE, values)
            else:
                result = store.update(MEMBER_EXAM_ATTENDANCE, existing["id"], values) or existing
            complete_day_mutation(session, guard, actor_member_id=actor_member_id)
            return result

    def update_exam_slot_status(
        self,
        day_id: int,
        slot_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            slot = self._confirmed_slot(store, day_id, slot_id)
            day = session.get(EXAM_DAY.model, day_id)
            if day is None:
                raise ValueError("Prüfungstag nicht gefunden")
            correction_mode = day.closure_status == "reopening"
            target_status = self._slot_status_target(payload)
            reason = self._slot_status_reason(slot, payload, target_status)
            changed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            actual_started_at, actual_completed_at = self._slot_status_facts(
                slot,
                payload,
                target_status,
                changed_at,
                correction_mode,
            )
            if self._slot_status_is_unchanged(
                slot, target_status, reason, actual_started_at, actual_completed_at
            ):
                return slot
            guard = guard_day_mutation(
                session,
                day=day,
                kind="slot_status",
                entity_id=slot_id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
            self._validate_slot_status_transition(slot, target_status, correction_mode)
            exam_slot = session.get(EXAM_SLOT.model, slot_id)
            if exam_slot is None:
                raise ValueError("Prüfungsslot nicht gefunden")
            self._apply_slot_status(
                exam_slot,
                target_status,
                changed_at,
                reason,
                actual_started_at,
                actual_completed_at,
            )
            session.flush()
            complete_day_mutation(
                session,
                guard,
                actor_member_id=actor_member_id,
                reason=reason,
            )
            return {
                **slot,
                "execution_status": target_status,
                "status_changed_at": changed_at,
                "actual_started_at": actual_started_at,
                "actual_completed_at": actual_completed_at,
                "status_reason": reason,
            }

    @staticmethod
    def _slot_status_target(payload: dict[str, Any]) -> str:
        target_status = payload.get("status")
        if target_status not in EXECUTION_STATUS_VALUES:
            raise ValueError("Unbekannter Durchführungsstatus")
        return target_status

    @staticmethod
    def _slot_status_reason(
        slot: dict[str, Any],
        payload: dict[str, Any],
        target_status: str,
    ) -> str | None:
        if target_status not in {"cancelled", "needs_follow_up"}:
            return slot["status_reason"]
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                "Für einen Ausfall oder eine Nachbereitung ist eine Begründung erforderlich"
            )
        return reason.strip()

    def _slot_status_facts(
        self,
        slot: dict[str, Any],
        payload: dict[str, Any],
        target_status: str,
        changed_at: str,
        correction_mode: bool,
    ) -> tuple[Any, Any]:
        actual_started_at = slot["actual_started_at"]
        actual_completed_at = slot["actual_completed_at"]
        if correction_mode:
            actual_started_at = payload.get("actual_started_at", actual_started_at)
            actual_completed_at = payload.get("actual_completed_at", actual_completed_at)
            self._validate_corrected_slot_facts(
                target_status,
                actual_started_at,
                actual_completed_at,
            )
        elif target_status == "completed":
            actual_completed_at = changed_at
        return actual_started_at, actual_completed_at

    @staticmethod
    def _slot_status_is_unchanged(
        slot: dict[str, Any],
        target_status: str,
        reason: str | None,
        actual_started_at: Any,
        actual_completed_at: Any,
    ) -> bool:
        return (
            target_status == slot["execution_status"]
            and reason == slot["status_reason"]
            and actual_started_at == slot["actual_started_at"]
            and actual_completed_at == slot["actual_completed_at"]
        )

    @staticmethod
    def _validate_slot_status_transition(
        slot: dict[str, Any],
        target_status: str,
        correction_mode: bool,
    ) -> None:
        if target_status == "running" and not correction_mode:
            raise ValueError("Der Status Läuft wird ausschließlich durch die Startaktion gesetzt")
        if (
            not correction_mode
            and target_status == "cancelled"
            and slot["actual_started_at"] is not None
        ):
            raise ValueError(
                "Ein gestarteter Prüfungsslot kann nicht als ausgefallen markiert werden"
            )
        allowed = EXECUTION_STATUS_TRANSITIONS.get(slot["execution_status"], set())
        if not correction_mode and target_status not in allowed:
            raise ValueError(
                f"Der Statuswechsel von {slot['execution_status']} "
                f"zu {target_status} ist nicht erlaubt"
            )

    @staticmethod
    def _apply_slot_status(
        exam_slot: Any,
        target_status: str,
        changed_at: str,
        reason: str | None,
        actual_started_at: Any,
        actual_completed_at: Any,
    ) -> None:
        exam_slot.execution_status = target_status
        exam_slot.status_changed_at = changed_at
        exam_slot.status_reason = reason
        exam_slot.actual_started_at = actual_started_at
        exam_slot.actual_completed_at = actual_completed_at

    def start_exam_slot(
        self,
        day_id: int,
        slot_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            slot = self._confirmed_slot(store, day_id, slot_id)
            self._validate_startable_slot(slot)
            self._require_present_candidate(store, slot_id)
            present_regular_members = self._present_regular_members(store, day_id, slot)
            requested_started_at = payload.get("actual_started_at")
            repeated = self._repeat_slot_start(
                session,
                slot,
                slot_id,
                requested_started_at,
                present_regular_members,
                actor_member_id,
            )
            if repeated is not None:
                return repeated
            actual_started_at = self._actual_slot_start(requested_started_at)
            exam_slot = session.get(EXAM_SLOT.model, slot_id)
            if exam_slot is None:
                raise ValueError("Prüfungsslot nicht gefunden")
            day = session.get(EXAM_DAY.model, day_id)
            guard = guard_day_mutation(
                session,
                day=day,
                kind="slot_status",
                entity_id=slot_id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
            exam_slot.actual_started_at = actual_started_at
            exam_slot.execution_status = "running"
            exam_slot.status_changed_at = actual_started_at
            create_protocol_for_started_slot(
                session,
                slot_id=slot_id,
                participant_member_ids=present_regular_members,
                created_by_member_id=actor_member_id,
                created_at=actual_started_at,
            )
            session.flush()
            complete_day_mutation(session, guard, actor_member_id=actor_member_id)
            return {
                **slot,
                "actual_started_at": actual_started_at,
                "execution_status": "running",
                "status_changed_at": actual_started_at,
            }

    @staticmethod
    def _validate_startable_slot(slot: dict[str, Any]) -> None:
        if slot["execution_status"] not in {"open", "running"}:
            raise ValueError(
                "Ein abgeschlossener oder ausgefallener Prüfungsslot kann nicht gestartet werden"
            )
        if slot["execution_status"] == "running" and slot["actual_started_at"] is None:
            raise ValueError("Der laufende Prüfungsslot hat keinen tatsächlichen Startzeitpunkt")

    @staticmethod
    def _require_present_candidate(store: Store, slot_id: int) -> None:
        attendance = store.first(CANDIDATE_EXAM_ATTENDANCE, exam_slot_id=slot_id)
        if attendance is None or attendance["status"] not in {"present", "late"}:
            raise ValueError("Prüfling muss als anwesend oder verspätet erfasst sein")

    def _present_regular_members(
        self,
        store: Store,
        day_id: int,
        slot: dict[str, Any],
    ) -> set[int]:
        members: set[int] = set()
        sides: set[str] = set()
        for assignment in store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=day_id):
            if assignment["assignment_role"] != "examiner":
                continue
            if not self._assignment_applies_to_slot(assignment, slot):
                continue
            attendance = store.first(
                MEMBER_EXAM_ATTENDANCE,
                exam_day_id=day_id,
                committee_member_id=assignment["committee_member_id"],
            )
            if attendance is None or attendance["status"] not in {"present", "late"}:
                continue
            member = store.get(COMMITTEE_MEMBER, assignment["committee_member_id"])
            if member is not None:
                members.add(member["id"])
                sides.add(member["representing_side"])
        if len(members) < 3 or not REPRESENTING_SIDES.issubset(sides):
            raise ValueError(
                "Mindestens drei anwesende reguläre Prüfer mit allen drei "
                "Vertreterseiten sind erforderlich"
            )
        return members

    @staticmethod
    def _repeat_slot_start(
        session: Any,
        slot: dict[str, Any],
        slot_id: int,
        requested_started_at: Any,
        present_regular_members: set[int],
        actor_member_id: int,
    ) -> dict[str, Any] | None:
        if slot["actual_started_at"] is None:
            return None
        if slot["execution_status"] != "running":
            raise ValueError("Der Prüfungsslot kann nicht erneut gestartet werden")
        if requested_started_at and slot["actual_started_at"] != requested_started_at:
            raise ValueError(f"Prüfungsstart wurde bereits um {slot['actual_started_at']} erfasst")
        create_protocol_for_started_slot(
            session,
            slot_id=slot_id,
            participant_member_ids=present_regular_members,
            created_by_member_id=actor_member_id,
            created_at=slot["actual_started_at"],
        )
        return slot

    @staticmethod
    def _actual_slot_start(requested_started_at: Any) -> str:
        actual_started_at = (
            requested_started_at or datetime.now(UTC).replace(microsecond=0).isoformat()
        )
        if not isinstance(actual_started_at, str) or not actual_started_at.strip():
            raise ValueError("Tatsächlicher Startzeitpunkt ist erforderlich")
        return actual_started_at

    @staticmethod
    def _execution_status_summary(slots: list[dict[str, Any]]) -> dict[str, int]:
        summary = {status: 0 for status in EXECUTION_STATUS_SUMMARY_KEYS}
        for slot in slots:
            summary[slot["execution_status"]] += 1
        return summary

    def _confirmed_slot(self, store: Store, day_id: int, slot_id: int) -> dict[str, Any]:
        slot = store.get(EXAM_SLOT, slot_id)
        day = store.get(EXAM_DAY, day_id)
        if (
            slot is None
            or day is None
            or slot["exam_day_id"] != day_id
            or slot["status"] != "confirmed"
            or day["status"] not in {"confirmed", "completed", "cancelled"}
        ):
            raise ValueError(
                "Nur ein bestätigter Prüfungsslot des ausgewählten Tages darf geändert werden"
            )
        exam_round = store.get(EXAM_ROUND, day["exam_round_id"])
        if exam_round is None or exam_round["status"] != "plan_confirmed":
            raise ValueError(
                "Der Prüfungstag ist nicht Bestandteil eines bestätigten Prüfungsplans"
            )
        return slot

    def _confirmed_assignment(
        self, store: Store, day_id: int, assignment_id: int
    ) -> dict[str, Any]:
        assignment = store.get(EXAM_DAY_ASSIGNMENT, assignment_id)
        day = store.get(EXAM_DAY, day_id)
        if assignment is None or day is None or assignment["exam_day_id"] != day_id:
            raise ValueError(
                "Nur eine Besetzung des ausgewählten Prüfungstags darf geändert werden"
            )
        if day["status"] not in {"confirmed", "completed", "cancelled"}:
            raise ValueError(
                "Nur Besetzungen eines bestätigten Prüfungstags dürfen geändert werden"
            )
        exam_round = store.get(EXAM_ROUND, day["exam_round_id"])
        if exam_round is None or exam_round["status"] != "plan_confirmed":
            raise ValueError(
                "Der Prüfungstag ist nicht Bestandteil eines bestätigten Prüfungsplans"
            )
        return assignment

    @staticmethod
    def _validate_corrected_slot_facts(
        target_status: str,
        actual_started_at: Any,
        actual_completed_at: Any,
    ) -> None:
        def parsed(value: Any, label: str) -> datetime | None:
            if value is None:
                return None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} ist ungültig")
            try:
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(f"{label} ist ungültig") from error
            if result.tzinfo is None:
                raise ValueError(f"{label} benötigt eine Zeitzone")
            return result

        started = parsed(actual_started_at, "Tatsächlicher Beginn")
        completed = parsed(actual_completed_at, "Tatsächliches Ende")
        if target_status == "completed" and (started is None or completed is None):
            raise ValueError(
                "Ein korrigierter abgeschlossener Slot benötigt tatsächlichen Beginn und Ende"
            )
        if target_status in {"open", "cancelled"} and (
            started is not None or completed is not None
        ):
            raise ValueError(
                "Ein offener oder ausgefallener Slot darf keine tatsächlichen Zeiten enthalten"
            )
        if target_status in {"running", "needs_follow_up"} and started is None:
            raise ValueError("Ein begonnener Slot benötigt einen tatsächlichen Beginn")
        if started is not None and completed is not None and completed <= started:
            raise ValueError("Das tatsächliche Ende muss nach dem tatsächlichen Beginn liegen")

    def _attendance_payload(
        self, payload: dict[str, Any], existing: dict[str, Any] | None
    ) -> dict[str, Any]:
        status = payload.get("status")
        if status not in ATTENDANCE_VALUES:
            raise ValueError("Unbekannter Anwesenheitsstatus")
        arrived_at = payload.get("arrived_at", existing["arrived_at"] if existing else None)
        if status in {"open", "absent"}:
            arrived_at = None
        elif status == "late" and (not isinstance(arrived_at, str) or not arrived_at.strip()):
            raise ValueError("Für verspätete Personen ist die Ankunftszeit erforderlich")
        return {"status": status, "arrived_at": arrived_at}

    @staticmethod
    def _assignment_applies_to_slot(assignment: dict[str, Any], slot: dict[str, Any]) -> bool:
        day_part = assignment["day_part"]
        if day_part == "full_day":
            return True
        try:
            start = datetime.fromisoformat(slot["starts_at"].replace(" ", "T"))
        except TypeError, ValueError:
            return True
        return (day_part == "morning" and start.hour < 12) or (
            day_part == "afternoon" and start.hour >= 12
        )

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
