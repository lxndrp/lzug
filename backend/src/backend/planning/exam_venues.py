"""Planning-owned exam-venue rules and typed repository commands."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

from backend.planning_ports import (
    ACCESSIBILITY_STATUSES,
    COMMAND_META_FIELDS,
    CONTACT_FIELDS,
    COORDINATE_STATUSES,
    ROOM_FIELDS,
    VENUE_DUPLICATE_FIELDS,
    VENUE_FIELDS,
    VENUE_SCOPES,
    ExamVenueAccessDeniedError,
    ExamVenueConfirmationRequiredError,
    ExamVenueConflictError,
    ExamVenueError,
    GeocodeCandidate,
    Geocoder,
    VenueChangeFollowUp,
    VenueCommand,
    VenueCommandFacts,
    VenueCommandKind,
    VenueCommandResult,
    VenueFutureImpactFacts,
    VenueGeocodingAddress,
    VenueImpactQuery,
    VenueMutationPlan,
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
    def room_values(
        payload: Mapping[str, object], current: Mapping[str, object] | None = None
    ) -> tuple[dict[str, object], str | None]:
        command, reason = ExamVenuePolicy._command(payload, ROOM_FIELDS)
        source = {
            field: command.get(
                field,
                current.get(field) if current else (1 if field == "is_active" else None),
            )
            for field in ROOM_FIELDS
        }
        name = ExamVenuePolicy._text(source["name"])
        if not name:
            raise ExamVenueError("Room name is required")
        capacity = ExamVenuePolicy._optional_integer(source["capacity"], "capacity")
        if capacity is not None and capacity <= 0:
            raise ExamVenueError("Room capacity must be positive")
        return (
            {
                "name": name,
                "normalized_name": normalize_venue_text(name),
                "building": ExamVenuePolicy._optional_text(source["building"]),
                "wing": ExamVenuePolicy._optional_text(source["wing"]),
                "floor": ExamVenuePolicy._optional_text(source["floor"]),
                "room_number": ExamVenuePolicy._optional_text(source["room_number"]),
                "access_notes": ExamVenuePolicy._optional_text(source["access_notes"]),
                "capacity": capacity,
                "is_active": ExamVenuePolicy._boolean(source["is_active"], "is_active"),
            },
            reason,
        )

    @staticmethod
    def contact_values(
        payload: Mapping[str, object], current: Mapping[str, object] | None = None
    ) -> tuple[dict[str, object], tuple[int, ...] | None, str | None]:
        command, reason = ExamVenuePolicy._command(payload, CONTACT_FIELDS)
        source = {
            field: command.get(
                field,
                current.get(field) if current else (1 if field == "is_active" else None),
            )
            for field in CONTACT_FIELDS - {"room_ids"}
        }
        label = ExamVenuePolicy._text(source["label"])
        if not label:
            raise ExamVenueError("Contact label is required")
        values = {
            "label": label,
            "role": ExamVenuePolicy._optional_text(source["role"]),
            "phone": ExamVenuePolicy._optional_text(source["phone"]),
            "email": ExamVenuePolicy._optional_text(source["email"]),
            "availability_notes": ExamVenuePolicy._optional_text(source["availability_notes"]),
            "is_active": ExamVenuePolicy._boolean(source["is_active"], "is_active"),
        }
        if not any(values[field] for field in ("phone", "email", "availability_notes")):
            raise ExamVenueError("A contact needs phone, email, or availability information")
        room_ids = ExamVenuePolicy._room_ids(command["room_ids"]) if "room_ids" in command else None
        return values, room_ids, reason

    @staticmethod
    def assert_contact_rooms_belong_to_venue(
        venue_id: int, room_ids: tuple[int, ...], room_venue_ids: Mapping[int, int]
    ) -> None:
        if any(room_venue_ids.get(room_id) != venue_id for room_id in room_ids):
            raise ExamVenueError("A contact can only reference rooms at its own venue")

    @staticmethod
    def assert_duplicate_confirmation(
        values: Mapping[str, object],
        payload: Mapping[str, object],
        duplicate_candidates: tuple[Mapping[str, object], ...],
        *,
        creating: bool,
    ) -> None:
        relevant_change = creating or bool(VENUE_DUPLICATE_FIELDS.intersection(payload))
        if not relevant_change:
            return
        candidates_for_review = tuple(
            candidate
            for candidate in duplicate_candidates
            if not (
                candidate.get("normalized_name") == values.get("normalized_name")
                and candidate.get("scope") == values.get("scope")
                and (
                    values.get("scope") != "committee"
                    or candidate.get("committee_id") == values.get("committee_id")
                )
            )
        )
        matches = ExamVenuePolicy.duplicate_matches(
            values, candidates_for_review, restrict_scope=True
        )
        if not matches:
            return
        if payload.get("duplicates_reviewed") is not True:
            raise ExamVenueConfirmationRequiredError("Duplicate candidates must be reviewed")
        if values["scope"] == "committee" and any(
            candidate["scope"] == "global" for candidate in matches
        ):
            if not ExamVenuePolicy._optional_text(payload.get("duplicate_reason")):
                raise ExamVenueConfirmationRequiredError(
                    "A committee venue similar to a global venue needs a reason"
                )

    @staticmethod
    def assert_future_impact_confirmation(
        changed_fields: set[str],
        payload: Mapping[str, object],
        has_future_confirmed_assignments: bool,
    ) -> None:
        if (
            changed_fields
            and has_future_confirmed_assignments
            and payload.get("confirm_future_assignments") is not True
        ):
            raise ExamVenueConfirmationRequiredError(
                "Future confirmed appointments must be reviewed and confirmed"
            )

    @staticmethod
    def assert_no_global_promotion_collision(
        values: Mapping[str, object], duplicate_candidates: tuple[Mapping[str, object], ...]
    ) -> None:
        matches = ExamVenuePolicy.duplicate_matches(
            values, duplicate_candidates, restrict_scope=True
        )
        if any(candidate["scope"] == "global" for candidate in matches):
            raise ExamVenueConflictError("A colliding global venue prevents promotion")

    @staticmethod
    def duplicate_matches(
        values: Mapping[str, object],
        candidates: tuple[Mapping[str, object], ...],
        *,
        restrict_scope: bool,
    ) -> list[dict[str, object]]:
        normalized_name = normalize_venue_text(values.get("name"))
        normalized_address = ExamVenuePolicy.normalized_address(values)
        matches: list[dict[str, object]] = []
        for candidate in candidates:
            if (
                restrict_scope
                and values.get("scope") == "global"
                and candidate.get("scope") != "global"
            ):
                continue
            if (
                restrict_scope
                and values.get("scope") == "committee"
                and candidate.get("scope") == "committee"
                and candidate.get("committee_id") != values.get("committee_id")
            ):
                continue
            name_score = SequenceMatcher(
                None, normalized_name, str(candidate.get("normalized_name") or "")
            ).ratio()
            same_address = normalized_address == ExamVenuePolicy.normalized_address(candidate)
            if name_score < 0.9 and not same_address:
                continue
            matches.append(
                {
                    **dict(candidate),
                    "same_address": same_address,
                    "name_similarity": round(name_score, 2),
                }
            )
        return matches

    @staticmethod
    def normalized_address(source: Mapping[str, object]) -> str:
        return "|".join(
            normalize_venue_text(source.get(field))
            for field in ("street", "postal_code", "city", "country")
        )

    @staticmethod
    def _room_ids(value: object) -> tuple[int, ...]:
        if not isinstance(value, (tuple, list)):
            raise ExamVenueError("room_ids must be an array")
        identifiers: list[int] = []
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool) or item < 1:
                raise ExamVenueError("room_ids must contain positive integers")
            identifiers.append(item)
        if len(set(identifiers)) != len(identifiers):
            raise ExamVenueError("room_ids must not contain duplicates")
        return tuple(sorted(identifiers))

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

    @staticmethod
    def _required_choice(value: object, name: str, choices: frozenset[str]) -> str:
        return ExamVenuePolicy._choice(value, name, choices)


class ExamVenueService:
    """Apply Planning venue commands through an injected repository and geocoder."""

    def __init__(
        self,
        repository: VenueRepository,
        *,
        geocoder: Geocoder | None = None,
        follow_up: VenueChangeFollowUp | None = None,
        impact_query: VenueImpactQuery | None = None,
        policy: ExamVenuePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.geocoder = geocoder
        self.follow_up = follow_up
        self.impact_query = impact_query
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

    def geocoding_address(self, venue_id: int, expected_revision: int) -> str | None:
        """Return an address only when its detached snapshot has the requested revision."""
        snapshot = self._query(
            VenueQuery(
                VenueQueryKind.GEOCODING_ADDRESS,
                entity_id=venue_id,
                expected_revision=expected_revision,
            )
        )
        if snapshot is None:
            return None
        if not isinstance(snapshot, VenueGeocodingAddress):
            raise TypeError("Geocoding address query returned invalid facts")
        if snapshot.revision != expected_revision:
            raise ExamVenueConflictError("Venue data revision is stale")
        if not snapshot.address:
            raise ExamVenueError("A complete address is required for geocoding")
        return snapshot.address

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
        actor_person_id: int | None = None,
        reason: str,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.REQUEST_PROMOTION,
                entity_id=venue_id,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_VENUE,
                values=payload,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_venue(
        self,
        venue_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        actor_person_id: int | None = None,
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
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_VENUE,
                entity_id=venue_id,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_ROOM,
                entity_id=venue_id,
                values=payload,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_room(
        self,
        room_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        actor_person_id: int | None = None,
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
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_ROOM,
                entity_id=room_id,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            VenueCommand(
                VenueCommandKind.CREATE_CONTACT,
                entity_id=venue_id,
                values=payload,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
                technical_actor=technical_actor,
            )
        ).value

    def update_contact(
        self,
        contact_id: int,
        payload: Mapping[str, object],
        *,
        actor_member_id: int | None = None,
        actor_person_id: int | None = None,
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
                actor_person_id=actor_person_id,
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
        actor_person_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        return self._execute(
            VenueCommand(
                VenueCommandKind.DELETE_CONTACT,
                entity_id=contact_id,
                actor_member_id=actor_member_id,
                actor_person_id=actor_person_id,
                technical_actor=technical_actor,
                reason=reason,
                expected_revision=expected_revision,
            )
        ).value

    def _query(self, query: VenueQuery):
        raw = self.repository.query(query).value
        if query.kind == VenueQueryKind.FIND_DUPLICATES:
            plan = self.plan_query(
                query,
                VenueCommandFacts(duplicate_candidates=tuple(raw)),
            )
            return list(plan.values["matches"])
        if query.kind == VenueQueryKind.FUTURE_IMPACT:
            if not isinstance(raw, VenueFutureImpactFacts):
                raise TypeError("Future impact query returned invalid facts")
            plan = self.plan_query(query, VenueCommandFacts(current=raw.current))
            if self.impact_query is None:
                raise RuntimeError("Planning venue impact query must be injected by composition")
            return self.impact_query.preview(
                venue_id=raw.venue_id,
                entity_type=raw.entity_type,
                entity_id=raw.entity_id,
                before=dict(raw.before),
                after=dict(plan.values),
                meaningful_change=(query.values or {}).get("meaningful_change", True) is not False,
            )
        return raw

    def execute(self, command: VenueCommand) -> VenueCommandResult:
        """Return the detached mutation result and committed follow-up basis."""
        with self.repository.write_uow(command) as unit_of_work:
            facts = unit_of_work.facts()
            plan = self.plan(command, facts)
            result = unit_of_work.commit(plan)
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

    def plan(self, command: VenueCommand, facts: VenueCommandFacts) -> VenueMutationPlan:
        """Build a validated mutation plan from facts read inside the adapter UoW."""
        values = dict(command.values or {})
        self._assert_current_committee_actor(command, facts)
        match command.kind:
            case VenueCommandKind.CREATE_VENUE | VenueCommandKind.UPDATE_VENUE:
                normalized, reason = self.policy.venue_values(values, facts.current)
                audit_values = dict(values)
                if command.kind == VenueCommandKind.CREATE_VENUE:
                    self.policy.assert_new_venue_is_inactive(normalized)
                else:
                    if facts.current is None:
                        return VenueMutationPlan({}, audit_values=values)
                    if self.policy.coordinate_status_after_address_change(
                        normalized, facts.current, set(values)
                    ):
                        audit_values["coordinate_status"] = "needs_review"
                    if normalized["is_active"]:
                        self.policy.assert_venue_can_be_active(
                            normalized, has_active_room=facts.has_active_room
                        )
                if facts.duplicate_candidates is not None:
                    self.policy.assert_duplicate_confirmation(
                        normalized,
                        values,
                        facts.duplicate_candidates,
                        creating=command.kind == VenueCommandKind.CREATE_VENUE,
                    )
                if facts.has_future_confirmed_assignments is not None:
                    changed_fields = (
                        {
                            field
                            for field in VENUE_FIELDS
                            if facts.current is not None
                            and facts.current.get(field) != normalized[field]
                        }
                        if command.kind == VenueCommandKind.UPDATE_VENUE
                        else set()
                    )
                    self.policy.assert_future_impact_confirmation(
                        changed_fields, values, facts.has_future_confirmed_assignments
                    )
                return VenueMutationPlan(normalized, reason, audit_values)
            case VenueCommandKind.CREATE_ROOM | VenueCommandKind.UPDATE_ROOM:
                if command.kind == VenueCommandKind.UPDATE_ROOM and facts.current is None:
                    return VenueMutationPlan({})
                normalized, reason = self.policy.room_values(values, facts.current)
                if (
                    command.kind == VenueCommandKind.UPDATE_ROOM
                    and facts.room_active
                    and not normalized["is_active"]
                ):
                    self.policy.assert_room_can_be_deactivated(
                        venue_active=facts.venue_active,
                        room_active=facts.room_active,
                        has_another_active_room=facts.has_another_active_room,
                    )
                if facts.has_future_confirmed_assignments is not None:
                    changed_fields = {
                        field
                        for field in ROOM_FIELDS
                        if facts.current is not None
                        and facts.current.get(field) != normalized[field]
                    }
                    self.policy.assert_future_impact_confirmation(
                        changed_fields, values, facts.has_future_confirmed_assignments
                    )
                return VenueMutationPlan(normalized, reason, values)
            case VenueCommandKind.DELETE_ROOM:
                self.policy.assert_room_can_be_deactivated(
                    venue_active=facts.venue_active,
                    room_active=facts.room_active,
                    has_another_active_room=facts.has_another_active_room,
                )
                return VenueMutationPlan({}, command.reason)
            case VenueCommandKind.CREATE_CONTACT | VenueCommandKind.UPDATE_CONTACT:
                if command.kind == VenueCommandKind.UPDATE_CONTACT and facts.current is None:
                    return VenueMutationPlan({})
                normalized, room_ids, reason = self.policy.contact_values(values, facts.current)
                if room_ids is not None:
                    if facts.venue_id is None or facts.room_venue_ids is None:
                        raise ExamVenueError("Contact room ownership facts are unavailable")
                    self.policy.assert_contact_rooms_belong_to_venue(
                        facts.venue_id, room_ids, facts.room_venue_ids
                    )
                return VenueMutationPlan(normalized, reason, values, room_ids)
            case VenueCommandKind.REQUEST_PROMOTION:
                if facts.current is None:
                    return VenueMutationPlan({})
                if facts.current.get("scope") != "committee":
                    raise ExamVenueError("Only committee venues can be promoted")
                if facts.promotion_status == "pending":
                    raise ExamVenueConflictError("A promotion request is already pending")
                request_reason = self.policy._optional_text(command.reason)
                if not request_reason:
                    raise ExamVenueError("A promotion request needs a reason")
                return VenueMutationPlan({}, request_reason)
            case VenueCommandKind.DECIDE_PROMOTION:
                if facts.promotion_status != "pending":
                    raise ExamVenueConflictError("No pending promotion request exists")
                decision = command.decision or ""
                if decision not in {"approve", "reject"}:
                    raise ExamVenueError("Promotion decision must be approve or reject")
                decision_reason = self.policy._optional_text(command.reason)
                if not decision_reason:
                    raise ExamVenueError("A promotion decision needs a reason")
                if facts.current is None:
                    return VenueMutationPlan({})
                if decision == "approve":
                    normalized = self.policy.venue_source(
                        facts.current, {"scope": "global", "committee_id": None}
                    )
                    self.policy.assert_venue_can_be_active(
                        normalized, has_active_room=facts.has_active_room
                    )
                    if facts.duplicate_candidates is not None:
                        self.policy.assert_no_global_promotion_collision(
                            normalized, facts.duplicate_candidates
                        )
                    return VenueMutationPlan(normalized, decision_reason, values)
                return VenueMutationPlan({}, decision_reason, values)
            case _:
                return VenueMutationPlan({}, command.reason, values)

    @staticmethod
    def _assert_current_committee_actor(command: VenueCommand, facts: VenueCommandFacts) -> None:
        """Bind committee authorization to current membership and venue facts."""
        if command.actor_member_id is None:
            return
        if command.kind == VenueCommandKind.CREATE_VENUE:
            values = command.values or {}
            if values.get("scope") == "global" and values.get("committee_id") is None:
                raise ExamVenueAccessDeniedError("Forbidden.")
            if values.get("scope") != "committee":
                # Invalid scope/committee combinations retain their validation error.
                return
            committee_id = values.get("committee_id")
        elif facts.venue_scope == "committee":
            committee_id = facts.venue_committee_id
        elif facts.venue_scope == "global":
            raise ExamVenueAccessDeniedError("Forbidden.")
        else:
            # Missing aggregates retain their established not-found/no-op handling.
            return

        actor = facts.actor
        if (
            actor is None
            or actor.member_id != command.actor_member_id
            or not actor.is_active
            or actor.committee_role not in {"chair", "deputy_chair"}
            or actor.committee_id != committee_id
            or (command.actor_person_id is not None and actor.person_id != command.actor_person_id)
        ):
            raise ExamVenueAccessDeniedError("Forbidden.")

    def plan_query(self, query: VenueQuery, facts: VenueCommandFacts) -> VenueMutationPlan:
        """Prepare proposed venue values for a query without adapter-owned rules."""
        values = dict(query.values or {})
        if query.kind == VenueQueryKind.FIND_DUPLICATES:
            source = self.policy.venue_source(None, values)
            matches = self.policy.duplicate_matches(
                source, facts.duplicate_candidates or (), restrict_scope=False
            )
            return VenueMutationPlan({"matches": matches})
        if query.room_id is not None:
            normalized, reason = self.policy.room_values(values, facts.current)
        else:
            normalized, reason = self.policy.venue_values(values, facts.current)
            if facts.current is not None:
                self.policy.coordinate_status_after_address_change(
                    normalized, facts.current, set(values)
                )
        return VenueMutationPlan(normalized, reason)

    def _execute(self, command: VenueCommand) -> VenueCommandResult:
        return self.execute(command)
