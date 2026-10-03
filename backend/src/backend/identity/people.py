"""Identity-owned person, membership, and committee projections and use cases."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol


class IdentityUnitOfWork(Protocol):
    """Identity writes that share one caller-owned transaction."""

    def create_person(self, values: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_person(self, person_id: int, values: Mapping[str, Any]) -> dict[str, Any] | None: ...

    def create_membership(self, values: Mapping[str, Any]) -> dict[str, Any]: ...

    def update_membership(
        self, member_id: int, values: Mapping[str, Any]
    ) -> dict[str, Any] | None: ...

    def member_view(self, membership: dict[str, Any]) -> dict[str, Any]: ...


class IdentityUnitOfWorkFactory(Protocol):
    """Bind identity operations to an existing write transaction."""

    def for_transaction(self, transaction: object) -> IdentityUnitOfWork: ...


class IdentityMembership(Protocol):
    """Saved actor membership projection implemented by the persistence adapter."""

    @property
    def id(self) -> int: ...

    @property
    def person_id(self) -> int: ...

    @property
    def committee_id(self) -> int: ...

    @property
    def committee_role(self) -> str: ...


class LoginPerson(Protocol):
    """Primary person identity exposed to local login without an ORM object."""

    @property
    def person_id(self) -> int: ...

    @property
    def email(self) -> str: ...


class IdentityQueries(Protocol):
    """Read projections for local login and server-bound actor resolution."""

    def login_person(self, email: str) -> LoginPerson | None: ...

    def active_memberships(self, person_id: int) -> tuple[IdentityMembership, ...]: ...

    def members(self, filters: Mapping[str, object], scope: object | None) -> tuple[dict, ...]: ...

    def member(self, member_id: int, scope: object | None) -> dict | None: ...


class IdentityQueryFactory(Protocol):
    """Open one consistent read snapshot for Identity projections."""

    def snapshot(self) -> AbstractContextManager[IdentityQueries]: ...


@dataclass(frozen=True)
class IdentityService:
    """Coordinate Identity writes without depending on storage or transport."""

    unit_of_work_factory: IdentityUnitOfWorkFactory
    query_factory: IdentityQueryFactory

    def members(self, filters: Mapping[str, object], scope: object | None) -> list[dict]:
        with self.query_factory.snapshot() as queries:
            return [dict(row) for row in queries.members(filters, scope)]

    def member(self, member_id: int, scope: object | None) -> dict | None:
        with self.query_factory.snapshot() as queries:
            row = queries.member(member_id, scope)
            return dict(row) if row is not None else None

    def create_person(
        self,
        transaction: object,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        return self.unit_of_work_factory.for_transaction(transaction).create_person(
            self.normalize_person(values)
        )

    def update_person(
        self,
        transaction: object,
        person_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        values = self.normalize_person(values)
        return self.unit_of_work_factory.for_transaction(transaction).update_person(
            person_id, values
        )

    def create_membership(
        self,
        transaction: object,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        return self.unit_of_work_factory.for_transaction(transaction).create_membership(values)

    def update_membership(
        self,
        transaction: object,
        member_id: int,
        values: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.unit_of_work_factory.for_transaction(transaction).update_membership(
            member_id, values
        )

    @staticmethod
    def normalize_person(values: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        if "email" in normalized:
            email = str(normalized["email"]).strip().lower()
            if not email:
                raise ValueError("Primary email is required")
            normalized["email"] = email
        return normalized
