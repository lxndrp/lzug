"""Authorize resource commands through consumer-owned query ports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.application import ForbiddenRequestError
from backend.application.resource_access import (
    ResourceAccessQueryFactory,
    ResourceKind,
    ResourceOwnership,
    ResourceReferenceChange,
    ResourceReferenceField,
    reference_changes,
)
from backend.identity.authorization import AuthorizationScope


class ResourceAuthorizer:
    """Apply actor scope over materialized query results from one read snapshot.

    This boundary authorizes a command; the executing service still owns its
    write transaction and rechecks mutable prerequisites within that UoW.
    """

    OWNERSHIP_FIELDS = {
        ResourceKind.CANDIDATE: frozenset({ResourceReferenceField.EXAM_ROUND_ID}),
        ResourceKind.CANDIDATE_COMMITTEE_ASSIGNMENT: frozenset(
            {
                ResourceReferenceField.CANDIDATE_ID,
                ResourceReferenceField.EXAM_HALF_YEAR_ID,
                ResourceReferenceField.EXAM_ROUND_ID,
                ResourceReferenceField.ROUND_CANDIDATE_ID,
            }
        ),
        ResourceKind.COMMITTEE_MEMBER: frozenset(
            {ResourceReferenceField.COMMITTEE_ID, ResourceReferenceField.PERSON_ID}
        ),
        ResourceKind.ROUND_CANDIDATE: frozenset(
            {ResourceReferenceField.EXAM_ROUND_ID, ResourceReferenceField.CANDIDATE_ID}
        ),
        ResourceKind.PLANNING_SETTINGS: frozenset({ResourceReferenceField.EXAM_ROUND_ID}),
        ResourceKind.CANDIDATE_EXAM_DAY: frozenset({ResourceReferenceField.EXAM_ROUND_ID}),
        ResourceKind.MEMBER_AVAILABILITY: frozenset(
            {
                ResourceReferenceField.EXAM_ROUND_ID,
                ResourceReferenceField.COMMITTEE_MEMBER_ID,
                ResourceReferenceField.CANDIDATE_EXAM_DAY_ID,
            }
        ),
        ResourceKind.EXAM_DAY: frozenset({ResourceReferenceField.EXAM_ROUND_ID}),
        ResourceKind.EXAM_SLOT: frozenset(
            {ResourceReferenceField.EXAM_DAY_ID, ResourceReferenceField.ROUND_CANDIDATE_ID}
        ),
        ResourceKind.EXAM_DAY_ASSIGNMENT: frozenset(
            {ResourceReferenceField.EXAM_DAY_ID, ResourceReferenceField.COMMITTEE_MEMBER_ID}
        ),
    }

    ALLOWED_OWNERSHIP_CHANGES = {
        ResourceKind.CANDIDATE: frozenset({ResourceReferenceField.EXAM_ROUND_ID}),
        ResourceKind.MEMBER_AVAILABILITY: frozenset(
            {
                ResourceReferenceField.EXAM_ROUND_ID,
                ResourceReferenceField.COMMITTEE_MEMBER_ID,
                ResourceReferenceField.CANDIDATE_EXAM_DAY_ID,
            }
        ),
    }

    def __init__(self, queries: ResourceAccessQueryFactory, scope: AuthorizationScope) -> None:
        self.queries = queries
        self.scope = scope

    def require_round_access(self, round_id: int, *, manage: bool = False) -> None:
        """Require the existing read or management scope for a round."""
        with self.queries.snapshot() as queries:
            self._require_round_access(queries, round_id, manage=manage)

    def _require_round_access(self, queries, round_id: int, *, manage: bool = False) -> int:
        owner = queries.ownership(ResourceKind.EXAM_ROUND, round_id)
        committee_id = owner.committee_id
        allowed = owner.exists and (
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
        """Resolve a day's round and membership in the same query snapshot."""
        with self.queries.snapshot() as queries:
            day = queries.ownership(ResourceKind.EXAM_DAY, day_id)
            if not day.exists or day.round_id is None:
                raise ForbiddenRequestError("Forbidden.")
            committee_id = self._require_round_access(queries, day.round_id, manage=manage)
            if not manage and not self.scope.can_edit_member(member_id, committee_id):
                raise ForbiddenRequestError("Forbidden.")

    def authorize(
        self, resource: ResourceKind, entity_id: int | None, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Authorize a command and bind server-owned actor fields."""
        with self.queries.snapshot() as queries:
            return self.authorize_with_queries(queries, resource, entity_id, payload)

    def authorize_with_queries(
        self,
        queries,
        resource: ResourceKind,
        entity_id: int | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Authorize within a caller-owned query snapshot or writing UoW."""
        normalized = dict(payload)
        for actor_field in ("created_by_member_id", "updated_by_member_id"):
            normalized.pop(actor_field, None)
        if resource == ResourceKind.EXAM_HALF_YEAR:
            raise ForbiddenRequestError(
                "Prüfungshalbjahre entstehen ausschließlich gemeinsam mit einer Ausschussrunde."
            )
        changes = reference_changes(normalized)
        if resource == ResourceKind.MEMBER_AVAILABILITY:
            return self._authorize_availability(queries, entity_id, normalized, changes)
        if entity_id is None:
            target = queries.ownership(resource, None, changes)
            if not self.scope.can_manage_committee(target.committee_id):
                raise ForbiddenRequestError("Forbidden.")
            if target.round_id is not None:
                self._require_round_access(queries, target.round_id, manage=True)
            self._bind_actor(resource, target.committee_id, target.round_id, normalized)
            return normalized

        # Always authorize the stored source before resolving any requested target.
        source = queries.ownership(resource, entity_id)
        if not source.exists or not self.scope.can_manage_committee(source.committee_id):
            raise ForbiddenRequestError("Forbidden.")
        target = queries.ownership(resource, entity_id, changes)
        self._check_target(resource, source, target, changes, queries)
        self._bind_actor(resource, source.committee_id, source.round_id, normalized)
        return normalized

    def _check_target(
        self,
        resource: ResourceKind,
        source: ResourceOwnership,
        target: ResourceOwnership,
        changes: Sequence[ResourceReferenceChange],
        queries,
    ) -> None:
        ownership_fields = self.OWNERSHIP_FIELDS.get(resource, frozenset())
        changed = {
            change.field
            for change in changes
            if change.field in ownership_fields
            and change.value != source.references.value(change.field)
        }
        disallowed = changed - self.ALLOWED_OWNERSHIP_CHANGES.get(resource, frozenset())
        # Planning owns these writes and retains its established domain error.
        if (
            resource
            not in {
                ResourceKind.EXAM_DAY,
                ResourceKind.EXAM_SLOT,
                ResourceKind.EXAM_DAY_ASSIGNMENT,
            }
            and disallowed
        ):
            raise ForbiddenRequestError("Forbidden.")
        if (target.committee_id, target.round_id) != (source.committee_id, source.round_id):
            if not self.scope.can_manage_committee(target.committee_id):
                raise ForbiddenRequestError("Forbidden.")
            if target.round_id is not None:
                self._require_round_access(queries, target.round_id, manage=True)

    def _bind_actor(
        self,
        resource: ResourceKind,
        committee_id: int | None,
        round_id: int | None,
        normalized: dict[str, Any],
    ) -> None:
        if resource == ResourceKind.EXAM_ROUND:
            field = "created_by_member_id"
        elif resource == ResourceKind.PLANNING_SETTINGS and round_id is not None:
            field = "updated_by_member_id"
        else:
            return
        member_id = self.scope.member_for_committee(committee_id)
        if member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        normalized[field] = member_id

    def _authorize_availability(
        self,
        queries,
        entity_id: int | None,
        normalized: dict[str, Any],
        changes: Sequence[ResourceReferenceChange],
    ) -> dict[str, Any]:
        existing = (
            queries.ownership(ResourceKind.MEMBER_AVAILABILITY, entity_id)
            if entity_id is not None
            else None
        )
        round_id = (
            existing.references.exam_round_id
            if existing is not None and existing.exists
            else self._changed_value(changes, ResourceReferenceField.EXAM_ROUND_ID)
        )
        if round_id is None:
            raise ForbiddenRequestError("Forbidden.")
        committee_id = self._require_round_access(queries, round_id)
        target_member_id = (
            existing.references.committee_member_id
            if existing is not None and existing.exists
            else self._changed_value(changes, ResourceReferenceField.COMMITTEE_MEMBER_ID)
        )
        if not self.scope.can_manage_committee(committee_id):
            own_member_id = self.scope.member_for_committee(committee_id)
            if existing is not None and existing.exists:
                if existing.references.committee_member_id != own_member_id:
                    raise ForbiddenRequestError("Forbidden.")
            target_member_id = own_member_id
        member = self._availability_member(queries, target_member_id, committee_id)
        normalized["exam_round_id"] = round_id
        normalized["committee_member_id"] = member.member_id
        if existing is not None and existing.exists and "candidate_exam_day_id" not in normalized:
            normalized["candidate_exam_day_id"] = existing.references.candidate_exam_day_id
        return normalized

    @staticmethod
    def _changed_value(
        changes: Sequence[ResourceReferenceChange], field: ResourceReferenceField
    ) -> int | None:
        return next((change.value for change in changes if change.field == field), None)

    def _availability_member(self, queries, member_id: int | None, committee_id: int):
        member = queries.committee_member(member_id) if member_id is not None else None
        if (
            member is None
            or not member.is_active
            or member.committee_id != committee_id
            or not self.scope.can_edit_member(member.member_id, committee_id)
        ):
            raise ForbiddenRequestError("Forbidden.")
        return member
