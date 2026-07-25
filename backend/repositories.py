"""Resource-oriented persistence operations and business validation boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, session_scope
from .holiday_provider import GERMAN_SUBDIVISION_CODES
from .models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
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
            if resource == EXAM_DAY_ASSIGNMENT:
                existing = store.get(resource, resource_id)
                if existing is None:
                    return None
                self._validate_assignment_conflict(store, {**existing, **payload}, resource_id)
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
            if (
                target_part == "full_day"
                or assignment["day_part"] == "full_day"
                or assignment["day_part"] == target_part
            ):
                other_round = store.get(EXAM_ROUND, other_day["exam_round_id"])
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
                store.create(
                    ROUND_CANDIDATE,
                    {
                        "exam_round_id": payload["exam_round_id"],
                        "candidate_id": candidate["id"],
                        "attempt_number": payload.get("attempt_number", 1),
                        "requires_mep": payload.get("requires_mep", 0),
                    },
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
            if round_fields.intersection(payload):
                exam_round_id = payload.get("exam_round_id")
                if exam_round_id is None:
                    raise ValueError("Missing required field: exam_round_id")
                round_candidate = store.first(
                    ROUND_CANDIDATE,
                    candidate_id=candidate_id,
                    exam_round_id=exam_round_id,
                )
                if round_candidate is None:
                    raise ValueError("Candidate does not belong to the exam round")
                store.update(ROUND_CANDIDATE, round_candidate["id"], payload)

            return candidate

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
            store.delete_where(ROUND_CANDIDATE, candidate_id=candidate_id)
            return store.delete(CANDIDATE, candidate_id)

    def round_summary(self, round_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                return None

            committee = store.get(COMMITTEE, exam_round["committee_id"])
            candidate_count = store.count(ROUND_CANDIDATE, exam_round_id=round_id)
            mep_count = store.count(
                ROUND_CANDIDATE,
                exam_round_id=round_id,
                requires_mep=1,
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

        existing = store.first(
            PLANNING_SETTINGS,
            exam_round_id=payload["exam_round_id"],
        )
        changes_week_limit = "max_exam_days_per_week" in payload and (
            existing is None
            or existing["max_exam_days_per_week"] != payload["max_exam_days_per_week"]
        )
        if changes_week_limit and updater["committee_role"] != "chair":
            raise ValueError("Only the committee chair may change max_exam_days_per_week")

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
        """Mirror one response to same-person memberships on the same calendar day."""
        member = store.get(COMMITTEE_MEMBER, saved["committee_member_id"])
        source_day = store.get(CANDIDATE_EXAM_DAY, saved["candidate_exam_day_id"])
        if member is None or source_day is None:
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
