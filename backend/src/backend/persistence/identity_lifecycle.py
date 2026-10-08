"""Identity projections required by cross-domain lifecycle use cases."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.identity.lifecycle_ports import (
    IdentityCommitteeLifecycleSnapshot,
    IdentityMemberLifecycleSnapshot,
)
from backend.persistence.models import Committee, CommitteeMember, Person


class SQLiteIdentityLifecycleWork:
    """Materialize Identity values inside a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def committee_members(self, committee_id: int) -> Sequence[IdentityMemberLifecycleSnapshot]:
        return self._members(
            select(CommitteeMember, Person)
            .join(Person, Person.id == CommitteeMember.person_id)
            .where(CommitteeMember.committee_id == committee_id)
            .order_by(CommitteeMember.id)
        )

    def committee_members_by_ids(
        self, member_ids: Sequence[int]
    ) -> Sequence[IdentityMemberLifecycleSnapshot]:
        if not member_ids:
            return ()
        return self._members(
            select(CommitteeMember, Person)
            .join(Person, Person.id == CommitteeMember.person_id)
            .where(CommitteeMember.id.in_(member_ids))
            .order_by(CommitteeMember.id)
        )

    def committee(self, committee_id: int) -> IdentityCommitteeLifecycleSnapshot | None:
        row = self._session.get(Committee, committee_id)
        if row is None:
            return None
        return IdentityCommitteeLifecycleSnapshot(
            id=row.id,
            name=row.name,
            occupation=row.occupation,
            ihk=row.ihk,
        )

    def management_member_ids(self, committee_id: int) -> set[int]:
        return set(
            self._session.scalars(
                select(CommitteeMember.id).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.is_active == 1,
                    CommitteeMember.committee_role.in_({"chair", "deputy_chair"}),
                )
            )
        )

    def _members(self, statement) -> tuple[IdentityMemberLifecycleSnapshot, ...]:
        return tuple(
            IdentityMemberLifecycleSnapshot(
                id=member.id,
                committee_id=member.committee_id,
                person_id=member.person_id,
                first_name=person.first_name,
                last_name=person.last_name,
                committee_role=member.committee_role,
                representing_side=member.representing_side,
                is_active=member.is_active,
            )
            for member, person in self._session.execute(statement)
        )
