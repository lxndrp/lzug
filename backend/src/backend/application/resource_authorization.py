"""Authorize resource commands in one repository transaction per operation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.application import ForbiddenRequestError
from backend.application.resource_ownership import ResourceOwnership
from backend.identity.authorization import AuthorizationScope
from backend.persistence.database import read_session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Resource,
)
from backend.persistence.store import Store


class ResourceAuthorizer:
    """Apply the actor's scope without mixing transport parsing and DB lookup.

    Each public operation owns one session. Helpers share its Store; they never
    call a repository entrypoint that would open another session. This boundary
    authorizes a command; the executing service still owns its write transaction.
    """

    OWNERSHIP_FIELDS = {
        CANDIDATE: frozenset({"exam_round_id"}),
        CANDIDATE_COMMITTEE_ASSIGNMENT: frozenset(
            {"candidate_id", "exam_half_year_id", "exam_round_id", "round_candidate_id"}
        ),
        COMMITTEE_MEMBER: frozenset({"committee_id", "person_id"}),
        ROUND_CANDIDATE: frozenset({"exam_round_id", "candidate_id"}),
        PLANNING_SETTINGS: frozenset({"exam_round_id"}),
        CANDIDATE_EXAM_DAY: frozenset({"exam_round_id"}),
        MEMBER_AVAILABILITY: frozenset(
            {"exam_round_id", "committee_member_id", "candidate_exam_day_id"}
        ),
        EXAM_DAY: frozenset({"exam_round_id"}),
        EXAM_SLOT: frozenset({"exam_day_id", "round_candidate_id"}),
        EXAM_DAY_ASSIGNMENT: frozenset({"exam_day_id", "committee_member_id"}),
    }

    # These are existing command contracts with explicit source/target handling.
    # All other ownership fields are immutable through the generic resource API.
    ALLOWED_OWNERSHIP_CHANGES = {
        CANDIDATE: frozenset({"exam_round_id"}),
        MEMBER_AVAILABILITY: frozenset(
            {"exam_round_id", "committee_member_id", "candidate_exam_day_id"}
        ),
    }

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
            ownership = ResourceOwnership(store)
            if entity_id is None:
                target = ownership.resolve(resource, None, normalized)
                if not self.scope.can_manage_committee(target.committee_id):
                    raise ForbiddenRequestError("Forbidden.")
                if target.round_id is not None:
                    self._require_round_access(store, int(target.round_id), manage=True)
                self._bind_actor(resource, target.committee_id, target.round_id, normalized)
                return normalized
            source = ownership.resolve(resource, entity_id)
            if not self.scope.can_manage_committee(source.committee_id):
                raise ForbiddenRequestError("Forbidden.")
            target = ownership.resolve(resource, entity_id, normalized)
            self._check_target(resource, source, target, normalized, store, entity_id)
            self._bind_actor(resource, source.committee_id, source.round_id, normalized)
            return normalized

    def _check_target(
        self,
        resource: Resource,
        source,
        target,
        payload: dict[str, Any],
        store: Store,
        entity_id: int | None,
    ) -> None:
        stored = store.get(resource, entity_id) if entity_id is not None else {}
        ownership_fields = self.OWNERSHIP_FIELDS.get(resource, frozenset())
        changed = {
            field
            for field in ownership_fields
            if field in payload
            and payload[field]
            != stored.get(field, source.round_id if field == "exam_round_id" else None)
        }
        disallowed = changed - self.ALLOWED_OWNERSHIP_CHANGES.get(resource, frozenset())
        # The planning aggregate owns these writes and must retain its
        # established domain error rather than turning them into an auth error.
        if resource not in {EXAM_DAY, EXAM_SLOT, EXAM_DAY_ASSIGNMENT} and disallowed:
            raise ForbiddenRequestError("Forbidden.")
        if (target.committee_id, target.round_id) != (source.committee_id, source.round_id):
            if not self.scope.can_manage_committee(target.committee_id):
                raise ForbiddenRequestError("Forbidden.")
            if target.round_id is not None:
                self._require_round_access(store, int(target.round_id), manage=True)

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
