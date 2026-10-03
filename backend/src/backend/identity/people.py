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

    def delete_person(self, person_id: int) -> bool: ...

    def delete_membership(self, member_id: int) -> bool: ...

    def require_membership_manager(
        self,
        member_id: int | None,
        values: Mapping[str, Any],
        actor_memberships: Mapping[int, int],
        actor_person_id: int | None,
    ) -> None: ...

    def require_person_manager(
        self, person_id: int, actor_memberships: Mapping[int, int], actor_person_id: int | None
    ) -> None: ...

    def require_any_membership_manager(
        self, actor_memberships: Mapping[int, int], actor_person_id: int | None
    ) -> None: ...


class IdentityUnitOfWorkFactory(Protocol):
    """Open Identity-owned transactional write units."""

    def unit_of_work(self) -> AbstractContextManager[IdentityUnitOfWork]: ...


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

    def login_person(self, email: str) -> LoginPerson | None:
        with self.query_factory.snapshot() as queries:
            return queries.login_person(email.strip().lower())

    def active_memberships(self, person_id: int) -> tuple[IdentityMembership, ...]:
        with self.query_factory.snapshot() as queries:
            return queries.active_memberships(person_id)

    def members(self, filters: Mapping[str, object], scope: object | None) -> list[dict]:
        with self.query_factory.snapshot() as queries:
            return [dict(row) for row in queries.members(filters, scope)]

    def member(self, member_id: int, scope: object | None) -> dict | None:
        with self.query_factory.snapshot() as queries:
            row = queries.member(member_id, scope)
            return dict(row) if row is not None else None

    def create_person(
        self,
        values: dict[str, Any],
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> dict[str, Any]:
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_any_membership_manager(actor_memberships, actor_person_id)
            return uow.create_person(self.normalize_person(values))

    def update_person(
        self,
        person_id: int,
        values: dict[str, Any],
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> dict[str, Any] | None:
        values = self.normalize_person(values)
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_person_manager(person_id, actor_memberships, actor_person_id)
            return uow.update_person(person_id, values)

    def delete_person(
        self,
        person_id: int,
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> bool:
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_person_manager(person_id, actor_memberships, actor_person_id)
            return uow.delete_person(person_id)

    def create_membership(
        self,
        values: dict[str, Any],
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> dict[str, Any]:
        membership = dict(values)
        person_fields: dict[str, Any] = {
            key: membership[key]
            for key in ("first_name", "last_name", "email", "mobile")
            if key in membership
        }
        membership.update(self.normalize_person(person_fields))
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_membership_manager(None, membership, actor_memberships, actor_person_id)
            return uow.create_membership(membership)

    def update_membership(
        self,
        member_id: int,
        values: dict[str, Any],
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_membership_manager(
                    member_id, values, actor_memberships, actor_person_id
                )
            return uow.update_membership(member_id, values)

    def delete_membership(
        self,
        member_id: int,
        *,
        actor_memberships: Mapping[int, int] | None = None,
        actor_person_id: int | None = None,
    ) -> bool:
        with self.unit_of_work_factory.unit_of_work() as uow:
            if actor_memberships is not None:
                uow.require_membership_manager(member_id, {}, actor_memberships, actor_person_id)
            return uow.delete_membership(member_id)

    @staticmethod
    def normalize_person(values: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(values)
        if "email" in normalized:
            email = str(normalized["email"]).strip().lower()
            if not email:
                raise ValueError("Primary email is required")
            normalized["email"] = email
        return normalized
