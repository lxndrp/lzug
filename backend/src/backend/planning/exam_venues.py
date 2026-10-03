"""Planning-owned exam-venue rules and typed repository commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.planning_ports import (
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
)


class ExamVenueService:
    """Apply Planning venue commands through an injected repository and geocoder."""

    def __init__(
        self,
        repository: VenueRepository,
        *,
        geocoder: Geocoder | None = None,
        follow_up: VenueChangeFollowUp | None = None,
    ) -> None:
        self.repository = repository
        self.geocoder = geocoder
        self.follow_up = follow_up

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
