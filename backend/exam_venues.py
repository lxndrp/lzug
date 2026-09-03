"""Venue master-data persistence and planning eligibility rules.

This module deliberately keeps the venue aggregate outside the generic resource
repository.  Venue, room, and contact updates have optimistic revisions,
append-only audit records, and cross-entity invariants that do not belong in
generic CRUD helpers.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import DEFAULT_DB_PATH, session_scope
from .map_provider import planning_requires_confirmed_coordinates
from .models import (
    EXAM_ROOM,
    EXAM_VENUE,
    EXAM_VENUE_CONTACT,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamRoom,
    ExamRound,
    ExamVenue,
    ExamVenueAuditEvent,
    ExamVenueContact,
    ExamVenueContactRoom,
    LegacyLocationRoomMapping,
    PlanningSettings,
    model_to_dict,
)


class ExamVenueError(ValueError):
    """Base error for a rejected venue-master-data command."""


class ExamVenueConflictError(ExamVenueError):
    """Signal a stale revision or a conflicting uniqueness invariant."""


class ExamVenueNotFoundError(ExamVenueError):
    """Signal an absent venue aggregate entity."""


class ExamVenueInUseError(ExamVenueError):
    """Signal an entity that still has durable planning or migration references."""


class ExamVenueConfirmationRequiredError(ExamVenueError):
    """Signal that a visible impact or duplicate warning needs confirmation."""


VENUE_SCOPES = frozenset({"global", "committee"})
ACCESSIBILITY_STATUSES = frozenset({"confirmed", "needs_clarification"})
COORDINATE_STATUSES = frozenset({"missing", "confirmed", "needs_review"})
VENUE_FIELDS = frozenset(
    {
        "scope",
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
        "latitude",
        "longitude",
        "coordinate_status",
        "coordinate_source",
        "is_active",
    }
)
ROOM_FIELDS = frozenset(
    {
        "name",
        "building",
        "wing",
        "floor",
        "room_number",
        "access_notes",
        "capacity",
        "is_active",
    }
)
CONTACT_FIELDS = frozenset(
    {"label", "role", "phone", "email", "availability_notes", "is_active", "room_ids"}
)
COMMAND_META_FIELDS = frozenset(
    {
        "reason",
        "duplicates_reviewed",
        "duplicate_reason",
        "confirm_future_assignments",
        "meaningful_change",
    }
)
VENUE_DUPLICATE_FIELDS = frozenset({"name", "street", "postal_code", "city", "country"})


def normalize_venue_text(value: object) -> str:
    """Return the exact-match key used for names and migration grouping."""
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split()).casefold()


def room_is_usable_for_committee(session: Session, room_id: int, committee_id: int) -> bool:
    """Return whether a room is active and selectable by this committee's new plan."""
    room = session.get(ExamRoom, room_id)
    if room is None or not room.is_active:
        return False
    venue = session.get(ExamVenue, room.venue_id)
    return bool(
        venue
        and venue.is_active
        and (venue.scope == "global" or venue.committee_id == committee_id)
        and (
            not planning_requires_confirmed_coordinates() or venue.coordinate_status == "confirmed"
        )
    )


