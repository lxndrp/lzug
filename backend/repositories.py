"""Resource-oriented persistence operations and business validation boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, session_scope
from .holiday_provider import GERMAN_SUBDIVISION_CODES
from .models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    LOCATION,
    MEMBER_AVAILABILITY,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Resource,
)
from .store import Store

SPECIALIZATION_LABELS = {
    "application_development": "Anwendungsentwicklung",
    "system_integration": "Systemintegration",
    "data_and_process_analysis": "Daten- und Prozessanalyse",
    "digital_networking": "Digitale Vernetzung",
}

AVAILABILITY_VALUES = {"full_day", "morning", "afternoon", "unavailable", "pending"}


class ResourceRepository:
    """Expose CRUD operations while applying resource-specific domain rules.

    One repository call creates one :func:`session_scope`; the method either
    completes and commits all of its related writes or rolls them back. Generic
    ``Store`` operations remain deliberately unaware of person memberships,
    candidate records, and cross-committee assignment conflicts.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

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

    def get(self, resource: Resource, resource_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            return Store(session).get(resource, resource_id)

    def create(self, resource: Resource, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a resource after applying its domain-specific write rules.

        Person payloads are normalized, memberships are created through their
        dedicated invariant-preserving path, and assignment conflicts are
        rejected before a row is written.

        Raises:
            ValueError: If the payload violates a resource invariant or names
                an unknown field.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            if resource == PERSON:
                return store.create(PERSON, self._person_payload(payload))
            if resource == COMMITTEE_MEMBER:
                return self._create_membership(store, payload)
            if resource == EXAM_HALF_YEAR:
                return store.create(EXAM_HALF_YEAR, self._exam_half_year_payload(payload))
            if resource == EXAM_ROUND:
                return self._create_exam_round(store, payload)
            if resource == ROUND_CANDIDATE:
                return self._create_round_candidate(store, payload)
            if resource == EXAM_DAY_ASSIGNMENT:
                self._validate_assignment_conflict(store, payload)
            return store.create(resource, payload)

    def update(
        self,
        resource: Resource,
        resource_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update a resource and return ``None`` only when it does not exist.

        Membership and assignment writes reuse the same validation as creation.
        In particular, an assignment update cannot bypass person-wide conflict
        checks by changing only one of its fields.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            if resource == PERSON:
                return store.update(PERSON, resource_id, self._person_payload(payload))
            if resource == COMMITTEE_MEMBER:
                return self._update_membership(store, resource_id, payload)
            if resource == EXAM_HALF_YEAR:
                return store.update(
                    EXAM_HALF_YEAR, resource_id, self._exam_half_year_payload(payload)
                )
            if resource == EXAM_DAY_ASSIGNMENT:
                existing = store.get(resource, resource_id)
                if existing is None:
                    return None
                self._validate_assignment_conflict(store, {**existing, **payload}, resource_id)
            if resource == ROUND_CANDIDATE:
                raise ValueError(
                    "Round candidate assignments must be changed through the candidate endpoint"
                )
            return store.update(resource, resource_id, payload)

    def member_list(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            rows = store.where(COMMITTEE_MEMBER, **(filters or {}))
            return [self._member_view(store, row) for row in rows]

    def member_get(self, member_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            row = store.get(COMMITTEE_MEMBER, member_id)
            return self._member_view(store, row) if row else None

    def create_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            return self._create_membership(Store(session), payload)

    def update_membership(self, member_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            return self._update_membership(Store(session), member_id, payload)

    def _person_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "email" in normalized:
            email = str(normalized["email"]).strip().lower()
            if not email:
                raise ValueError("Primary email is required")
            normalized["email"] = email
        return normalized

    def _exam_half_year_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        season = normalized.get("season")
        if season is not None and season not in {"summer", "winter"}:
            raise ValueError("Season must be summer or winter")
        if "year" in normalized:
            try:
                normalized["year"] = int(normalized["year"])
            except (TypeError, ValueError) as error:
                raise ValueError("Year must be a four-digit number") from error
            if not 2000 <= normalized["year"] <= 2100:
                raise ValueError("Year must be between 2000 and 2100")
        if "status" in normalized and normalized["status"] not in {
            "draft",
            "active",
            "completed",
            "archived",
        }:
            raise ValueError("Unknown exam half-year status")
        return normalized

    def _create_exam_round(self, store: Store, payload: dict[str, Any]) -> dict[str, Any]:
        required = ("exam_half_year_id", "committee_id", "created_by_member_id")
        for field in required:
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        if store.get(EXAM_HALF_YEAR, payload["exam_half_year_id"]) is None:
            raise ValueError("Exam half-year not found")
        committee = store.get(COMMITTEE, payload["committee_id"])
        if committee is None:
            raise ValueError("Committee not found")
        creator = store.get(COMMITTEE_MEMBER, payload["created_by_member_id"])
        if creator is None or creator["committee_id"] != payload["committee_id"]:
            raise ValueError("Creating member does not belong to the exam round committee")
        if not str(payload.get("name", "")).strip():
            raise ValueError("Exam round name is required")
        return store.create(EXAM_ROUND, payload)

    def _create_round_candidate(self, store: Store, payload: dict[str, Any]) -> dict[str, Any]:
        candidate_id = int(payload["candidate_id"])
        exam_round_id = int(payload["exam_round_id"])
        self._assign_candidate_to_round(
            store,
            candidate_id,
            exam_round_id,
            attempt_number=payload.get("attempt_number", 1),
            requires_mep=payload.get("requires_mep", 0),
            change_reason=payload.get("assignment_change_reason"),
        )
        round_candidate = store.first(
            ROUND_CANDIDATE,
            candidate_id=candidate_id,
            exam_round_id=exam_round_id,
        )
        if round_candidate is None:
            raise ValueError("Round candidate assignment could not be created")
        return round_candidate

    def _create_membership(self, store: Store, payload: dict[str, Any]) -> dict[str, Any]:
        membership = dict(payload)
        person_id = membership.get("person_id")
        person_fields = {
            key: membership.pop(key)
            for key in ("first_name", "last_name", "email", "mobile")
            if key in membership
        }
        if person_id is None:
            required = {"first_name", "last_name", "email"}
            if not required.issubset(person_fields):
                raise ValueError(
                    "Select an existing person or provide first name, last name and email"
                )
            person = store.create(PERSON, self._person_payload(person_fields))
            person_id = person["id"]
        elif store.get(PERSON, int(person_id)) is None:
            raise ValueError("Person not found")
        elif person_fields:
            raise ValueError(
                "Existing person contact data must be changed through the person endpoint"
            )
        membership["person_id"] = person_id
        return self._member_view(store, store.create(COMMITTEE_MEMBER, membership))

    def _update_membership(
        self, store: Store, member_id: int, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        existing = store.get(COMMITTEE_MEMBER, member_id)
        if existing is None:
            return None
        if {"first_name", "last_name", "email", "mobile"}.intersection(payload):
            person_values = {
                key: payload[key]
                for key in ("first_name", "last_name", "email", "mobile")
                if key in payload
            }
            store.update(PERSON, existing["person_id"], self._person_payload(person_values))
        member_values = {
            key: value
            for key, value in payload.items()
            if key not in {"first_name", "last_name", "email", "mobile"}
        }
        row = (
            store.update(COMMITTEE_MEMBER, member_id, member_values) if member_values else existing
        )
        return self._member_view(store, row)

    def _member_view(self, store: Store, member: dict[str, Any]) -> dict[str, Any]:
        person = store.get(PERSON, member["person_id"])
        return {
            **member,
            **{key: person[key] for key in ("first_name", "last_name", "email", "mobile")},
            "email_verified_at": None,
        }

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

    def delete(self, resource: Resource, resource_id: int) -> bool:
        with session_scope(self.db_path) as session:
            return Store(session).delete(resource, resource_id)

    def candidate_list(self) -> list[dict[str, Any]]:
        rows = self.list(CANDIDATE)
        for row in rows:
            row["specialization_label"] = SPECIALIZATION_LABELS.get(
                row["specialization"], row["specialization"]
            )
        return rows

    def create_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            candidate = store.create(CANDIDATE, payload)
            if "exam_round_id" in payload:
                self._assign_candidate_to_round(
                    store,
                    candidate["id"],
                    int(payload["exam_round_id"]),
                    attempt_number=payload.get("attempt_number", 1),
                    requires_mep=payload.get("requires_mep", 0),
                )
            return candidate

    def update_candidate(
        self,
        candidate_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            candidate = store.update(CANDIDATE, candidate_id, payload)
            if candidate is None:
                return None

            round_fields = {"attempt_number", "requires_mep"}
            exam_round_id = payload.get("exam_round_id")
            if round_fields.intersection(payload) and exam_round_id is None:
                raise ValueError("Missing required field: exam_round_id")
            if exam_round_id is not None:
                self._assign_candidate_to_round(
                    store,
                    candidate_id,
                    int(exam_round_id),
                    attempt_number=payload.get("attempt_number"),
                    requires_mep=payload.get("requires_mep"),
                    change_reason=payload.get("assignment_change_reason"),
                )

            return candidate

    def candidate_committee_assignments(
        self,
        candidate_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            filters = {"candidate_id": candidate_id} if candidate_id is not None else {}
            return store.where(CANDIDATE_COMMITTEE_ASSIGNMENT, **filters)

    def _assign_candidate_to_round(
        self,
        store: Store,
        candidate_id: int,
        exam_round_id: int,
        *,
        attempt_number: int | None,
        requires_mep: int | None,
        change_reason: str | None = None,
    ) -> dict[str, Any]:
        """Activate one committee-round assignment and preserve an earlier one."""
        if store.get(CANDIDATE, candidate_id) is None:
            raise ValueError("Candidate not found")
        exam_round = store.get(EXAM_ROUND, exam_round_id)
        if exam_round is None:
            raise ValueError("Exam round not found")

        exam_half_year_id = exam_round["exam_half_year_id"]
        active_assignment = store.first(
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            candidate_id=candidate_id,
            exam_half_year_id=exam_half_year_id,
            ended_at=None,
        )
        target_round_candidate = store.first(
            ROUND_CANDIDATE,
            candidate_id=candidate_id,
            exam_round_id=exam_round_id,
        )

        if active_assignment and active_assignment["exam_round_id"] != exam_round_id:
            reason = str(change_reason or "").strip()
            if not reason:
                raise ValueError("A reason is required for a committee change")
            self._end_candidate_assignment(store, active_assignment, reason)
            active_assignment = None

        if target_round_candidate is None:
            target_round_candidate = store.create(
                ROUND_CANDIDATE,
                {
                    "exam_round_id": exam_round_id,
                    "candidate_id": candidate_id,
                    "attempt_number": attempt_number or 1,
                    "requires_mep": requires_mep or 0,
                    "is_active": 1,
                },
            )
        else:
            updated_values: dict[str, Any] = {"is_active": 1}
            if attempt_number is not None:
                updated_values["attempt_number"] = attempt_number
            if requires_mep is not None:
                updated_values["requires_mep"] = requires_mep
            target_round_candidate = (
                store.update(ROUND_CANDIDATE, target_round_candidate["id"], updated_values)
                or target_round_candidate
            )

        if active_assignment is None:
            return store.create(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                {
                    "candidate_id": candidate_id,
                    "exam_half_year_id": exam_half_year_id,
                    "exam_round_id": exam_round_id,
                    "round_candidate_id": target_round_candidate["id"],
                },
            )
        return active_assignment

    def _end_candidate_assignment(
        self,
        store: Store,
        assignment: dict[str, Any],
        change_reason: str,
    ) -> None:
        ended_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        store.update(
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            assignment["id"],
            {"ended_at": ended_at, "change_reason": change_reason},
        )
        store.update(ROUND_CANDIDATE, assignment["round_candidate_id"], {"is_active": 0})

    def save_planning_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            self._validate_planning_settings(store, payload)
            existing = store.first(
                PLANNING_SETTINGS,
                exam_round_id=payload["exam_round_id"],
            )
            if existing is None:
                return store.create(PLANNING_SETTINGS, payload)
            return store.update(PLANNING_SETTINGS, existing["id"], payload) or existing

    def update_planning_settings(
        self,
        settings_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            existing = store.get(PLANNING_SETTINGS, settings_id)
            if existing is None:
                return None
            merged = {**existing, **payload}
            self._validate_planning_settings(store, merged)
            return store.update(PLANNING_SETTINGS, settings_id, payload) or existing

    def update_exam_round(
        self,
        round_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            existing = store.get(EXAM_ROUND, round_id)
            if existing is None:
                return None

            merged = {**existing, **payload}
            if any(
                merged[field] != existing[field]
                for field in ("exam_half_year_id", "committee_id")
                if field in payload
            ):
                raise ValueError(
                    "An exam round cannot be reassigned to another half-year or committee"
                )
            if not str(merged.get("name", "")).strip():
                raise ValueError("Exam round name is required")
            deadline = merged.get("availability_deadline")
            reminder = merged.get("availability_reminder_at")
            if deadline and reminder and reminder > deadline:
                raise ValueError("Availability reminder must be before the deadline")

            return store.update(EXAM_ROUND, round_id, payload) or existing

    def save_member_availability(self, payload: dict[str, Any]) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            payload = self._availability_payload(store, payload)
            existing = store.first(
                MEMBER_AVAILABILITY,
                exam_round_id=payload["exam_round_id"],
                committee_member_id=payload["committee_member_id"],
                candidate_exam_day_id=payload["candidate_exam_day_id"],
            )
            saved = (
                store.create(MEMBER_AVAILABILITY, payload)
                if existing is None
                else store.update(MEMBER_AVAILABILITY, existing["id"], payload) or existing
            )
            self._propagate_person_availability(store, saved)
            return saved

    def update_member_availability(
        self,
        availability_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            existing = store.get(MEMBER_AVAILABILITY, availability_id)
            if existing is None:
                return None
            normalized = self._availability_payload(store, {**existing, **payload})
            saved = store.update(MEMBER_AVAILABILITY, availability_id, normalized) or existing
            self._propagate_person_availability(store, saved)
            return saved

    def delete_candidate(self, candidate_id: int) -> bool:
        with session_scope(self.db_path) as session:
            store = Store(session)
            store.delete_where(CANDIDATE_COMMITTEE_ASSIGNMENT, candidate_id=candidate_id)
            store.delete_where(ROUND_CANDIDATE, candidate_id=candidate_id)
            return store.delete(CANDIDATE, candidate_id)

    def round_summary(self, round_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                return None

            committee = store.get(COMMITTEE, exam_round["committee_id"])
            exam_half_year = store.get(EXAM_HALF_YEAR, exam_round["exam_half_year_id"])
            candidate_count = store.count(
                ROUND_CANDIDATE,
                exam_round_id=round_id,
                is_active=1,
            )
            mep_count = store.count(
                ROUND_CANDIDATE,
                exam_round_id=round_id,
                requires_mep=1,
                is_active=1,
            )
            settings = self._first(
                store,
                PLANNING_SETTINGS,
                exam_round_id=round_id,
            )

            return {
                "round": {
                    "id": exam_round["id"],
                    "name": exam_round["name"],
                    "status": exam_round["status"],
                    "committee_name": committee["name"] if committee else None,
                    "exam_half_year": exam_half_year,
                },
                "counts": {
                    "candidates": candidate_count,
                    "mep_count": mep_count,
                    "required_exam_slots": candidate_count + mep_count,
                },
                "settings": settings,
                "availability": store.grouped_counts(
                    MEMBER_AVAILABILITY,
                    "availability",
                    exam_round_id=round_id,
                ),
            }

    def scheduling_overview(self) -> list[dict[str, Any]]:
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

    def confirmed_plans(self) -> list[dict[str, Any]]:
        """Return the published calendar read model, excluding every proposal.

        This deliberately performs the state check at the server boundary.  A
        client cannot obtain draft or proposed appointments by merely hiding a
        tab in the UI.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            committees = {row["id"]: row for row in store.all(COMMITTEE)}
            half_years = {row["id"]: row for row in store.all(EXAM_HALF_YEAR)}
            locations = {row["id"]: row for row in store.all(LOCATION)}
            candidates = {row["id"]: row for row in store.all(CANDIDATE)}
            round_candidates = {row["id"]: row for row in store.all(ROUND_CANDIDATE)}
            members = {
                row["id"]: self._member_view(store, row) for row in store.all(COMMITTEE_MEMBER)
            }

            plans = []
            for exam_round in store.where(EXAM_ROUND, status="plan_confirmed"):
                committee = committees.get(exam_round["committee_id"])
                if committee is None:
                    continue
                days = []
                for exam_day in sorted(
                    store.where(EXAM_DAY, exam_round_id=exam_round["id"]),
                    key=lambda row: (row["date"], row["id"]),
                ):
                    if exam_day["status"] != "confirmed":
                        continue
                    slots = []
                    for slot in sorted(
                        store.where(EXAM_SLOT, exam_day_id=exam_day["id"]),
                        key=lambda row: (row["starts_at"], row["sequence_number"], row["id"]),
                    ):
                        if slot["status"] != "confirmed":
                            continue
                        round_candidate = round_candidates.get(slot["round_candidate_id"])
                        candidate = (
                            candidates.get(round_candidate["candidate_id"])
                            if round_candidate
                            else None
                        )
                        if candidate is None:
                            continue
                        slots.append(
                            {
                                "id": slot["id"],
                                "starts_at": slot["starts_at"],
                                "ends_at": slot["ends_at"],
                                "sequence_number": slot["sequence_number"],
                                "slot_type": slot["slot_type"],
                                "candidate": {
                                    "id": candidate["id"],
                                    "first_name": candidate["first_name"],
                                    "last_name": candidate["last_name"],
                                    "ihk_exam_number": candidate["ihk_exam_number"],
                                },
                            }
                        )
                    assignments = []
                    for assignment in store.where(EXAM_DAY_ASSIGNMENT, exam_day_id=exam_day["id"]):
                        member = members.get(assignment["committee_member_id"])
                        if member is None:
                            continue
                        assignments.append(
                            {
                                "id": assignment["id"],
                                "assignment_role": assignment["assignment_role"],
                                "day_part": assignment["day_part"],
                                "fallback_status": assignment["fallback_status"],
                                "member": {
                                    "id": member["id"],
                                    "first_name": member["first_name"],
                                    "last_name": member["last_name"],
                                    "representing_side": member["representing_side"],
                                },
                            }
                        )
                    location = locations.get(exam_day["location_id"])
                    days.append(
                        {
                            "id": exam_day["id"],
                            "date": exam_day["date"],
                            "location": (
                                {
                                    "id": location["id"],
                                    "name": location["name"],
                                    "room": location["room"],
                                    "city": location["city"],
                                }
                                if location
                                else None
                            ),
                            "slots": slots,
                            "assignments": assignments,
                        }
                    )
                plans.append(
                    {
                        "id": exam_round["id"],
                        "name": exam_round["name"],
                        "committee": {"id": committee["id"], "name": committee["name"]},
                        "exam_half_year": half_years.get(exam_round["exam_half_year_id"]),
                        "days": days,
                    }
                )
            return sorted(
                plans, key=lambda plan: (plan["committee"]["name"], plan["name"], plan["id"])
            )

    def _first(
        self,
        store: Store,
        resource: Resource,
        **filters: Any,
    ) -> dict[str, Any] | None:
        return store.first(resource, **filters)

    def _validate_planning_settings(
        self,
        store: Store,
        payload: dict[str, Any],
    ) -> None:
        required_fields = ("exam_round_id", "updated_by_member_id")
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")

        exam_round = store.get(EXAM_ROUND, payload["exam_round_id"])
        if exam_round is None:
            raise ValueError("Exam round not found")

        updater = store.get(COMMITTEE_MEMBER, payload["updated_by_member_id"])
        if updater is None or updater["committee_id"] != exam_round["committee_id"]:
            raise ValueError("Updating member does not belong to the exam round committee")

        if "default_location_id" in payload and payload["default_location_id"] is not None:
            location = store.get(LOCATION, payload["default_location_id"])
            if location is None or location["committee_id"] != exam_round["committee_id"]:
                raise ValueError("Default location does not belong to the exam round committee")

        subdivision_code = payload.get("holiday_subdivision_code")
        if subdivision_code is not None and subdivision_code not in GERMAN_SUBDIVISION_CODES:
            raise ValueError("Unknown German federal state")
        if payload.get("exclude_public_holidays") and subdivision_code is None:
            raise ValueError("Federal state is required when public holidays are excluded")

    def _availability_payload(
        self,
        store: Store,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        required_fields = (
            "exam_round_id",
            "committee_member_id",
            "candidate_exam_day_id",
            "availability",
        )
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")

        if payload["availability"] not in AVAILABILITY_VALUES:
            raise ValueError("Unknown availability value")

        exam_round = store.get(EXAM_ROUND, payload["exam_round_id"])
        if exam_round is None:
            raise ValueError("Exam round not found")

        member = store.get(COMMITTEE_MEMBER, payload["committee_member_id"])
        if member is None or member["committee_id"] != exam_round["committee_id"]:
            raise ValueError("Member does not belong to the exam round committee")

        exam_day = store.get(CANDIDATE_EXAM_DAY, payload["candidate_exam_day_id"])
        if exam_day is None or exam_day["exam_round_id"] != payload["exam_round_id"]:
            raise ValueError("Candidate exam day does not belong to the exam round")

        normalized = dict(payload)
        if normalized["availability"] == "pending":
            normalized["responded_at"] = None
        else:
            normalized["responded_at"] = (
                normalized.get("responded_at")
                or datetime.now(UTC).replace(microsecond=0).isoformat()
            )
        return normalized

    def _propagate_person_availability(self, store: Store, saved: dict[str, Any]) -> None:
        """Mirror one response to same-person memberships in the same half-year."""
        member = store.get(COMMITTEE_MEMBER, saved["committee_member_id"])
        source_day = store.get(CANDIDATE_EXAM_DAY, saved["candidate_exam_day_id"])
        source_round = store.get(EXAM_ROUND, saved["exam_round_id"])
        if member is None or source_day is None or source_round is None:
            return
        for other_member in store.all(COMMITTEE_MEMBER):
            if (
                other_member["id"] == member["id"]
                or other_member["person_id"] != member["person_id"]
            ):
                continue
            for other_day in store.all(CANDIDATE_EXAM_DAY):
                if other_day["date"] != source_day["date"]:
                    continue
                other_round = store.get(EXAM_ROUND, other_day["exam_round_id"])
                if (
                    other_round is None
                    or other_round["committee_id"] != other_member["committee_id"]
                    or other_round["exam_half_year_id"] != source_round["exam_half_year_id"]
                ):
                    continue
                existing = store.first(
                    MEMBER_AVAILABILITY,
                    exam_round_id=other_day["exam_round_id"],
                    committee_member_id=other_member["id"],
                    candidate_exam_day_id=other_day["id"],
                )
                values = {
                    "exam_round_id": other_day["exam_round_id"],
                    "committee_member_id": other_member["id"],
                    "candidate_exam_day_id": other_day["id"],
                    "availability": saved["availability"],
                    "responded_at": saved["responded_at"],
                }
                if existing is None:
                    store.create(MEMBER_AVAILABILITY, values)
                else:
                    store.update(MEMBER_AVAILABILITY, existing["id"], values)


REST_RESOURCES = {
    "committees": COMMITTEE,
    "persons": PERSON,
    "members": COMMITTEE_MEMBER,
    "memberships": COMMITTEE_MEMBER,
    "locations": LOCATION,
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
