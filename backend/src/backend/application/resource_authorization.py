"""Authorize resource commands in one repository transaction per operation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.application import ForbiddenRequestError
from backend.application.resource_ownership import ResourceOwnership
from backend.identity.authorization import AuthorizationScope
from backend.persistence.database import read_session_scope
from backend.persistence.models import (
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    Resource,
)
from backend.persistence.store import Store


class ResourceAuthorizer:
    """Apply the actor's scope without mixing transport parsing and DB lookup.

    Each public operation owns one session. Helpers share its Store; they never
    call a repository entrypoint that would open another session. This boundary
    authorizes a command; the executing service still owns its write transaction.
    """

    def __init__(self, db_path: Path, scope: AuthorizationScope):
        self.db_path = db_path
        self.scope = scope

    def require_round_access(self, round_id: int, *, manage: bool = False) -> None:
        """Require the existing read or management scope for a round."""
        with read_session_scope(self.db_path) as session:
            self._require_round_access(Store(session), round_id, manage=manage)

    def _require_round_access(self, store: Store, round_id: int, *, manage: bool = False) -> int:
        exam_round = store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            raise ForbiddenRequestError("Forbidden.")
        committee_id = exam_round["committee_id"]
        allowed = (
            self.scope.can_manage_committee(committee_id)
            if manage
            else self.scope.can_read_committee(committee_id)
        )
        if not allowed:
            raise ForbiddenRequestError("Forbidden.")
        return committee_id

    def require_day_access(
        self, day_id: int, *, manage: bool = False, member_id: int | None = None
    ) -> None:
        """Resolve a day's round and membership in the same transaction."""
        with read_session_scope(self.db_path) as session:
            store = Store(session)
            day = store.get(EXAM_DAY, day_id)
            round_id = day.get("exam_round_id") if day else None
            if round_id is None:
                raise ForbiddenRequestError("Forbidden.")
            committee_id = self._require_round_access(store, round_id, manage=manage)
            if not manage and not self.scope.can_edit_member(member_id, committee_id):
                raise ForbiddenRequestError("Forbidden.")

    def authorize(
        self, resource: Resource, entity_id: int | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Authorize a resource command and bind server-owned actor fields."""
        normalized = dict(payload)
        for actor_field in ("created_by_member_id", "updated_by_member_id"):
            normalized.pop(actor_field, None)
        if resource == EXAM_HALF_YEAR:
            raise ForbiddenRequestError(
                "Prüfungshalbjahre entstehen ausschließlich gemeinsam mit einer Ausschussrunde."
            )
        with read_session_scope(self.db_path) as session:
            store = Store(session)
            if resource == MEMBER_AVAILABILITY:
                return self._authorize_availability(store, entity_id, normalized)
            owner = ResourceOwnership(store).resolve(resource, entity_id, normalized)
            if not self.scope.can_manage_committee(owner.committee_id):
                raise ForbiddenRequestError("Forbidden.")
            if owner.round_id is not None:
                self._require_round_access(store, int(owner.round_id), manage=True)
            self._bind_actor(resource, owner.committee_id, owner.round_id, normalized)
            return normalized

    def _bind_actor(
        self,
        resource: Resource,
        committee_id: int | None,
        round_id: int | None,
        normalized: dict[str, Any],
    ) -> None:
        if resource == EXAM_ROUND:
            field = "created_by_member_id"
        elif resource == PLANNING_SETTINGS and round_id is not None:
            field = "updated_by_member_id"
        else:
            return
        member_id = self.scope.member_for_committee(committee_id)
        if member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        normalized[field] = member_id

    def _authorize_availability(
        self, store: Store, entity_id: int | None, normalized: dict[str, Any]
    ) -> dict[str, Any]:
        existing = store.get(MEMBER_AVAILABILITY, entity_id) if entity_id is not None else None
        round_id = existing["exam_round_id"] if existing else normalized.get("exam_round_id")
        if round_id is None:
            raise ForbiddenRequestError("Forbidden.")
        committee_id = self._require_round_access(store, int(round_id))
        target_member_id = (
            existing["committee_member_id"]
            if existing is not None
            else normalized.get("committee_member_id")
        )
        if not self.scope.can_manage_committee(committee_id):
            own_member_id = self.scope.member_for_committee(committee_id)
            if existing is not None and existing["committee_member_id"] != own_member_id:
                raise ForbiddenRequestError("Forbidden.")
            target_member_id = own_member_id
        member = self._availability_member(store, target_member_id, committee_id)
        normalized["exam_round_id"] = int(round_id)
        normalized["committee_member_id"] = member["id"]
        if existing is not None and "candidate_exam_day_id" not in normalized:
            normalized["candidate_exam_day_id"] = existing["candidate_exam_day_id"]
        return normalized

    def _availability_member(
        self, store: Store, member_id: int | None, committee_id: int
    ) -> dict[str, Any]:
        member = store.get(COMMITTEE_MEMBER, int(member_id)) if member_id is not None else None
        if (
            member is None
            or not member["is_active"]
            or member["committee_id"] != committee_id
            or not self.scope.can_edit_member(member["id"], committee_id)
        ):
            raise ForbiddenRequestError("Forbidden.")
        return member
