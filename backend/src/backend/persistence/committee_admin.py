"""SQLite adapter for Identity's committee administration UoW."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.errors import TransactionConflictError, TransactionUnavailableError
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.models import (
    AuthToken,
    Committee,
    CommitteeAdminOperation,
    CommitteeMember,
    Person,
    UserAccount,
)

if TYPE_CHECKING:
    from backend.identity.committee_admin import (
        AccountRecord,
        CommitteeRecord,
        InvitationRecord,
        MembershipRecord,
        OperationRecord,
        PersonRecord,
    )


def _record(row: Any | None) -> SimpleNamespace | None:
    if row is None:
        return None
    return SimpleNamespace(
        **{column.key: getattr(row, column.key) for column in row.__table__.columns}
    )


class SQLiteCommitteeAdminUnitOfWork:
    """Expose materialized records and focused queries over one SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def begin_write(self) -> None:
        self._session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    def flush(self) -> None:
        self._session.flush()

    def create_committee(self, values: Mapping[str, Any]) -> CommitteeRecord:
        row = Committee(**dict(values))
        self._session.add(row)
        self._session.flush()
        return cast("CommitteeRecord", _record(row))

    def get_committee(self, committee_id: int) -> CommitteeRecord | None:
        return cast("CommitteeRecord | None", _record(self._session.get(Committee, committee_id)))

    def save_committee(self, committee: CommitteeRecord) -> None:
        row = self._session.get(Committee, committee.id)
        if row is None:
            raise ValueError("Committee no longer exists")
        row.name = committee.name
        row.occupation = committee.occupation
        row.ihk = committee.ihk
        row.is_active = committee.is_active
        row.bootstrap_state = committee.bootstrap_state
        row.updated_at = committee.updated_at

    def delete_committee(self, committee_id: int) -> bool:
        row = self._session.get(Committee, committee_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def require_committee_manager(
        self,
        committee_id: int,
        actor_memberships: Mapping[int, int],
        actor_person_id: int | None,
    ) -> None:
        committee = self._session.get(Committee, committee_id)
        actor_id = actor_memberships.get(committee_id)
        actor = self._session.get(CommitteeMember, actor_id) if actor_id is not None else None
        if (
            committee is None
            or not committee.is_active
            or committee.bootstrap_state != "ready"
            or actor is None
            or actor_person_id is None
            or actor.person_id != actor_person_id
            or actor.committee_id != committee_id
            or not actor.is_active
            or actor.committee_role not in {"chair", "deputy_chair"}
        ):
            raise PermissionError("Forbidden.")

    def person_by_email(self, email: str) -> PersonRecord | None:
        return cast(
            "PersonRecord | None",
            _record(
                self._session.scalars(
                    select(Person).where(func.lower(Person.email) == email)
                ).first()
            ),
        )

    def account_by_email(self, email: str) -> AccountRecord | None:
        return cast(
            "AccountRecord | None",
            _record(
                self._session.scalars(
                    select(UserAccount).where(func.lower(UserAccount.email) == email.lower())
                ).first()
            ),
        )

    def account_by_person(self, person_id: int) -> AccountRecord | None:
        return cast(
            "AccountRecord | None",
            _record(
                self._session.scalars(
                    select(UserAccount).where(UserAccount.person_id == person_id)
                ).first()
            ),
        )

    def create_person(self, values: Mapping[str, Any]) -> PersonRecord:
        row = Person(**dict(values))
        self._session.add(row)
        self._session.flush()
        return cast("PersonRecord", _record(row))

    def create_account(self, values: Mapping[str, Any]) -> AccountRecord:
        row = UserAccount(**dict(values))
        self._session.add(row)
        self._session.flush()
        return cast("AccountRecord", _record(row))

    def membership_for_person(self, committee_id: int, person_id: int) -> MembershipRecord | None:
        return cast(
            "MembershipRecord | None",
            _record(
                self._session.scalars(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == committee_id,
                        CommitteeMember.person_id == person_id,
                    )
                ).first()
            ),
        )

    def active_membership_for_person(
        self, committee_id: int, person_id: int
    ) -> MembershipRecord | None:
        return cast(
            "MembershipRecord | None",
            _record(
                self._session.scalars(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == committee_id,
                        CommitteeMember.person_id == person_id,
                        CommitteeMember.is_active == 1,
                    )
                ).first()
            ),
        )

    def create_membership(self, values: Mapping[str, Any]) -> MembershipRecord:
        row = CommitteeMember(**dict(values))
        self._session.add(row)
        self._session.flush()
        return cast("MembershipRecord", _record(row))

    def save_membership(self, membership: MembershipRecord) -> None:
        row = self._session.get(CommitteeMember, membership.id)
        if row is None:
            raise ValueError("Membership no longer exists")
        row.is_active = membership.is_active
        row.updated_at = membership.updated_at

    def active_memberships(self, committee_id: int) -> list[MembershipRecord]:
        return [
            cast("MembershipRecord", _record(row))
            for row in self._session.scalars(
                select(CommitteeMember).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.is_active == 1,
                )
            ).all()
        ]

    def accounts_for_people(self, person_ids: list[int]) -> list[AccountRecord]:
        if not person_ids:
            return []
        return [
            cast("AccountRecord", _record(row))
            for row in self._session.scalars(
                select(UserAccount).where(UserAccount.person_id.in_(person_ids))
            ).all()
        ]

    def count_active_role(self, committee_id: int, role: str) -> int:
        return int(
            self._session.scalar(
                select(func.count(CommitteeMember.id)).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.committee_role == role,
                    CommitteeMember.is_active == 1,
                )
            )
            or 0
        )

    def open_invitations(self, account_id: int) -> list[InvitationRecord]:
        return [
            cast("InvitationRecord", _record(row))
            for row in self._session.scalars(
                select(AuthToken).where(
                    AuthToken.account_id == account_id,
                    AuthToken.kind == "invitation",
                    AuthToken.consumed_at.is_(None),
                )
            ).all()
        ]

    def consume_open_invitations(self, account_id: int, consumed_at: str) -> None:
        self._session.execute(
            update(AuthToken)
            .where(
                AuthToken.account_id == account_id,
                AuthToken.kind == "invitation",
                AuthToken.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
        )

    def create_invitation(self, values: Mapping[str, Any]) -> None:
        self._session.add(AuthToken(**dict(values)))
        self._session.flush()

    def operation_by_key(self, key: str) -> OperationRecord | None:
        return cast(
            "OperationRecord | None",
            _record(
                self._session.scalars(
                    select(CommitteeAdminOperation).where(
                        CommitteeAdminOperation.idempotency_key == key
                    )
                ).first()
            ),
        )

    def create_operation(self, values: Mapping[str, Any]) -> OperationRecord:
        row = CommitteeAdminOperation(**dict(values))
        self._session.add(row)
        self._session.flush()
        return cast("OperationRecord", _record(row))


class SQLiteCommitteeAdminUnitOfWorkFactory:
    """Open short-lived SQLite snapshots and immediate write transactions."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def snapshot(self) -> Iterator[SQLiteCommitteeAdminUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield SQLiteCommitteeAdminUnitOfWork(session)

    @contextmanager
    def unit_of_work(self) -> Iterator[SQLiteCommitteeAdminUnitOfWork]:
        try:
            with session_scope(self.db_path) as session:
                yield SQLiteCommitteeAdminUnitOfWork(session)
        except IntegrityError as error:
            raise TransactionConflictError from error
        except OperationalError as error:
            raise TransactionUnavailableError from error