class ExamVenueService:
    """Create and mutate the venue aggregate in one transaction per command."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def list_venues(self) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            venues = session.scalars(
                select(ExamVenue).order_by(ExamVenue.is_active.desc(), ExamVenue.name, ExamVenue.id)
            ).all()
            return [self._venue_payload(session, venue) for venue in venues]

    def get_venue(self, venue_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            return self._venue_payload(session, venue) if venue else None

    def address_label(self, venue_id: int) -> str | None:
        """Return the address only for the authorized explicit geocoding command."""
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            return self._address_label(vars(venue)) if venue else None

    def referenced_committee_ids(self, venue_id: int) -> frozenset[int]:
        """Return committees with a durable plan reference to this venue."""
        with session_scope(self.db_path) as session:
            rows = session.execute(
                select(ExamRound.committee_id)
                .join(ExamDay, ExamDay.exam_round_id == ExamRound.id)
                .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
                .where(ExamRoom.venue_id == venue_id)
                .distinct()
            ).scalars()
            return frozenset(rows)

    def future_impact(
        self,
        venue_id: int,
        room_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Summarize assignments and field-specific effects before a change."""
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            room = session.get(ExamRoom, room_id) if room_id is not None else None
            if venue is None or (
                room_id is not None and (room is None or room.venue_id != venue_id)
            ):
                raise ExamVenueNotFoundError("Exam venue entity not found")
            command = dict(payload or {})
            expected = command.pop("expected_revision", None)
            entity = room if room is not None else venue
            if expected is not None:
                self._assert_revision(entity.revision, expected)
            if room is not None:
                after, _reason = self._room_values(command, current=room)
                fields = ROOM_FIELDS
                entity_type = "room"
            else:
                after, _reason = self._venue_values(command, current=venue)
                if any(
                    after[field] != getattr(venue, field)
                    for field in ("street", "postal_code", "city", "country")
                ) and not {
                    "latitude",
                    "longitude",
                    "coordinate_status",
                    "coordinate_source",
                }.intersection(
                    command
                ):
                    if after["latitude"] is not None:
                        after["coordinate_status"] = "needs_review"
                fields = VENUE_FIELDS
                entity_type = "venue"
            before = {field: getattr(entity, field) for field in fields}
            resolved_entity_id = entity.id
        from .venue_consequences import VenueConsequenceService

        return VenueConsequenceService(self.db_path).preview(
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=resolved_entity_id,
            before=before,
            after=after,
            meaningful_change=command.get("meaningful_change", True) is not False,
        )

    def find_duplicates(
        self,
        payload: dict[str, Any],
        *,
        visible_venue_ids: frozenset[int] | None = None,
        excluded_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return non-blocking duplicate candidates without exposing hidden venues."""
        source = self._venue_source(None, payload)
        normalized_name = normalize_venue_text(source["name"])
        normalized_address = self._normalized_address(source)
        if not normalized_name and not normalized_address:
            return []
        matches: list[dict[str, Any]] = []
        with session_scope(self.db_path) as session:
            for venue in session.scalars(select(ExamVenue).order_by(ExamVenue.id)):
                if venue.id == excluded_id:
                    continue
                if visible_venue_ids is not None and venue.id not in visible_venue_ids:
                    continue
                name_score = SequenceMatcher(None, normalized_name, venue.normalized_name).ratio()
                address_match = normalized_address == self._normalized_address(vars(venue))
                if name_score < 0.9 and not address_match:
                    continue
                matches.append(
                    {
                        "id": venue.id,
                        "scope": venue.scope,
                        "committee_id": venue.committee_id,
                        "name": venue.name,
                        "address": self._address_label(vars(venue)),
                        "same_address": address_match,
                        "name_similarity": round(name_score, 2),
                    }
                )
        return matches

    def request_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int,
        reason: str,
    ) -> dict[str, Any]:
        """Record one pending request without changing venue visibility."""
        with session_scope(self.db_path) as session:
            self._require_actor(session, actor_member_id, None)
            venue = self._venue_or_raise(session, venue_id)
            self._assert_revision(venue.revision, expected_revision)
            if venue.scope != "committee":
                raise ExamVenueError("Only committee venues can be promoted")
            if self._promotion_status(session, venue.id) == "pending":
                raise ExamVenueConflictError("A promotion request is already pending")
            request_reason = self._text(reason)
            if not request_reason:
                raise ExamVenueError("A promotion request needs a reason")
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="promotion_requested",
                actor_member_id=actor_member_id,
                technical_actor=None,
                reason=request_reason,
                fields={"scope": venue.scope, "committee_id": venue.committee_id},
            )
            return self._promotion_payload(session, venue)

    def list_pending_promotions(self) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            return [
                self._promotion_payload(session, venue)
                for venue in session.scalars(
                    select(ExamVenue).order_by(ExamVenue.name, ExamVenue.id)
                )
                if venue.scope == "committee"
                and self._promotion_status(session, venue.id) == "pending"
            ]

    def decide_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        decision: str,
        reason: str,
        technical_actor: str,
    ) -> dict[str, Any]:
        """Approve or reject a pending promotion while preserving the venue identity."""
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, None, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            self._assert_revision(venue.revision, expected_revision)
            if self._promotion_status(session, venue.id) != "pending":
                raise ExamVenueConflictError("No pending promotion request exists")
            if decision not in {"approve", "reject"}:
                raise ExamVenueError("Promotion decision must be approve or reject")
            decision_reason = self._text(reason)
            if not decision_reason:
                raise ExamVenueError("A promotion decision needs a reason")
            if decision == "approve":
                values = self._venue_source(venue, {"scope": "global", "committee_id": None})
                self._assert_venue_can_be_active(session, venue.id, values)
                collisions = self._duplicate_matches(session, values, excluded_id=venue.id)
                if any(item.scope == "global" for item in collisions):
                    raise ExamVenueConflictError("A colliding global venue prevents promotion")
                venue.scope = "global"
                venue.committee_id = None
                venue.revision += 1
                session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type=f"promotion_{'approved' if decision == 'approve' else 'rejected'}",
                actor_member_id=None,
                technical_actor=actor[1],
                reason=decision_reason,
                fields={"decision": decision},
            )
            return self._venue_payload(session, venue)

    def create_venue(
        self,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        values, reason = self._venue_values(payload, current=None)
        duplicate_reason = self._optional_text(payload.get("duplicate_reason"))
        if values["is_active"]:
            raise ExamVenueError("A venue must be created inactive before its first room exists")
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            self._assert_venue_name_available(
                session,
                values["scope"],
                values["committee_id"],
                values["normalized_name"],
            )
            self._assert_duplicate_confirmation(session, values, payload)
            venue = ExamVenue(**values)
            session.add(venue)
            session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason or duplicate_reason,
                fields={
                    **values,
                    "duplicates_reviewed": payload.get("duplicates_reviewed") is True,
                    **(
                        {"duplicate_reason": duplicate_reason}
                        if duplicate_reason is not None
                        else {}
                    ),
                },
            )
            session.flush()
            return self._venue_payload(session, venue)

    def update_venue(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        expected_revision, command = self._expected_revision(payload)
        audit_id: int | None = None
        changed_fields: set[str] = set()
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = session.get(ExamVenue, venue_id)
            if venue is None:
                return None
            self._assert_revision(venue.revision, expected_revision)
            values, reason = self._venue_values(command, current=venue)
            address_changed = any(
                values[field] != getattr(venue, field)
                for field in ("street", "postal_code", "city", "country")
            )
            coordinates_supplied = bool(
                {"latitude", "longitude", "coordinate_status", "coordinate_source"}.intersection(
                    command
                )
            )
            if address_changed and not coordinates_supplied and values["latitude"] is not None:
                values["coordinate_status"] = "needs_review"
                command["coordinate_status"] = "needs_review"
            duplicate_reason = self._optional_text(command.get("duplicate_reason"))
            self._assert_venue_name_available(
                session,
                values["scope"],
                values["committee_id"],
                values["normalized_name"],
                excluded_id=venue.id,
            )
            self._assert_duplicate_confirmation(session, values, command, excluded_id=venue.id)
            if values["is_active"]:
                self._assert_venue_can_be_active(session, venue.id, values)
            was_active = bool(venue.is_active)
            before = {field: getattr(venue, field) for field in VENUE_FIELDS}
            changed_fields = {field for field in VENUE_FIELDS if before[field] != values[field]}
            self._assert_future_impact_confirmation(
                session, venue.id, None, changed_fields, command
            )
            for field, value in values.items():
                setattr(venue, field, value)
            venue.revision += 1
            session.flush()
            audit_id = self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type=self._change_type(was_active, bool(venue.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason or duplicate_reason,
                fields=command,
                before=before,
                after={field: getattr(venue, field) for field in VENUE_FIELDS},
                changed_fields=changed_fields,
                meaningful_change=command.get("meaningful_change", True) is not False,
            )
            session.flush()
            result = self._venue_payload(session, venue)
        return self._apply_consequences(result, audit_id, changed_fields)

    def delete_venue(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = session.get(ExamVenue, venue_id)
            if venue is None:
                return False
            self._assert_revision(venue.revision, expected_revision)
            if session.scalar(select(ExamRoom.id).where(ExamRoom.venue_id == venue.id).limit(1)):
                raise ExamVenueInUseError("Delete rooms before deleting a venue")
            if session.scalar(
                select(ExamVenueContact.id).where(ExamVenueContact.venue_id == venue.id).limit(1)
            ):
                raise ExamVenueInUseError("Delete contacts before deleting a venue")
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(venue)
            return True

    def create_room(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        values, reason = self._room_values(payload, current=None)
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            self._assert_room_name_available(session, venue.id, values["normalized_name"])
            room = ExamRoom(venue_id=venue.id, **values)
            session.add(room)
            session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=values,
            )
            session.flush()
            return self._room_payload(room)

    def update_room(
        self,
        room_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        expected_revision, command = self._expected_revision(payload)
        audit_id: int | None = None
        changed_fields: set[str] = set()
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            room = session.get(ExamRoom, room_id)
            if room is None:
                return None
            self._assert_revision(room.revision, expected_revision)
            values, reason = self._room_values(command, current=room)
            self._assert_room_name_available(
                session, room.venue_id, values["normalized_name"], room.id
            )
            was_active = bool(room.is_active)
            if was_active and not values["is_active"]:
                self._assert_room_can_be_deactivated(session, room)
            before = {field: getattr(room, field) for field in ROOM_FIELDS}
            changed_fields = {field for field in ROOM_FIELDS if before[field] != values[field]}
            self._assert_future_impact_confirmation(
                session, room.venue_id, room.id, changed_fields, command
            )
            for field, value in values.items():
                setattr(room, field, value)
            room.revision += 1
            session.flush()
            audit_id = self._audit(
                session,
                venue_id=room.venue_id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type=self._change_type(was_active, bool(room.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=command,
                before=before,
                after={field: getattr(room, field) for field in ROOM_FIELDS},
                changed_fields=changed_fields,
                meaningful_change=command.get("meaningful_change", True) is not False,
            )
            session.flush()
            result = self._room_payload(room)
        return self._apply_consequences(result, audit_id, changed_fields)

    def delete_room(
        self,
        room_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            room = session.get(ExamRoom, room_id)
            if room is None:
                return False
            self._assert_revision(room.revision, expected_revision)
            self._assert_room_is_unused(session, room)
            self._assert_room_can_be_deactivated(session, room)
            self._audit(
                session,
                venue_id=room.venue_id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(room)
            return True

    def create_contact(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any]:
        values, room_ids, reason = self._contact_values(payload, current=None)
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            contact = ExamVenueContact(venue_id=venue.id, **values)
            session.add(contact)
            session.flush()
            self._replace_contact_rooms(session, contact, room_ids or [])
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields={**values, "room_ids": room_ids},
            )
            session.flush()
            return self._contact_payload(session, contact)

    def update_contact(
        self,
        contact_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
    ) -> dict[str, Any] | None:
        expected_revision, command = self._expected_revision(payload)
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            contact = session.get(ExamVenueContact, contact_id)
            if contact is None:
                return None
            self._assert_revision(contact.revision, expected_revision)
            values, room_ids, reason = self._contact_values(command, current=contact)
            was_active = bool(contact.is_active)
            for field, value in values.items():
                setattr(contact, field, value)
            if room_ids is not None:
                self._replace_contact_rooms(session, contact, room_ids)
            contact.revision += 1
            session.flush()
            self._audit(
                session,
                venue_id=contact.venue_id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type=self._change_type(was_active, bool(contact.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=command,
            )
            session.flush()
            return self._contact_payload(session, contact)

    def delete_contact(
        self,
        contact_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
    ) -> bool:
        with session_scope(self.db_path) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            contact = session.get(ExamVenueContact, contact_id)
            if contact is None:
                return False
            self._assert_revision(contact.revision, expected_revision)
            self._audit(
                session,
                venue_id=contact.venue_id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(contact)
            return True

    def _venue_values(
        self, payload: dict[str, Any], *, current: ExamVenue | None
    ) -> tuple[dict[str, Any], str | None]:
        command, reason = self._command(payload, VENUE_FIELDS)
        source = self._venue_source(current, command)
        scope = self._required_choice(source["scope"], "scope", VENUE_SCOPES)
        committee_id = self._optional_integer(source["committee_id"], "committee_id")
        if (scope == "global" and committee_id is not None) or (
            scope == "committee" and committee_id is None
        ):
            raise ExamVenueError("Venue scope and committee must agree")
        accessibility_status = self._required_choice(
            source["accessibility_status"], "accessibility_status", ACCESSIBILITY_STATUSES
        )
        is_accessible = self._optional_boolean(source["is_accessible"], "is_accessible")
        if (accessibility_status == "confirmed") != (is_accessible is not None):
            raise ExamVenueError("Accessibility confirmation must include exactly one yes/no value")
        latitude = self._optional_float(source["latitude"], "latitude", -90, 90)
        longitude = self._optional_float(source["longitude"], "longitude", -180, 180)
        if (latitude is None) != (longitude is None):
            raise ExamVenueError("Latitude and longitude must be supplied together")
        coordinate_status = self._required_choice(
            source["coordinate_status"], "coordinate_status", COORDINATE_STATUSES
        )
        coordinate_source = self._optional_text(source["coordinate_source"])
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
                "name": self._text(source["name"]),
                "normalized_name": normalize_venue_text(source["name"]),
                "street": self._text(source["street"]),
                "postal_code": self._text(source["postal_code"]),
                "city": self._text(source["city"]),
                "country": self._text(source["country"]),
                "site_name": self._optional_text(source["site_name"]),
                "entrance": self._optional_text(source["entrance"]),
                "travel_directions": self._optional_text(source["travel_directions"]),
                "is_accessible": is_accessible,
                "accessibility_status": accessibility_status,
                "accessibility_notes": self._optional_text(source["accessibility_notes"]),
                "latitude": latitude,
                "longitude": longitude,
                "coordinate_status": coordinate_status,
                "coordinate_source": coordinate_source,
                "is_active": self._boolean(source["is_active"], "is_active"),
            },
            reason,
        )

    def _room_values(
        self, payload: dict[str, Any], *, current: ExamRoom | None
    ) -> tuple[dict[str, Any], str | None]:
        command, reason = self._command(payload, ROOM_FIELDS)
        source = {
            field: command.get(
                field,
                getattr(current, field) if current else self._room_default(field),
            )
            for field in ROOM_FIELDS
        }
        name = self._text(source["name"])
        if not name:
            raise ExamVenueError("Room name is required")
        capacity = self._optional_integer(source["capacity"], "capacity")
        if capacity is not None and capacity <= 0:
            raise ExamVenueError("Room capacity must be positive")
        return (
            {
                "name": name,
                "normalized_name": normalize_venue_text(name),
                "building": self._optional_text(source["building"]),
                "wing": self._optional_text(source["wing"]),
                "floor": self._optional_text(source["floor"]),
                "room_number": self._optional_text(source["room_number"]),
                "access_notes": self._optional_text(source["access_notes"]),
                "capacity": capacity,
                "is_active": self._boolean(source["is_active"], "is_active"),
            },
            reason,
        )

    def _contact_values(
        self, payload: dict[str, Any], *, current: ExamVenueContact | None
    ) -> tuple[dict[str, Any], list[int] | None, str | None]:
        command, reason = self._command(payload, CONTACT_FIELDS)
        source = {
            field: command.get(
                field,
                getattr(current, field) if current else self._contact_default(field),
            )
            for field in CONTACT_FIELDS - {"room_ids"}
        }
        label = self._text(source["label"])
        if not label:
            raise ExamVenueError("Contact label is required")
        values = {
            "label": label,
            "role": self._optional_text(source["role"]),
            "phone": self._optional_text(source["phone"]),
            "email": self._optional_text(source["email"]),
            "availability_notes": self._optional_text(source["availability_notes"]),
            "is_active": self._boolean(source["is_active"], "is_active"),
        }
        if not any(values[field] for field in ("phone", "email", "availability_notes")):
            raise ExamVenueError("A contact needs phone, email, or availability information")
        room_ids = self._room_ids(command["room_ids"]) if "room_ids" in command else None
        return values, room_ids, reason

    @staticmethod
    def _venue_source(current: ExamVenue | None, command: dict[str, Any]) -> dict[str, Any]:
        defaults = {
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
            defaults.update({field: getattr(current, field) for field in VENUE_FIELDS})
        defaults.update(command)
        return defaults

    @staticmethod
    def _room_default(field: str) -> object:
        return 1 if field == "is_active" else None

    @staticmethod
    def _contact_default(field: str) -> object:
        return 1 if field == "is_active" else None

    @staticmethod
    def _assert_room_name_available(
        session: Session, venue_id: int, normalized_name: str, excluded_id: int | None = None
    ) -> None:
        statement = select(ExamRoom.id).where(
            ExamRoom.venue_id == venue_id, ExamRoom.normalized_name == normalized_name
        )
        if excluded_id is not None:
            statement = statement.where(ExamRoom.id != excluded_id)
        if session.scalar(statement.limit(1)) is not None:
            raise ExamVenueConflictError("Room name is already used at this venue")

    @staticmethod
    def _assert_venue_name_available(
        session: Session,
        scope: str,
        committee_id: int | None,
        normalized_name: str,
        excluded_id: int | None = None,
    ) -> None:
        statement = select(ExamVenue.id).where(
            ExamVenue.scope == scope,
            ExamVenue.normalized_name == normalized_name,
        )
        if scope == "committee":
            statement = statement.where(ExamVenue.committee_id == committee_id)
        if excluded_id is not None:
            statement = statement.where(ExamVenue.id != excluded_id)
        if session.scalar(statement.limit(1)) is not None:
            raise ExamVenueConflictError("Venue name is already used within this scope")

    def _assert_duplicate_confirmation(
        self,
        session: Session,
        values: dict[str, Any],
        payload: dict[str, Any],
        excluded_id: int | None = None,
    ) -> None:
        relevant_change = excluded_id is None or bool(VENUE_DUPLICATE_FIELDS.intersection(payload))
        if not relevant_change:
            return
        matches = self._duplicate_matches(session, values, excluded_id=excluded_id)
        if not matches:
            return
        if payload.get("duplicates_reviewed") is not True:
            raise ExamVenueConfirmationRequiredError("Duplicate candidates must be reviewed")
        if values["scope"] == "committee" and any(item.scope == "global" for item in matches):
            if not self._optional_text(payload.get("duplicate_reason")):
                raise ExamVenueConfirmationRequiredError(
                    "A committee venue similar to a global venue needs a reason"
                )

    def _duplicate_matches(
        self,
        session: Session,
        values: dict[str, Any],
        *,
        excluded_id: int | None,
    ) -> list[ExamVenue]:
        normalized_name = normalize_venue_text(values["name"])
        normalized_address = self._normalized_address(values)
        matches: list[ExamVenue] = []
        for venue in session.scalars(select(ExamVenue).order_by(ExamVenue.id)):
            if venue.id == excluded_id:
                continue
            if values["scope"] == "global" and venue.scope != "global":
                continue
            if (
                values["scope"] == "committee"
                and venue.scope == "committee"
                and venue.committee_id != values["committee_id"]
            ):
                continue
            name_score = SequenceMatcher(None, normalized_name, venue.normalized_name).ratio()
            if name_score >= 0.9 or normalized_address == self._normalized_address(vars(venue)):
                matches.append(venue)
        return matches

    def _assert_future_impact_confirmation(
        self,
        session: Session,
        venue_id: int,
        room_id: int | None,
        changed_fields: set[str],
        payload: dict[str, Any],
    ) -> None:
        if not changed_fields:
            return
        statement = (
            select(ExamDayAssignment.id)
            .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
            .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
            .where(
                ExamRoom.venue_id == venue_id,
                ExamDay.status == "confirmed",
                ExamDay.date >= date.today().isoformat(),
            )
        )
        if room_id is not None:
            statement = statement.where(ExamDay.room_id == room_id)
        if (
            session.scalar(statement.limit(1)) is not None
            and payload.get("confirm_future_assignments") is not True
        ):
            raise ExamVenueConfirmationRequiredError(
                "Future confirmed appointments must be reviewed and confirmed"
            )

    @staticmethod
    def _assert_revision(actual: int, expected: int) -> None:
        if actual != expected:
            raise ExamVenueConflictError("Venue data revision is stale")

    @staticmethod
    def _assert_venue_can_be_active(
        session: Session, venue_id: int, values: dict[str, Any]
    ) -> None:
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
        if not session.scalar(
            select(ExamRoom.id)
            .where(ExamRoom.venue_id == venue_id, ExamRoom.is_active == 1)
            .limit(1)
        ):
            raise ExamVenueError("An active venue needs an active room")

    @staticmethod
    def _assert_room_can_be_deactivated(session: Session, room: ExamRoom) -> None:
        venue = session.get(ExamVenue, room.venue_id)
        if venue is None or not venue.is_active or not room.is_active:
            return
        another_room = session.scalar(
            select(ExamRoom.id)
            .where(
                ExamRoom.venue_id == room.venue_id,
                ExamRoom.id != room.id,
                ExamRoom.is_active == 1,
            )
            .limit(1)
        )
        if another_room is None:
            raise ExamVenueError("An active venue needs an active room")

    @staticmethod
    def _assert_room_is_unused(session: Session, room: ExamRoom) -> None:
        checks = (
            select(PlanningSettings.id).where(PlanningSettings.default_room_id == room.id),
            select(ExamDay.id).where(ExamDay.room_id == room.id),
            select(LegacyLocationRoomMapping.legacy_location_id).where(
                LegacyLocationRoomMapping.room_id == room.id
            ),
            select(ExamVenueContactRoom.contact_id).where(ExamVenueContactRoom.room_id == room.id),
        )
        if any(session.scalar(statement.limit(1)) is not None for statement in checks):
            raise ExamVenueInUseError("A used room cannot be deleted")

    def _replace_contact_rooms(
        self, session: Session, contact: ExamVenueContact, room_ids: Iterable[int]
    ) -> None:
        identifiers = list(room_ids)
        rooms = [self._room_or_raise(session, room_id) for room_id in identifiers]
        if any(room.venue_id != contact.venue_id for room in rooms):
            raise ExamVenueError("A contact can only reference rooms at its own venue")
        session.query(ExamVenueContactRoom).filter_by(contact_id=contact.id).delete()
        session.add_all(
            [
                ExamVenueContactRoom(contact_id=contact.id, room_id=room_id)
                for room_id in identifiers
            ]
        )

    @staticmethod
    def _audit(
        session: Session,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        entity_revision: int,
        change_type: str,
        actor_member_id: int | None,
        technical_actor: str | None,
        reason: str | None,
        fields: dict[str, Any],
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        changed_fields: set[str] | None = None,
        meaningful_change: bool = True,
    ) -> int:
        details: dict[str, Any] = {"fields": sorted(fields), "values": fields}
        if before is not None and after is not None and changed_fields:
            details.update(
                {
                    "consequence_version": 1,
                    "before": before,
                    "after": after,
                    "changed_fields": sorted(changed_fields),
                    "meaningful_change": meaningful_change,
                }
            )
        event = ExamVenueAuditEvent(
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_revision=entity_revision,
            change_type=change_type,
            actor_kind="member" if actor_member_id is not None else "operator",
            actor_member_id=actor_member_id,
            technical_actor=technical_actor,
            reason=reason,
            details_json=json.dumps(
                details,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        session.add(event)
        session.flush()
        return event.id

    def _apply_consequences(
        self, result: dict[str, Any], audit_id: int | None, changed_fields: set[str]
    ) -> dict[str, Any]:
        if audit_id is None or not changed_fields:
            return result
        try:
            from .venue_consequences import VenueConsequenceService

            consequence_status = VenueConsequenceService(self.db_path).process_audit(audit_id)
        except Exception:
            return {
                **result,
                "consequence_audit_id": audit_id,
                "consequence_warning": (
                    "Die Stammdaten wurden gespeichert, aber Kalender- oder "
                    "Benachrichtigungsfolgen konnten nicht vollständig verarbeitet werden."
                ),
            }
        return {
            **result,
            "consequence_audit_id": audit_id,
            "consequence_status": consequence_status,
            **(
                {
                    "consequence_warning": (
                        "Die Stammdaten wurden gespeichert, aber Kalender- oder "
                        "Benachrichtigungsfolgen konnten nicht vollständig verarbeitet werden."
                    )
                }
                if consequence_status["problems"] or consequence_status["pending"]
                else {}
            ),
        }

    def _venue_payload(self, session: Session, venue: ExamVenue) -> dict[str, Any]:
        return {
            **model_to_dict(venue, EXAM_VENUE),
            "rooms": [
                self._room_payload(room)
                for room in session.scalars(
                    select(ExamRoom)
                    .where(ExamRoom.venue_id == venue.id)
                    .order_by(ExamRoom.is_active.desc(), ExamRoom.name, ExamRoom.id)
                )
            ],
            "contacts": [
                self._contact_payload(session, contact)
                for contact in session.scalars(
                    select(ExamVenueContact)
                    .where(ExamVenueContact.venue_id == venue.id)
                    .order_by(
                        ExamVenueContact.is_active.desc(),
                        ExamVenueContact.label,
                        ExamVenueContact.id,
                    )
                )
            ],
        }

    @staticmethod
    def _room_payload(room: ExamRoom) -> dict[str, Any]:
        return model_to_dict(room, EXAM_ROOM)

    @staticmethod
    def _contact_payload(session: Session, contact: ExamVenueContact) -> dict[str, Any]:
        return {
            **model_to_dict(contact, EXAM_VENUE_CONTACT),
            "room_ids": list(
                session.scalars(
                    select(ExamVenueContactRoom.room_id)
                    .where(ExamVenueContactRoom.contact_id == contact.id)
                    .order_by(ExamVenueContactRoom.room_id)
                )
            ),
        }

    @staticmethod
    def _change_type(was_active: bool, is_active: bool) -> str:
        if was_active != is_active:
            return "activated" if is_active else "deactivated"
        return "updated"

    @staticmethod
    def _require_actor(
        session: Session,
        actor_member_id: int | None,
        technical_actor: str | None,
    ) -> tuple[int | None, str | None]:
        if actor_member_id is not None:
            if isinstance(actor_member_id, int) and not isinstance(actor_member_id, bool):
                if session.get(CommitteeMember, actor_member_id):
                    return actor_member_id, None
            raise ExamVenueError("The audit actor does not exist")
        normalized_actor = ExamVenueService._optional_text(technical_actor)
        if normalized_actor:
            return None, normalized_actor
        raise ExamVenueError("A venue change needs an audit actor")

    @staticmethod
    def _promotion_status(session: Session, venue_id: int) -> str | None:
        event = session.scalars(
            select(ExamVenueAuditEvent)
            .where(
                ExamVenueAuditEvent.venue_id == venue_id,
                ExamVenueAuditEvent.change_type.in_(
                    {"promotion_requested", "promotion_approved", "promotion_rejected"}
                ),
            )
            .order_by(ExamVenueAuditEvent.id.desc())
            .limit(1)
        ).first()
        if event is None:
            return None
        return {
            "promotion_requested": "pending",
            "promotion_approved": "approved",
            "promotion_rejected": "rejected",
        }.get(event.change_type)

    def _promotion_payload(self, session: Session, venue: ExamVenue) -> dict[str, Any]:
        event = session.scalars(
            select(ExamVenueAuditEvent)
            .where(
                ExamVenueAuditEvent.venue_id == venue.id,
                ExamVenueAuditEvent.change_type == "promotion_requested",
            )
            .order_by(ExamVenueAuditEvent.id.desc())
            .limit(1)
        ).first()
        return {
            "status": self._promotion_status(session, venue.id),
            "requested_at": event.created_at if event else None,
            "requested_by_member_id": event.actor_member_id if event else None,
            "reason": event.reason if event else None,
            "venue": self._venue_payload(session, venue),
        }

    @staticmethod
    def _normalized_address(source: dict[str, Any]) -> str:
        return "|".join(
            normalize_venue_text(source.get(field))
            for field in ("street", "postal_code", "city", "country")
        )

    @staticmethod
    def _address_label(source: dict[str, Any]) -> str:
        return ", ".join(
            part
            for part in (
                str(source.get("street") or "").strip(),
                " ".join(
                    part
                    for part in (
                        str(source.get("postal_code") or "").strip(),
                        str(source.get("city") or "").strip(),
                    )
                    if part
                ),
                str(source.get("country") or "").strip(),
            )
            if part
        )

    @staticmethod
    def _venue_or_raise(session: Session, venue_id: int) -> ExamVenue:
        venue = session.get(ExamVenue, venue_id)
        if venue is None:
            raise ExamVenueNotFoundError("Exam venue not found")
        return venue

    @staticmethod
    def _room_or_raise(session: Session, room_id: int) -> ExamRoom:
        room = session.get(ExamRoom, room_id)
        if room is None:
            raise ExamVenueNotFoundError("Exam room not found")
        return room

    @staticmethod
    def _command(
        payload: dict[str, Any], allowed: frozenset[str]
    ) -> tuple[dict[str, Any], str | None]:
        if not isinstance(payload, dict):
            raise ExamVenueError("Venue payload must be an object")
        unknown = set(payload) - allowed - COMMAND_META_FIELDS
        if unknown:
            raise ExamVenueError("Unknown venue fields: " + ", ".join(sorted(unknown)))
        return (
            {field: payload[field] for field in allowed if field in payload},
            ExamVenueService._optional_text(payload.get("reason")),
        )

    @staticmethod
    def _expected_revision(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ExamVenueError("Venue payload must be an object")
        if "expected_revision" not in payload:
            raise ExamVenueConflictError("expected_revision is required")
        expected = payload["expected_revision"]
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ExamVenueConflictError("expected_revision must be a positive integer")
        return expected, {
            key: value for key, value in payload.items() if key != "expected_revision"
        }

    @staticmethod
    def _room_ids(value: object) -> list[int]:
        if not isinstance(value, list):
            raise ExamVenueError("room_ids must be an array")
        identifiers = []
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool) or item < 1:
                raise ExamVenueError("room_ids must contain positive integers")
            identifiers.append(item)
        if len(set(identifiers)) != len(identifiers):
            raise ExamVenueError("room_ids must not contain duplicates")
        return sorted(identifiers)

    @staticmethod
    def _required_choice(value: object, name: str, choices: frozenset[str]) -> str:
        if not isinstance(value, str) or value not in choices:
            raise ExamVenueError(f"{name} is invalid")
        return value

    @staticmethod
    def _text(value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ExamVenueError("Text fields must be strings")
        return value.strip()

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = ExamVenueService._text(value)
        return text or None

    @staticmethod
    def _boolean(value: object, name: str) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int) and value in {0, 1}:
            return value
        raise ExamVenueError(f"{name} must be a boolean")

    @staticmethod
    def _optional_boolean(value: object, name: str) -> int | None:
        return None if value is None else ExamVenueService._boolean(value, name)

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
