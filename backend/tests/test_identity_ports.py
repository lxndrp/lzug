"""Identity port contracts with a double and the SQLite adapter."""

from __future__ import annotations

import unittest
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError

from backend.application.repositories import ResourceRepository
from backend.identity.auth import AuthContext
from backend.identity.authorization import AuthorizationService
from backend.identity.people import (
    IdentityMembership,
    IdentityService,
    LoginPerson,
)
from backend.persistence.identity import SQLiteIdentityQueryFactory
from backend.persistence.models import PERSON
from backend.tests.helpers import TempDatabase


class IdentityPortTests(unittest.TestCase):
    def test_service_uses_one_injected_write_uow_and_canonicalizes_email(self) -> None:
        transaction = object()
        uow = _IdentityDouble()
        factory = _IdentityFactory(uow)
        service = IdentityService(factory, _IdentityQueryFactory(_IdentityQueryDouble()))

        created = service.create_person(
            transaction,
            {"first_name": "Ada", "last_name": "Lovelace", "email": " ADA@EXAMPLE.INVALID "},
        )

        self.assertIs(transaction, factory.transaction)
        self.assertEqual("ada@example.invalid", created["email"])
        self.assertEqual(
            {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.invalid"},
            uow.created_person,
        )

    def test_sqlite_membership_write_rolls_back_person_when_membership_fails(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            with self.assertRaises(IntegrityError):
                repository.create_membership(
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "email": "ada@example.invalid",
                        "committee_id": 999,
                        "member_status": "ordinary",
                        "committee_role": "member",
                        "representing_side": "school",
                        "is_active": 1,
                    }
                )

            self.assertEqual([], repository.list(PERSON))

    def test_actor_scope_uses_identity_query_double(self) -> None:
        query = _IdentityQueryDouble()
        factory = _IdentityQueryFactory(query)
        context = AuthContext(
            session_id=12,
            account_id=8,
            person_id=4,
            is_operator=False,
            committee_member_id=3,
        )

        scope = AuthorizationService(query_factory=factory).scope(context)

        self.assertEqual(frozenset({9}), scope.committee_ids)
        self.assertEqual({9: 3}, scope.member_by_committee)
        self.assertEqual(frozenset({9}), scope.management_committee_ids)

    def test_sqlite_identity_query_projects_login_and_active_actor_memberships(self) -> None:
        with TempDatabase() as db_path:
            with SQLiteIdentityQueryFactory(db_path).snapshot() as queries:
                login_person = queries.login_person("THESEUS.ATHEN@demo.lzug.invalid")
                memberships = queries.active_memberships(1)

        self.assertEqual(1, login_person.person_id)
        self.assertEqual("theseus.athen@demo.lzug.invalid", login_person.email)
        self.assertEqual(1, len(memberships))
        self.assertEqual(
            (1, 1, 1, "chair"),
            (
                memberships[0].id,
                memberships[0].person_id,
                memberships[0].committee_id,
                memberships[0].committee_role,
            ),
        )


class _IdentityDouble:
    def __init__(self) -> None:
        self.created_person: dict[str, object] | None = None

    def create_person(self, values):
        self.created_person = dict(values)
        return {"id": 4, **values}


class _IdentityFactory:
    def __init__(self, unit_of_work: _IdentityDouble) -> None:
        self.unit_of_work = unit_of_work
        self.transaction: object | None = None

    def for_transaction(self, transaction: object) -> _IdentityDouble:
        self.transaction = transaction
        return self.unit_of_work


class _IdentityQueryDouble:
    def login_person(self, email: str) -> LoginPerson | None:
        return _TestLoginPerson(4, email) if email.lower() == "ada@example.invalid" else None

    def active_memberships(self, person_id: int) -> tuple[IdentityMembership, ...]:
        return (_TestIdentityMembership(3, person_id, 9, "chair"),)


class _TestLoginPerson(NamedTuple):
    person_id: int
    email: str


class _TestIdentityMembership(NamedTuple):
    id: int
    person_id: int
    committee_id: int
    committee_role: str


class _IdentityQueryFactory:
    def __init__(self, queries: _IdentityQueryDouble) -> None:
        self.queries = queries

    def snapshot(self):
        return _Snapshot(self.queries)


class _Snapshot:
    def __init__(self, queries: _IdentityQueryDouble) -> None:
        self.queries = queries

    def __enter__(self):
        return self.queries

    def __exit__(self, exc_type, exc_value, traceback):
        return False


if __name__ == "__main__":
    unittest.main()
