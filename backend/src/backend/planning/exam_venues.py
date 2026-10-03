"""Planning-owned exam-venue rules and typed repository commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.planning_ports import (
    ACCESSIBILITY_STATUSES,
    COMMAND_META_FIELDS,
    COORDINATE_STATUSES,
    VENUE_FIELDS,
    VENUE_SCOPES,
    ExamVenueError,
    GeocodeCandidate,
    Geocoder,
    VenueChangeFollowUp,
    VenueCommand,
    VenueCommandKind,
    VenueCommandResult,
    VenueQuery,
    VenueQueryKind,
    VenueRepository,
    normalize_venue_text,
)


class ExamVenuePolicy:
    """Decide venue field and lifecycle rules from detached Planning values."""

    @staticmethod
    def venue_values(
        payload: Mapping[str, object], current: Mapping[str, object] | None = None
    ) -> tuple[dict[str, object], str | None]:
        command, reason = ExamVenuePolicy._command(payload, VENUE_FIELDS)
        source = ExamVenuePolicy.venue_source(current, command)
        scope = ExamVenuePolicy._choice(source["scope"], "scope", VENUE_SCOPES)
        committee_id = ExamVenuePolicy._optional_integer(source["committee_id"], "committee_id")
        if (scope == "global" and committee_id is not None) or (
            scope == "committee" and committee_id is None
        ):
            raise ExamVenueError("Venue scope and committee must agree")
        accessibility_status = ExamVenuePolicy._choice(
            source["accessibility_status"], "accessibility_status", ACCESSIBILITY_STATUSES
        )
        is_accessible = ExamVenuePolicy._optional_boolean(source["is_accessible"], "is_accessible")
        if (accessibility_status == "confirmed") != (is_accessible is not None):
            raise ExamVenueError("Accessibility confirmation must include exactly one yes/no value")
        latitude = ExamVenuePolicy._optional_float(source["latitude"], "latitude", -90, 90)
        longitude = ExamVenuePolicy._optional_float(source["longitude"], "longitude", -180, 180)
        if (latitude is None) != (longitude is None):
            raise ExamVenueError("Latitude and longitude must be supplied together")
        coordinate_status = ExamVenuePolicy._choice(
            source["coordinate_status"], "coordinate_status", COORDINATE_STATUSES
        )
        coordinate_source = ExamVenuePolicy._optional_text(source["coordinate_source"])
        if coordinate_status == "missing" and (
            latitude is not None or coordinate_source is not None
        ):
            raise ExamVenueError("Missing coordinates cannot have a value or source")
        if coordinate_status == "confirmed" and (latitude is None or coordinate_source is None):
            raise ExamVenueError("Confirmed coordinates need a position and source")
        return (
            {
                "scope": scope,
                "committee_id": committee_id,
                "name": ExamVenuePolicy._text(source["name"]),
                "normalized_name": normalize_venue_text(source["name"]),
                "street": ExamVenuePolicy._text(source["street"]),
                "postal_code": ExamVenuePolicy._text(source["postal_code"]),
                "city": ExamVenuePolicy._text(source["city"]),
                "country": ExamVenuePolicy._text(source["country"]),
                "site_name": ExamVenuePolicy._optional_text(source["site_name"]),
                "entrance": ExamVenuePolicy._optional_text(source["entrance"]),
                "travel_directions": ExamVenuePolicy._optional_text(source["travel_directions"]),
                "is_accessible": is_accessible,
                "accessibility_status": accessibility_status,
                "accessibility_notes": ExamVenuePolicy._optional_text(
                    source["accessibility_notes"]
                ),
                "latitude": latitude,
                "longitude": longitude,
                "coordinate_status": coordinate_status,
                "coordinate_source": coordinate_source,
                "is_active": ExamVenuePolicy._boolean(source["is_active"], "is_active"),
            },
            reason,
        )

    @staticmethod
    def coordinate_status_after_address_change(
        values: dict[str, object], before: Mapping[str, object], supplied_fields: set[str]
    ) -> bool:
        address_fields = ("street", "postal_code", "city", "country")
        coordinate_fields = {"latitude", "longitude", "coordinate_status", "coordinate_source"}
        if (
            any(values[field] != before.get(field) for field in address_fields)
            and not coordinate_fields.intersection(supplied_fields)
            and values["latitude"] is not None
        ):
            values["coordinate_status"] = "needs_review"
            return True
        return False

    @staticmethod
    def assert_venue_can_be_active(values: Mapping[str, object], *, has_active_room: bool) -> None:
        required = (
            values["name"],
            values["street"],
            values["postal_code"],
            values["city"],
            values["country"],
        )
        if not all(str(value).strip() for value in required):
            raise ExamVenueError("An active venue needs a complete address")
        if values["accessibility_status"] != "confirmed" or values["is_accessible"] is None:
            raise ExamVenueError("An active venue needs confirmed accessibility")
        if not has_active_room:
            raise ExamVenueError("An active venue needs an active room")

    @staticmethod
    def assert_new_venue_is_inactive(values: Mapping[str, object]) -> None:
        if values["is_active"]:
            raise ExamVenueError("A venue must be created inactive before its first room exists")

    @staticmethod
    def assert_room_can_be_deactivated(
        *, venue_active: bool, room_active: bool, has_another_active_room: bool
    ) -> None:
        if venue_active and room_active and not has_another_active_room:
            raise ExamVenueError("An active venue needs an active room")

    @staticmethod
    def venue_source(
        current: Mapping[str, object] | None, command: Mapping[str, object]
    ) -> dict[str, object]:
        source: dict[str, object] = {
            "scope": None,
            "committee_id": None,
            "name": "",
            "street": "",
            "postal_code": "",
            "city": "",
            "country": "Deutschland",
            "site_name": None,
            "entrance": None,
            "travel_directions": None,
            "is_accessible": None,
            "accessibility_status": "needs_clarification",
            "accessibility_notes": None,
            "latitude": None,
            "longitude": None,
            "coordinate_status": "missing",
            "coordinate_source": None,
            "is_active": 0,
        }
        if current is not None:
            source.update({field: current[field] for field in VENUE_FIELDS})
        source.update(command)
        return source

    @staticmethod
    def _command(
        payload: Mapping[str, object], allowed: frozenset[str]
    ) -> tuple[dict[str, object], str | None]:
        unknown = set(payload) - allowed - COMMAND_META_FIELDS
        if unknown:
            raise ExamVenueError("Unknown venue fields: " + ", ".join(sorted(unknown)))
        return (
            {field: payload[field] for field in allowed if field in payload},
            ExamVenuePolicy._optional_text(payload.get("reason")),
        )

    @staticmethod
    def _text(value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ExamVenueError("Text fields must be strings")
        return value.strip()

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = ExamVenuePolicy._text(value)
        return text or None

    @staticmethod
    def _choice(value: object, name: str, choices: frozenset[str]) -> str:
        if not isinstance(value, str) or value not in choices:
            raise ExamVenueError(f"{name} is invalid")
        return value

    @staticmethod
    def _boolean(value: object, name: str) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int) and value in {0, 1}:
            return value
        raise ExamVenueError(f"{name} must be a boolean")

    @staticmethod
    def _optional_boolean(value: object, name: str) -> int | None:
        return None if value is None else ExamVenuePolicy._boolean(value, name)

    @staticmethod
    def _optional_integer(value: object, name: str) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ExamVenueError(f"{name} must be an integer")
        return value

    @staticmethod
    def _optional_float(value: object, name: str, lower: float, upper: float) -> float | None:
        if value is None:
            return None
        if not isinstance(value, (float, int)) or isinstance(value, bool):
            raise ExamVenueError(f"{name} must be a number")
        parsed = float(value)
        if not lower <= parsed <= upper:
            raise ExamVenueError(f"{name} is out of range")
        return parsed


class ExamVenueService:
    """Apply Planning venue commands through an injected repository and geocoder."""

    def __init__(
        self,
        repository: VenueRepository,
        *,
        geocoder: Geocoder | None = None,
        follow_up: VenueChangeFollowUp | None = None,
        policy: ExamVenuePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.geocoder = geocoder
        self.follow_up = follow_up
        self.policy = policy or ExamVenuePolicy()

    def geocode(self, address: str) -> GeocodeCandidate:
        """Resolve one address through the Planning-owned provider port."""
        if self.geocoder is None:
            raise ExamVenueError("Geocoding is unavailable")
        return self.geocoder.geocode(address)

    def list_venues(self) -> list[dict[str, Any]]:
        return self._query(VenueQuery(VenueQueryKind.LIST_VENUES))

    def get_venue(self, venue_id: int) -> dict[str, Any] | None:
        return self._query(VenueQuery(VenueQueryKind.GET_VENUE, entity_id=venue_id))

    def address_label(self, venue_id: int) -> str | None:
        return self._query(VenueQuery(VenueQueryKind.ADDRESS_LABEL, entity_id=venue_id))

    def referenced_committee_ids(self, venue_id: int) -> frozenset[int]:
        return self._query(VenueQuery(VenueQueryKind.REFERENCED_COMMITTEES, entity_id=venue_id))

    def future_impact(
        self,
        venue_id: int,
        room_id: int | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        return self._query(
            VenueQuery(
                VenueQueryKind.FUTURE_IMPACT,
                entity_id=venue_id,
                room_id=room_id,
                values=payload,
            )
        )

    def find_duplicates(
        self,
        payload: Mapping[str, object],
        *,
        visible_venue_ids: frozenset[int] | None = None,
        excluded_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._query(
            VenueQuery(
                VenueQueryKind.FIND_DUPLICATES,
                values=payload,
                visible_venue_ids=visible_venue_ids,
                excluded_id=excluded_id,
            )
        )

    def request_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int,
        reason: str,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.REQUEST_PROMOTION,
                entity_id=venue_id,
                actor_member_id=actor_member_id,
                reason=reason,
                expected_revision=expected_revision,
            )
        ).value

    def list_pending_promotions(self) -> list[dict[str, Any]]:
        return self._query(VenueQuery(VenueQueryKind.LIST_PENDING_PROMOTIONS))

    def decide_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        decision: str,
        reason: str,
        technical_actor: str,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DECIDE_PROMOTION,
                entity_id=venue_id,
                technical_actor=technical_actor,
                reason=reason,
                decision=decision,
                expected_revision=expected_revision,
            )
        ).value

    def create_venue(
        self,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_VENUE,
                values=payload,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_venue(
        self,
        venue_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        values = dict(payload)
        revision = values.pop("expected_revision", None)
        if not isinstance(revision, int):
            raise ExamVenueError("Expected venue revision is required")
        result = self._execute(
            VenueCommand(
                VenueCommandKind.UPDATE_VENUE,
                entity_id=venue_id,
                values=values,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                expected_revision=revision,
            )
        )
        return result.value

    def delete_venue(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_VENUE,
                entity_id=venue_id,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                reason=reason,
                expected_revision=expected_revision,
            )
        ).value

    def create_room(
        self,
        venue_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_ROOM,
                entity_id=venue_id,
                values=payload,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_room(
        self,
        room_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        values = dict(payload)
        revision = values.pop("expected_revision", None)
        if not isinstance(revision, int):
            raise ExamVenueError("Expected room revision is required")
        return self._execute(
            VenueCommand(
                VenueCommandKind.UPDATE_ROOM,
                entity_id=room_id,
                values=values,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                expected_revision=revision,
            )
        ).value

    def delete_room(
        self,
        room_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_ROOM,
                entity_id=room_id,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                reason=reason,
                expected_revision=expected_revision,
            )
        ).value

    def create_contact(
        self,
        venue_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_CONTACT,
                entity_id=venue_id,
                values=payload,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_contact(
        self,
        contact_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        values = dict(payload)
        revision = values.pop("expected_revision", None)
        if not isinstance(revision, int):
            raise ExamVenueError("Expected contact revision is required")
        return self._execute(
            VenueCommand(
                VenueCommandKind.UPDATE_CONTACT,
                entity_id=contact_id,
                values=values,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                expected_revision=revision,
            )
        ).value

    def delete_contact(
        self,
        contact_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_CONTACT,
                entity_id=contact_id,
                actor_member_id=actor_member_id,
                technical_actor=technical_actor,
                reason=reason,
                expected_revision=expected_revision,
            )
        ).value

    def _query(self, query: VenueQuery):
        return self.repository.query(query).value

    def execute(self, command: VenueCommand) -> VenueCommandResult:
        """Return the detached mutation result and committed follow-up basis."""
        result = self.repository.execute(command)
        change = result.change
        if change is None or not change.changed_fields or self.follow_up is None:
            return result
        try:
            follow_up = self.follow_up.process(change)
        except Exception:
            value = {
                **result.value,
                "consequence_audit_id": change.audit_id,
                "consequence_warning": (
                    "Die Stammdaten wurden gespeichert, aber Kalender- oder "
                    "Benachrichtigungsfolgen konnten nicht vollständig verarbeitet werden."
                ),
            }
        else:
            value = {
                **result.value,
                "consequence_audit_id": change.audit_id,
                "consequence_status": dict(follow_up),
            }
            status = value["consequence_status"]
            if status.get("problems") or status.get("pending"):
                value["consequence_warning"] = (
                    "Die Stammdaten wurden gespeichert, aber mindestens eine "
                    "Kalender- oder Benachrichtigungsfolge ist noch offen."
                )
        return VenueCommandResult(value, change)

    def _execute(self, command: VenueCommand) -> VenueCommandResult:
        return self.execute(command)
