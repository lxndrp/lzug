"""Transport-neutral access boundary for the exam-venue aggregate.

The aggregate model belongs to #585.  The richer visibility, global-management,
and promotion policy intentionally remains with #586.  Until then this adapter
keeps the pre-existing committee-management boundary and offers a read-only
legacy location projection for callers that have not yet moved to rooms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH
from .exam_venues import ExamVenueService


class ExamVenueApi:
    """Apply the current committee boundary around venue-master-data commands."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.service = ExamVenueService(db_path)

    def list_venues(self, scope: AuthorizationScope) -> list[dict[str, Any]]:
        """Return the committee-scoped rows visible through the current API policy."""
        return [venue for venue in self.service.list_venues() if self._can_read(scope, venue)]

    def get_venue(self, venue_id: int, scope: AuthorizationScope) -> dict[str, Any] | None:
        """Return a visible venue without revealing another committee's data."""
        venue = self.service.get_venue(venue_id)
        return venue if venue is not None and self._can_read(scope, venue) else None

    def create_venue(
        self,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any]:
        """Create a committee-scoped venue for its authorized chair or deputy."""
        actor_member_id = self._actor_for_payload(scope, payload)
        return self.service.create_venue(payload, actor_member_id=actor_member_id)

    def update_venue(
        self,
        venue_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        """Update one accessible committee venue without allowing scope changes."""
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        self._reject_scope_change(payload)
        return self.service.update_venue(venue_id, payload, actor_member_id=actor_member_id)

    def delete_venue(
        self,
        venue_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> bool | None:
        """Delete an unused committee venue when its revision still matches."""
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.delete_venue(
            venue_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            reason=self._reason(payload),
        )

    def create_room(
        self,
        venue_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        """Create one room at a managed committee venue."""
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.create_room(venue_id, payload, actor_member_id=actor_member_id)

    def get_room(self, room_id: int, scope: AuthorizationScope) -> dict[str, Any] | None:
        """Return one visible room through its owning venue aggregate."""
        venue = self._venue_for_room(room_id)
        if venue is None or not self._can_read(scope, venue):
            return None
        return next(room for room in venue["rooms"] if room["id"] == room_id)

    def update_room(
        self,
        room_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        """Update a room after resolving its venue through the aggregate view."""
        venue = self._venue_for_room(room_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.update_room(room_id, payload, actor_member_id=actor_member_id)

    def delete_room(
        self,
        room_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> bool | None:
        """Delete an unused room after an optimistic revision check."""
        venue = self._venue_for_room(room_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.delete_room(
            room_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            reason=self._reason(payload),
        )

    def create_contact(
        self,
        venue_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        """Create an optional venue-wide or room-specific contact."""
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.create_contact(venue_id, payload, actor_member_id=actor_member_id)

    def get_contact(self, contact_id: int, scope: AuthorizationScope) -> dict[str, Any] | None:
        """Return one visible master-data contact through its owning venue."""
        venue = self._venue_for_contact(contact_id)
        if venue is None or not self._can_read(scope, venue):
            return None
        return next(contact for contact in venue["contacts"] if contact["id"] == contact_id)

    def update_contact(
        self,
        contact_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> dict[str, Any] | None:
        """Update a contact without granting it any account or authorization role."""
        venue = self._venue_for_contact(contact_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.update_contact(contact_id, payload, actor_member_id=actor_member_id)

    def delete_contact(
        self,
        contact_id: int,
        payload: dict[str, Any],
        scope: AuthorizationScope,
    ) -> bool | None:
        """Delete an unused contact after an optimistic revision check."""
        venue = self._venue_for_contact(contact_id)
        if venue is None:
            return None
        actor_member_id = self._actor_for_venue(scope, venue)
        return self.service.delete_contact(
            contact_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            reason=self._reason(payload),
        )

    def list_legacy_locations(self, scope: AuthorizationScope) -> list[dict[str, Any]]:
        """Flatten visible rooms for the temporary pre-#587 location read contract."""
        return [
            self._legacy_location(venue, room)
            for venue in self.list_venues(scope)
            for room in venue["rooms"]
        ]

    def get_legacy_location(self, room_id: int, scope: AuthorizationScope) -> dict[str, Any] | None:
        """Return one room projected as its former combined location record."""
        venue = self._venue_for_room(room_id)
        if venue is None or not self._can_read(scope, venue):
            return None
        room = next(room for room in venue["rooms"] if room["id"] == room_id)
        return self._legacy_location(venue, room)

    @staticmethod
    def _can_read(scope: AuthorizationScope, venue: dict[str, Any]) -> bool:
        return venue["scope"] == "committee" and scope.can_read_committee(venue["committee_id"])

    @staticmethod
    def _expected_revision(payload: dict[str, Any]) -> int:
        value = payload.get("expected_revision")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("expected_revision must be a positive integer")
        return value

    @staticmethod
    def _reason(payload: dict[str, Any]) -> str | None:
        value = payload.get("reason")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("reason must be a string")
        return value.strip() or None

    @staticmethod
    def _reject_scope_change(payload: dict[str, Any]) -> None:
        if "scope" in payload or "committee_id" in payload:
            raise PermissionError("Venue scope changes are handled through the promotion workflow.")

    @staticmethod
    def _legacy_location(venue: dict[str, Any], room: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": room["id"],
            "venue_id": venue["id"],
            "committee_id": venue["committee_id"],
            "name": venue["name"],
            "street": venue["street"],
            "postal_code": venue["postal_code"],
            "city": venue["city"],
            "room": room["name"],
            "is_active": int(bool(venue["is_active"]) and bool(room["is_active"])),
            "created_at": room["created_at"],
            "updated_at": room["updated_at"],
        }

    def _actor_for_payload(self, scope: AuthorizationScope, payload: dict[str, Any]) -> int:
        if payload.get("scope") != "committee":
            raise PermissionError("Global venue management is not available through this endpoint.")
        committee_id = payload.get("committee_id")
        if not isinstance(committee_id, int) or isinstance(committee_id, bool):
            raise PermissionError("Forbidden.")
        return self._actor_for_committee(scope, committee_id)

    def _actor_for_venue(self, scope: AuthorizationScope, venue: dict[str, Any]) -> int:
        if venue["scope"] != "committee":
            raise PermissionError("Global venue management is not available through this endpoint.")
        return self._actor_for_committee(scope, venue["committee_id"])

    @staticmethod
    def _actor_for_committee(scope: AuthorizationScope, committee_id: int | None) -> int:
        if not scope.can_manage_committee(committee_id):
            raise PermissionError("Forbidden.")
        actor_member_id = scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise PermissionError("Forbidden.")
        return actor_member_id

    def _venue_for_room(self, room_id: int) -> dict[str, Any] | None:
        for venue in self.service.list_venues():
            if any(room["id"] == room_id for room in venue["rooms"]):
                return venue
        return None

    def _venue_for_contact(self, contact_id: int) -> dict[str, Any] | None:
        for venue in self.service.list_venues():
            if any(contact["id"] == contact_id for contact in venue["contacts"]):
                return venue
        return None
