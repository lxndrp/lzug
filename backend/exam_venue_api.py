"""Scope-safe transport boundary for exam-venue management."""

from __future__ import annotations

from pathlib import Path

from .auth import AuthContext
from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH
from .exam_venues import ExamVenueService


class ExamVenueApi:
    """Apply member, management, operator, and promotion visibility rules."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.service = ExamVenueService(db_path)

    def list_venues(self, scope: AuthorizationScope, auth: AuthContext | None = None):
        return [
            self._decorate(scope, auth, venue)
            for venue in self.service.list_venues()
            if self._can_read(scope, auth, venue)
        ]

    def get_venue(self, venue_id: int, scope: AuthorizationScope, auth: AuthContext | None = None):
        venue = self.service.get_venue(venue_id)
        return (
            self._decorate(scope, auth, venue)
            if venue and self._can_read(scope, auth, venue)
            else None
        )

    def find_duplicates(self, payload, scope, auth=None, *, excluded_id=None):
        visible = frozenset(
            venue["id"]
            for venue in self.service.list_venues()
            if self._can_read(scope, auth, venue)
        )
        return self.service.find_duplicates(
            payload, visible_venue_ids=visible, excluded_id=excluded_id
        )

    def future_impact(self, venue_id, scope, auth=None, *, room_id=None):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        self._actor_for_venue(scope, auth, venue)
        return self.service.future_impact(venue_id, room_id)

    def create_venue(self, payload, scope, auth=None):
        if payload.get("scope") == "global":
            result = self.service.create_venue(payload, technical_actor=self._operator_actor(auth))
        else:
            result = self.service.create_venue(
                payload, actor_member_id=self._actor_for_payload(scope, payload)
            )
        return self._decorate(scope, auth, result)

    def update_venue(self, venue_id, payload, scope, auth=None):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        self._reject_scope_change(payload)
        result = self.service.update_venue(
            venue_id, payload, actor_member_id=actor_member_id, technical_actor=technical_actor
        )
        return self._decorate(scope, auth, result) if result else None

    def delete_venue(self, venue_id, payload, scope, auth=None):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.delete_venue(
            venue_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            technical_actor=technical_actor,
            reason=self._reason(payload),
        )

    def create_room(self, venue_id, payload, scope, auth=None):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.create_room(
            venue_id, payload, actor_member_id=actor_member_id, technical_actor=technical_actor
        )

    def get_room(self, room_id, scope, auth=None):
        venue = self._venue_for_room(room_id)
        if venue is None or not self._can_read(scope, auth, venue):
            return None
        return next(room for room in venue["rooms"] if room["id"] == room_id)

    def update_room(self, room_id, payload, scope, auth=None):
        venue = self._venue_for_room(room_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.update_room(
            room_id, payload, actor_member_id=actor_member_id, technical_actor=technical_actor
        )

    def delete_room(self, room_id, payload, scope, auth=None):
        venue = self._venue_for_room(room_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.delete_room(
            room_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            technical_actor=technical_actor,
            reason=self._reason(payload),
        )

    def create_contact(self, venue_id, payload, scope, auth=None):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.create_contact(
            venue_id, payload, actor_member_id=actor_member_id, technical_actor=technical_actor
        )

    def get_contact(self, contact_id, scope, auth=None):
        venue = self._venue_for_contact(contact_id)
        if venue is None or not self._can_read(scope, auth, venue):
            return None
        return next(contact for contact in venue["contacts"] if contact["id"] == contact_id)

    def update_contact(self, contact_id, payload, scope, auth=None):
        venue = self._venue_for_contact(contact_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.update_contact(
            contact_id, payload, actor_member_id=actor_member_id, technical_actor=technical_actor
        )

    def delete_contact(self, contact_id, payload, scope, auth=None):
        venue = self._venue_for_contact(contact_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, auth, venue)
        return self.service.delete_contact(
            contact_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            technical_actor=technical_actor,
            reason=self._reason(payload),
        )

    def request_promotion(self, venue_id, payload, scope):
        venue = self.service.get_venue(venue_id)
        if venue is None:
            return None
        actor_member_id, technical_actor = self._actor_for_venue(scope, None, venue)
        if technical_actor is not None or actor_member_id is None:
            raise PermissionError("Forbidden.")
        return self.service.request_promotion(
            venue_id,
            expected_revision=self._expected_revision(payload),
            actor_member_id=actor_member_id,
            reason=self._required_reason(payload),
        )

    def list_pending_promotions(self, auth):
        self._operator_actor(auth)
        return self.service.list_pending_promotions()

    def decide_promotion(self, venue_id, payload, auth):
        return self.service.decide_promotion(
            venue_id,
            expected_revision=self._expected_revision(payload),
            decision=str(payload.get("decision", "")),
            reason=self._required_reason(payload),
            technical_actor=self._operator_actor(auth),
        )

    def list_legacy_locations(self, scope, auth=None):
        return [
            self._legacy_location(venue, room)
            for venue in self.list_venues(scope, auth)
            for room in venue["rooms"]
        ]

    def get_legacy_location(self, room_id, scope, auth=None):
        venue = self._venue_for_room(room_id)
        if venue is None or not self._can_read(scope, auth, venue):
            return None
        return self._legacy_location(
            venue, next(room for room in venue["rooms"] if room["id"] == room_id)
        )

    def _can_read(self, scope, auth, venue):
        referenced = bool(self.service.referenced_committee_ids(venue["id"]) & scope.committee_ids)
        if venue["scope"] == "global":
            return bool(auth and auth.is_operator) or (
                scope.has_active_membership and (venue["is_active"] or referenced)
            )
        if auth and auth.is_operator:
            return any(
                item["venue"]["id"] == venue["id"]
                for item in self.service.list_pending_promotions()
            )
        committee_id = venue["committee_id"]
        return scope.can_manage_committee(committee_id) or (
            scope.can_read_committee(committee_id) and bool(venue["is_active"] or referenced)
        )

    def _decorate(self, scope, auth, venue):
        manage = self._can_manage(scope, auth, venue)
        return {
            **venue,
            "capabilities": {
                "manage": manage,
                "request_promotion": manage and venue["scope"] == "committee",
                "decide_promotion": bool(
                    auth and auth.is_operator and venue["scope"] == "committee"
                ),
            },
        }

    @staticmethod
    def _can_manage(scope, auth, venue):
        return (
            bool(auth and auth.is_operator)
            if venue["scope"] == "global"
            else scope.can_manage_committee(venue["committee_id"])
        )

    def _actor_for_payload(self, scope, payload):
        if payload.get("scope") != "committee":
            raise PermissionError("Forbidden.")
        return self._actor_for_committee(scope, payload.get("committee_id"))

    def _actor_for_venue(self, scope, auth, venue):
        if venue["scope"] == "global":
            return None, self._operator_actor(auth)
        return self._actor_for_committee(scope, venue["committee_id"]), None

    @staticmethod
    def _actor_for_committee(scope, committee_id):
        if (
            not isinstance(committee_id, int)
            or isinstance(committee_id, bool)
            or not scope.can_manage_committee(committee_id)
        ):
            raise PermissionError("Forbidden.")
        actor = scope.member_for_committee(committee_id)
        if actor is None:
            raise PermissionError("Forbidden.")
        return actor

    @staticmethod
    def _operator_actor(auth):
        if auth is None or not auth.is_operator:
            raise PermissionError("Forbidden.")
        return f"account:{auth.account_id}"

    @staticmethod
    def _expected_revision(payload):
        value = payload.get("expected_revision")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("expected_revision must be a positive integer")
        return value

    @staticmethod
    def _reason(payload):
        value = payload.get("reason")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("reason must be a string")
        return value.strip() or None

    @classmethod
    def _required_reason(cls, payload):
        reason = cls._reason(payload)
        if reason is None:
            raise ValueError("reason is required")
        return reason

    @staticmethod
    def _reject_scope_change(payload):
        if "scope" in payload or "committee_id" in payload:
            raise PermissionError("Venue scope changes are handled through the promotion workflow.")

    @staticmethod
    def _legacy_location(venue, room):
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

    def _venue_for_room(self, room_id):
        return next(
            (
                venue
                for venue in self.service.list_venues()
                if any(room["id"] == room_id for room in venue["rooms"])
            ),
            None,
        )

    def _venue_for_contact(self, contact_id):
        return next(
            (
                venue
                for venue in self.service.list_venues()
                if any(contact["id"] == contact_id for contact in venue["contacts"])
            ),
            None,
        )
