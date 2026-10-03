"""SQLite adapter for Identity-owned person and membership persistence."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import func, select

from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope
from backend.persistence.models import (
    COMMITTEE_MEMBER,
    PERSON,
    Committee,
    CommitteeMember,
    Person,
)
from backend.persistence.resource_access import SQLiteResourceAccessQueries
from backend.persistence.store import Store

if TYPE_CHECKING:
    from backend.identity.people import IdentityQueries, IdentityUnitOfWork


class _SQLiteIdentityMembership(NamedTuple):
    id: int
    person_id: int
    committee_id: int
    committee_role: str


class _SQLiteLoginPerson(NamedTuple):
    person_id: int
    email: str


class SQLiteIdentityUnitOfWork:
    """Map identity values to the existing tables using the root transaction."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def create_person(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.create(PERSON, dict(values))

    def update_person(self, person_id: int, values: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._store.update(PERSON, person_id, dict(values))

    def create_membership(self, values: Mapping[str, Any]) -> dict[str, Any]:
        membership = dict(values)
        person_id = membership.get("person_id")
        person_fields: dict[str, Any] = {
            key: membership.pop(key)
            for key in ("first_name", "last_name", "email", "mobile")
            if key in membership
        }
        if person_id is None:
            required = {"first_name", "last_name", "email"}
            if not required.issubset(person_fields):
                raise ValueError(
                    "Select an existing person or provide first name, last name and email"
                )
            person = self.create_person(person_fields)
            person_id = person["id"]
        elif self._store.get(PERSON, int(person_id)) is None:
            raise ValueError("Person not found")
        elif person_fields:
            raise ValueError(
                "Existing person contact data must be changed through the person endpoint"
            )
        membership["person_id"] = person_id
        return self.member_view(self._store.create(COMMITTEE_MEMBER, membership))

    def update_membership(self, member_id: int, values: Mapping[str, Any]) -> dict[str, Any] | None:
        existing = self._store.get(COMMITTEE_MEMBER, member_id)
        if existing is None:
            return None
        values = dict(values)
        person_fields: dict[str, Any] = {
            key: values[key]
            for key in ("first_name", "last_name", "email", "mobile")
            if key in values
        }
        if person_fields:
            self.update_person(existing["person_id"], self.normalize_person(person_fields))
        member_values = {
            key: value
            for key, value in values.items()
            if key not in {"first_name", "last_name", "email", "mobile"}
        }
        row = (
            self._store.update(COMMITTEE_MEMBER, member_id, member_values)
            if member_values
            else existing
        )
        return self.member_view(row)

    def member_view(self, member: dict[str, Any]) -> dict[str, Any]:
        person = self._store.get(PERSON, member["person_id"])
        if person is None:
            raise ValueError("Membership person not found")
        return {
            **member,
            **{key: person[key] for key in ("first_name", "last_name", "email", "mobile")},
            "email_verified_at": None,
        }

    @staticmethod
    def normalize_person(values: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        if "email" in normalized:
            email = str(normalized["email"]).strip().lower()
            if not email:
                raise ValueError("Primary email is required")
            normalized["email"] = email
        return normalized


class SQLiteIdentityUnitOfWorkFactory:
    """Adapt an existing repository transaction to the Identity port."""

    def for_transaction(self, transaction: object) -> IdentityUnitOfWork:
        if isinstance(transaction, Store):
            return SQLiteIdentityUnitOfWork(transaction)
        return SQLiteIdentityUnitOfWork(Store(transaction))


class SQLiteIdentityQueryFactory:
    """Open SQLite snapshots for Identity-owned read projections."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def snapshot(self) -> Iterator[IdentityQueries]:
        with read_session_scope(self.db_path) as session:
            yield SQLiteIdentityQueries(session)


class SQLiteIdentityQueries:
    """Materialize login and actor projections without returning ORM values."""

    def __init__(self, session) -> None:
        self._session = session
        self._resource_queries = SQLiteResourceAccessQueries(Store(session))

    def login_person(self, email: str) -> _SQLiteLoginPerson | None:
        row = self._session.scalars(
            select(Person).where(func.lower(Person.email) == email.strip().lower())
        ).first()
        if row is None:
            return None
        return _SQLiteLoginPerson(person_id=row.id, email=row.email)

    def active_memberships(self, person_id: int) -> tuple[_SQLiteIdentityMembership, ...]:
        rows = self._session.execute(
            select(
                CommitteeMember.id,
                CommitteeMember.person_id,
                CommitteeMember.committee_id,
                CommitteeMember.committee_role,
            )
            .join(Committee, Committee.id == CommitteeMember.committee_id)
            .where(
                CommitteeMember.person_id == person_id,
                CommitteeMember.is_active == 1,
                Committee.is_active == 1,
                Committee.bootstrap_state == "ready",
            )
            .order_by(CommitteeMember.id)
        ).all()
        return tuple(
            _SQLiteIdentityMembership(
                id=row.id,
                person_id=row.person_id,
                committee_id=row.committee_id,
                committee_role=row.committee_role,
            )
            for row in rows
        )

    def members(self, filters: Mapping[str, object], scope: object | None) -> tuple[dict, ...]:
        return tuple(self._resource_queries.list_members(filters, scope))

    def member(self, member_id: int, scope: object | None) -> dict | None:
        return self._resource_queries.get_member(member_id, scope)
