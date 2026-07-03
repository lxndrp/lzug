from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, session_scope
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
        with session_scope(self.db_path) as session:
            return Store(session).create(resource, payload)

    def update(
        self,
        resource: Resource,
        resource_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            return Store(session).update(resource, resource_id, payload)

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
            if existing is None:
                return store.create(MEMBER_AVAILABILITY, payload)
            return store.update(MEMBER_AVAILABILITY, existing["id"], payload) or existing

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
            return store.update(MEMBER_AVAILABILITY, availability_id, normalized) or existing

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
            raise ValueError(
                "Updating member does not belong to the exam round committee"
            )

        if (
            "default_location_id" in payload
            and payload["default_location_id"] is not None
        ):
            location = store.get(LOCATION, payload["default_location_id"])
            if location is None or location["committee_id"] != exam_round["committee_id"]:
                raise ValueError(
                    "Default location does not belong to the exam round committee"
                )

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
            normalized["responded_at"] = normalized.get("responded_at") or datetime.now(
                timezone.utc
            ).replace(microsecond=0).isoformat()
        return normalized


REST_RESOURCES = {
    "committees": COMMITTEE,
    "members": COMMITTEE_MEMBER,
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
