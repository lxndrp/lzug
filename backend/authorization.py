"""Server-side committee authorization scopes.

Authentication answers *who* sent a request.  This module answers which
committee data that identity may use.  The scope deliberately contains only
active committee memberships; account/operator state never becomes a domain
role here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from .auth import AuthContext
from .database import DEFAULT_DB_PATH, session_scope
from .models import Committee, CommitteeMember


@dataclass(frozen=True)
class AuthorizationScope:
    """The active memberships and management rights of one authenticated actor."""

    person_id: int | None
    person_ids: frozenset[int]
    committee_ids: frozenset[int]
    member_ids: frozenset[int]
    management_committee_ids: frozenset[int]
    member_by_committee: dict[int, int]

    @property
    def has_active_membership(self) -> bool:
        return bool(self.member_ids)

    def member_for_committee(self, committee_id: int | None) -> int | None:
        if committee_id is None:
            return None
        return self.member_by_committee.get(committee_id)

    def can_read_committee(self, committee_id: int | None) -> bool:
        return committee_id in self.committee_ids

    def can_manage_committee(self, committee_id: int | None) -> bool:
        return committee_id in self.management_committee_ids

    def can_edit_member(self, member_id: int | None, committee_id: int | None) -> bool:
        """Allow own feedback/tasks, or management of the whole committee."""
        return self.can_manage_committee(committee_id) or member_id in self.member_ids


class AuthorizationService:
    """Resolve an authenticated session to its active committee scope."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def scope(self, context: AuthContext) -> AuthorizationScope:
        if context.person_id is None:
            return AuthorizationScope(None, frozenset(), frozenset(), frozenset(), frozenset(), {})
        with session_scope(self.db_path) as session:
            memberships = [
                {
                    "id": membership.id,
                    "person_id": membership.person_id,
                    "committee_id": membership.committee_id,
                    "committee_role": membership.committee_role,
                }
                for membership in session.scalars(
                    select(CommitteeMember)
                    .join(Committee, Committee.id == CommitteeMember.committee_id)
                    .where(
                        CommitteeMember.person_id == context.person_id,
                        CommitteeMember.is_active == 1,
                        Committee.is_active == 1,
                        Committee.bootstrap_state == "ready",
                    )
                    .order_by(CommitteeMember.id)
                ).all()
            ]

        member_by_committee = {
            membership["committee_id"]: membership["id"] for membership in memberships
        }
        management_committee_ids = {
            membership["committee_id"]
            for membership in memberships
            if membership["committee_role"] in {"chair", "deputy_chair"}
        }
        return AuthorizationScope(
            person_id=context.person_id,
            person_ids=frozenset(membership["person_id"] for membership in memberships),
            committee_ids=frozenset(member_by_committee),
            member_ids=frozenset(membership["id"] for membership in memberships),
            management_committee_ids=frozenset(management_committee_ids),
            member_by_committee=member_by_committee,
        )
