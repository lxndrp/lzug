from __future__ import annotations

import json
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import func, select

from backend.admin_service import AdminOperationError
from backend.auth import AuthenticationRepository
from backend.authorization import AuthorizationService
from backend.committee_admin import CommitteeAdminService
from backend.database import session_scope
from backend.local_auth import LocalAuthService
from backend.models import (
    COMMITTEE,
    PERSON,
    AuthToken,
    Committee,
    CommitteeAdminOperation,
    Person,
    UserAccount,
)
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


def new_person(email: str, *, side: str = "employer") -> dict[str, object]:
    local = email.split("@", 1)[0]
    return {
        "mode": "new",
        "first_name": "Neue",
        "last_name": local.title(),
        "email": email,
        "mobile": "+49 000 123456",
        "member_status": "ordinary",
        "representing_side": side,
    }


def existing_person(email: str, *, side: str = "employer") -> dict[str, object]:
    return {
        "mode": "existing",
        "email": email,
        "member_status": "ordinary",
        "representing_side": side,
    }


def bootstrap_arguments(key: str = "bootstrap-001") -> dict[str, object]:
    return {
        "idempotency_key": key,
        "committee": {
            "name": "Prüfungsausschuss Nord",
            "ihk": "IHK Teststadt",
            "occupation": "Fachinformatiker/in",
        },
        "chair": new_person("chair@example.invalid"),
    }


class CommitteeAdminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    def test_bootstrap_creates_complete_committee_and_secret_free_evidence(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            arguments = bootstrap_arguments()
            arguments["deputy"] = new_person("deputy@example.invalid", side="school")

            result = CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual("ready", result["bootstrap_state"])
            self.assertTrue(result["is_active"])
            self.assertEqual(2, result["invitations_issued"])
            self.assertEqual(2, len(result["invitations"]))
            tokens = [invitation["token"] for invitation in result["invitations"]]
            with sqlite3.connect(db_path) as connection:
                committee = connection.execute(
                    "SELECT name, ihk, occupation, is_active, bootstrap_state FROM committee"
                ).fetchone()
                memberships = connection.execute(
                    "SELECT committee_role, is_active FROM committee_member "
                    "ORDER BY committee_role"
                ).fetchall()
                accounts = connection.execute(
                    "SELECT person_id, is_operator, is_active FROM user_account ORDER BY id"
                ).fetchall()
                token_hashes = [
                    row[0] for row in connection.execute("SELECT token_hash FROM auth_token")
                ]
                evidence = connection.execute(
                    "SELECT technical_source, response_json, person_ids_json, "
                    "membership_ids_json FROM committee_admin_operation"
                ).fetchone()
            self.assertEqual(
                (
                    "Prüfungsausschuss Nord",
                    "IHK Teststadt",
                    "Fachinformatiker/in",
                    1,
                    "ready",
                ),
                committee,
            )
            self.assertEqual([("chair", 1), ("deputy_chair", 1)], memberships)
            self.assertTrue(
                all(
                    person_id and not operator and active
                    for person_id, operator, active in accounts
                )
            )
            self.assertTrue(all(token not in json.dumps(evidence) for token in tokens))
            self.assertTrue(all(token not in token_hashes for token in tokens))
            self.assertEqual("operator-cli", evidence[0])
            self.assertEqual(result["person_ids"], json.loads(evidence[2]))
            self.assertEqual(result["membership_ids"], json.loads(evidence[3]))

            with sqlite3.connect(db_path) as connection:
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    connection.execute(
                        "UPDATE committee_admin_operation SET result = 'ready' WHERE id = 1"
                    )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    connection.execute("DELETE FROM committee_admin_operation WHERE id = 1")

    def test_existing_person_and_active_linked_account_are_reused(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            person = repository.create(
                resource=PERSON,
                payload={
                    "first_name": "Vorhanden",
                    "last_name": "Vorsitz",
                    "email": "existing@example.invalid",
                },
            )
            account = AuthenticationRepository(db_path).create_account(
                "login@example.invalid", person_id=person["id"]
            )
            arguments = bootstrap_arguments()
            arguments["chair"] = existing_person("EXISTING@example.invalid")

            result = CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual([person["id"]], result["person_ids"])
            self.assertEqual([account["id"]], result["account_ids"])
            self.assertEqual([], result["invitations"])
            self.assertEqual(0, result["invitations_issued"])
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(1, connection.execute("SELECT count(*) FROM person").fetchone()[0])
                self.assertEqual(
                    "existing@example.invalid",
                    connection.execute("SELECT email FROM person").fetchone()[0],
                )

    def test_existing_chair_and_existing_deputy_are_reused_without_new_invitations(
        self,
    ) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            selections = {}
            for role, email in (
                ("chair", "existing.chair@example.invalid"),
                ("deputy", "existing.deputy@example.invalid"),
            ):
                person = repository.create(
                    PERSON,
                    {
                        "first_name": "Vorhanden",
                        "last_name": role.title(),
                        "email": email,
                    },
                )
                AuthenticationRepository(db_path).create_account(
                    f"login.{role}@example.invalid", person_id=person["id"]
                )
                selections[role] = existing_person(email)

            arguments = bootstrap_arguments()
            arguments["chair"] = selections["chair"]
            arguments["deputy"] = selections["deputy"]
            result = CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual(2, len(result["person_ids"]))
            self.assertEqual(2, len(result["membership_ids"]))
            self.assertEqual(2, len(result["account_ids"]))
            self.assertEqual([], result["invitations"])
            self.assertEqual(0, result["invitations_issued"])

    def test_same_person_cannot_be_chair_and_deputy(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            person = repository.create(
                PERSON,
                {
                    "first_name": "Doppelt",
                    "last_name": "Gewählt",
                    "email": "same@example.invalid",
                },
            )
            AuthenticationRepository(db_path).create_account(
                "same.login@example.invalid", person_id=person["id"]
            )
            arguments = bootstrap_arguments()
            arguments["chair"] = existing_person("same@example.invalid")
            arguments["deputy"] = existing_person("same@example.invalid")

            with self.assertRaises(AdminOperationError) as raised:
                CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual("person_conflict", raised.exception.code)
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    0, connection.execute("SELECT count(*) FROM committee").fetchone()[0]
                )

    def test_conflicting_account_requires_explicit_clarification_and_rolls_back(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            repository.create(
                PERSON,
                {
                    "first_name": "Ziel",
                    "last_name": "Person",
                    "email": "conflict@example.invalid",
                },
            )
            AuthenticationRepository(db_path).create_account("conflict@example.invalid")
            arguments = bootstrap_arguments()
            arguments["chair"] = existing_person("conflict@example.invalid")

            with self.assertRaisesRegex(AdminOperationError, "requires clarification") as raised:
                CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual("account_conflict", raised.exception.code)
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    0, connection.execute("SELECT count(*) FROM committee").fetchone()[0]
                )
                self.assertEqual(
                    0,
                    connection.execute("SELECT count(*) FROM committee_member").fetchone()[0],
                )
                self.assertEqual(
                    0,
                    connection.execute("SELECT count(*) FROM committee_admin_operation").fetchone()[
                        0
                    ],
                )

    def test_operator_account_cannot_become_committee_leadership(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            repository = ResourceRepository(db_path)
            person = repository.create(
                PERSON,
                {
                    "first_name": "Technik",
                    "last_name": "Operator",
                    "email": "operator.person@example.invalid",
                },
            )
            AuthenticationRepository(db_path).create_account(
                "operator@example.invalid", person_id=person["id"], is_operator=True
            )
            arguments = bootstrap_arguments()
            arguments["chair"] = existing_person("operator.person@example.invalid")

            with self.assertRaises(AdminOperationError) as raised:
                CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            self.assertEqual("account_conflict", raised.exception.code)

    def test_wrongly_linked_and_inactive_accounts_are_clarification_conflicts(self) -> None:
        for case in ("wrongly_linked", "inactive"):
            with self.subTest(case=case), TempDatabase(with_seed=False) as db_path:
                repository = ResourceRepository(db_path)
                target = repository.create(
                    PERSON,
                    {
                        "first_name": "Ziel",
                        "last_name": "Person",
                        "email": "target@example.invalid",
                    },
                )
                authentication = AuthenticationRepository(db_path)
                if case == "wrongly_linked":
                    other = repository.create(
                        PERSON,
                        {
                            "first_name": "Andere",
                            "last_name": "Person",
                            "email": "other@example.invalid",
                        },
                    )
                    authentication.create_account("target@example.invalid", person_id=other["id"])
                else:
                    account = authentication.create_account(
                        "login@example.invalid", person_id=target["id"]
                    )
                    authentication.set_account_active(account["id"], False)
                arguments = bootstrap_arguments()
                arguments["chair"] = existing_person("target@example.invalid")

                with self.assertRaises(AdminOperationError) as raised:
                    CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

                self.assertEqual("account_conflict", raised.exception.code)
                with sqlite3.connect(db_path) as connection:
                    self.assertEqual(
                        0,
                        connection.execute("SELECT count(*) FROM committee").fetchone()[0],
                    )

    def test_idempotent_replay_omits_secret_and_changed_input_conflicts(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = CommitteeAdminService(db_path)
            arguments = bootstrap_arguments()
            first = service.bootstrap(arguments, now=self.now)
            replay = service.bootstrap(arguments, now=self.now + timedelta(minutes=1))

            self.assertFalse(first["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(first["committee_id"], replay["committee_id"])
            self.assertEqual([], replay["invitations"])
            self.assertEqual(1, replay["invitations_issued"])

            changed = json.loads(json.dumps(arguments))
            changed["committee"]["name"] = "Anderer Ausschuss"
            with self.assertRaises(AdminOperationError) as raised:
                service.bootstrap(changed, now=self.now)
            self.assertEqual("idempotency_conflict", raised.exception.code)

            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    1, connection.execute("SELECT count(*) FROM committee").fetchone()[0]
                )
                self.assertEqual(
                    1, connection.execute("SELECT count(*) FROM auth_token").fetchone()[0]
                )

    def test_concurrent_identical_bootstrap_issues_secret_once(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = CommitteeAdminService(db_path)
            arguments = bootstrap_arguments("concurrent-001")

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _: service.bootstrap(arguments, now=self.now),
                        range(2),
                    )
                )

            self.assertEqual(1, sum(not result["replayed"] for result in results))
            self.assertEqual(1, sum(bool(result["invitations"]) for result in results))
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    1, connection.execute("SELECT count(*) FROM committee").fetchone()[0]
                )
                self.assertEqual(1, connection.execute("SELECT count(*) FROM person").fetchone()[0])
                self.assertEqual(
                    1, connection.execute("SELECT count(*) FROM user_account").fetchone()[0]
                )

    def test_failure_after_partial_work_rolls_back_every_object(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            arguments = bootstrap_arguments()
            arguments["deputy"] = new_person("chair@example.invalid", side="school")

            with self.assertRaises(AdminOperationError):
                CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)

            with sqlite3.connect(db_path) as connection:
                for table in (
                    "committee",
                    "person",
                    "user_account",
                    "auth_token",
                    "committee_member",
                    "committee_admin_operation",
                ):
                    self.assertEqual(
                        0,
                        connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
                        table,
                    )

    def test_legacy_committee_can_be_completed_once_without_changing_master_data(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            committee = ResourceRepository(db_path).create(
                COMMITTEE,
                {
                    "name": "Altbestand",
                    "ihk": "IHK Bestand",
                    "occupation": "Bestandsberuf",
                },
            )
            arguments = {
                "idempotency_key": "complete-001",
                "committee_id": committee["id"],
                "chair": new_person("legacy.chair@example.invalid"),
            }

            result = CommitteeAdminService(db_path).complete(arguments, now=self.now)

            self.assertEqual("ready", result["bootstrap_state"])
            with sqlite3.connect(db_path) as connection:
                unchanged = connection.execute(
                    "SELECT name, ihk, occupation FROM committee WHERE id = ?",
                    (committee["id"],),
                ).fetchone()
            self.assertEqual(("Altbestand", "IHK Bestand", "Bestandsberuf"), unchanged)

            changed_key = dict(arguments)
            changed_key["idempotency_key"] = "complete-002"
            with self.assertRaises(AdminOperationError) as raised:
                CommitteeAdminService(db_path).complete(changed_key, now=self.now)
            self.assertEqual("committee_conflict", raised.exception.code)

    def test_expired_invitation_is_reissued_and_previous_token_invalidated(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = CommitteeAdminService(db_path)
            created = service.bootstrap(bootstrap_arguments(), now=self.now)
            old_token = created["invitations"][0]["token"]
            reinvited = service.reinvite(
                {
                    "idempotency_key": "reinvite-001",
                    "committee_id": created["committee_id"],
                    "email": "chair@example.invalid",
                },
                now=self.now + timedelta(hours=25),
            )

            self.assertEqual(1, reinvited["invitations_issued"])
            self.assertNotEqual(old_token, reinvited["invitations"][0]["token"])
            with session_scope(db_path) as session:
                tokens = session.scalars(select(AuthToken).order_by(AuthToken.id)).all()
                self.assertIsNotNone(tokens[0].consumed_at)
                self.assertIsNone(tokens[1].consumed_at)

            replay = service.reinvite(
                {
                    "idempotency_key": "reinvite-001",
                    "committee_id": created["committee_id"],
                    "email": "chair@example.invalid",
                },
                now=self.now + timedelta(hours=26),
            )
            self.assertEqual([], replay["invitations"])

    def test_activated_chair_and_deputy_receive_only_their_committee_scope(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            arguments = bootstrap_arguments()
            arguments["deputy"] = new_person("deputy@example.invalid", side="school")
            created = CommitteeAdminService(db_path).bootstrap(arguments, now=self.now)
            local_auth = LocalAuthService(db_path)

            for invitation in created["invitations"]:
                preparation = local_auth.prepare_invitation(invitation["token"], now=self.now)
                assert preparation.totp_secret is not None
                local_auth.activate_invitation(
                    invitation["token"],
                    "correct horse battery staple",
                    preparation.totp_secret,
                    pyotp.TOTP(preparation.totp_secret).at(self.now),
                    now=self.now,
                )

            authentication = AuthenticationRepository(db_path)
            for account_id in created["account_ids"]:
                credentials = authentication.create_session(account_id)
                context = authentication.authenticate(credentials.token)
                assert context is not None
                scope = AuthorizationService(db_path).scope(context)
                self.assertEqual({created["committee_id"]}, set(scope.committee_ids))
                self.assertEqual({created["committee_id"]}, set(scope.management_committee_ids))

    def test_deactivation_changes_only_target_committee_scope_and_reactivation_restores_it(
        self,
    ) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service = CommitteeAdminService(db_path)
            first = service.bootstrap(bootstrap_arguments("bootstrap-first"), now=self.now)
            person_id = first["person_ids"][0]
            with session_scope(db_path) as session:
                person = session.get(Person, person_id)
                assert person is not None
                email = person.email
            second_arguments = bootstrap_arguments("bootstrap-second")
            second_arguments["committee"]["name"] = "Prüfungsausschuss Süd"
            second_arguments["chair"] = existing_person(email)
            second = service.bootstrap(second_arguments, now=self.now)

            account_id = first["account_ids"][0]
            authentication = AuthenticationRepository(db_path)
            credentials = authentication.create_session(account_id)
            context = authentication.authenticate(credentials.token)
            assert context is not None
            self.assertEqual(
                {first["committee_id"], second["committee_id"]},
                set(AuthorizationService(db_path).scope(context).committee_ids),
            )

            service.deactivate(
                {
                    "idempotency_key": "deactivate-first",
                    "committee_id": first["committee_id"],
                    "reason": "Temporäre technische Sperre",
                },
                now=self.now,
            )
            self.assertIsNotNone(authentication.authenticate(credentials.token))
            self.assertEqual(
                {second["committee_id"]},
                set(AuthorizationService(db_path).scope(context).committee_ids),
            )

            service.reactivate(
                {
                    "idempotency_key": "reactivate-first",
                    "committee_id": first["committee_id"],
                    "reason": "Technische Prüfung abgeschlossen",
                },
                now=self.now,
            )
            self.assertEqual(
                {first["committee_id"], second["committee_id"]},
                set(AuthorizationService(db_path).scope(context).committee_ids),
            )

    def test_unresolved_committee_cannot_be_reactivated(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            committee = ResourceRepository(db_path).create(
                COMMITTEE,
                {"name": "Ungeklärt", "ihk": "IHK Test", "occupation": "Testberuf"},
            )
            service = CommitteeAdminService(db_path)
            service.deactivate(
                {
                    "idempotency_key": "deactivate-unresolved",
                    "committee_id": committee["id"],
                    "reason": "Ungeklärter Altbestand",
                },
                now=self.now,
            )

            with self.assertRaises(AdminOperationError) as raised:
                service.reactivate(
                    {
                        "idempotency_key": "reactivate-unresolved",
                        "committee_id": committee["id"],
                        "reason": "Ohne Vorsitz nicht zulässig",
                    },
                    now=self.now,
                )
            self.assertEqual("committee_conflict", raised.exception.code)

    def test_evidence_contains_no_authentication_material(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            created = CommitteeAdminService(db_path).bootstrap(bootstrap_arguments(), now=self.now)
            token = created["invitations"][0]["token"]
            with session_scope(db_path) as session:
                evidence = session.scalar(select(CommitteeAdminOperation))
                account = session.scalar(select(UserAccount))
                self.assertIsNotNone(evidence)
                self.assertIsNotNone(account)
                encoded = json.dumps(
                    {
                        "response": evidence.response_json,
                        "persons": evidence.person_ids_json,
                        "accounts": evidence.account_ids_json,
                    }
                )
                self.assertNotIn(token, encoded)
                self.assertNotIn("password", encoded)
                self.assertEqual(1, session.scalar(select(func.count(Committee.id))))


if __name__ == "__main__":
    unittest.main()
