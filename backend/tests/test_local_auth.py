from __future__ import annotations

import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pyotp

from backend.identity import local_auth
from backend.identity.admin_service import OperatorAuthService
from backend.identity.local_auth import (
    GENERIC_LOGIN_MESSAGE,
    LocalAuthError,
    LocalAuthService,
    LoginRateLimiter,
)
from backend.tests.helpers import TempDatabase


class LocalAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        LoginRateLimiter.reset()
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def _activate(self, db_path: Path) -> tuple[LocalAuthService, int, str, list[str]]:
        issued = OperatorAuthService(db_path).invite("member@example.invalid", now=self.now)
        service = LocalAuthService(db_path)
        preparation = service.prepare_invitation(issued.token, now=self.now)
        assert preparation.totp_secret is not None
        code = pyotp.TOTP(preparation.totp_secret).at(self.now)
        account, recovery_codes = service.activate_invitation(
            issued.token,
            "correct horse battery staple",
            preparation.totp_secret,
            code,
            now=self.now,
        )
        return service, account["id"], preparation.totp_secret, recovery_codes

    def test_activation_hashes_factors_and_issues_recovery_codes_once(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, account_id, secret, recovery_codes = self._activate(db_path)
            self.assertEqual(10, len(recovery_codes))
            self.assertEqual(10, len(set(recovery_codes)))

            with closing(sqlite3.connect(db_path)) as connection, connection:
                row = connection.execute(
                    "SELECT password_hash, totp_secret_encrypted FROM user_account WHERE id = ?",
                    (account_id,),
                ).fetchone()
                hashes = [
                    item[0]
                    for item in connection.execute("SELECT code_hash FROM auth_recovery_code")
                ]
            self.assertTrue(row[0].startswith("$argon2id$"))
            self.assertNotIn("correct horse battery staple", row[0])
            self.assertNotIn(secret, row[1])
            self.assertTrue(all(item.startswith("$argon2id$") for item in hashes))
            self.assertTrue(
                all(code not in item for code, item in zip(recovery_codes, hashes, strict=True))
            )

            with self.assertRaisesRegex(LocalAuthError, "abgelaufen"):
                service.activate_invitation(
                    "not-the-token",
                    "correct horse battery staple",
                    secret,
                    pyotp.TOTP(secret).at(self.now),
                    now=self.now,
                )

    def test_password_requires_totp_and_replay_is_rejected(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, _account_id, secret, _recovery_codes = self._activate(db_path)
            valid_code = pyotp.TOTP(secret).at(self.now)

            for password, factor in [
                ("wrong password", valid_code),
                ("correct horse battery staple", ""),
                ("correct horse battery staple", "000000"),
            ]:
                with self.assertRaisesRegex(LocalAuthError, GENERIC_LOGIN_MESSAGE):
                    service.login(
                        "member@example.invalid",
                        password,
                        factor,
                        now=self.now,
                    )
            LoginRateLimiter.reset()

            result = service.login(
                "member@example.invalid",
                "correct horse battery staple",
                valid_code,
                now=self.now,
            )
            self.assertEqual(1, result.account_id)
            with self.assertRaisesRegex(LocalAuthError, GENERIC_LOGIN_MESSAGE):
                service.login(
                    "member@example.invalid",
                    "correct horse battery staple",
                    valid_code,
                    now=self.now,
                )

    def test_recovery_code_is_single_use_and_recovery_token_replaces_factors(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, account_id, _secret, recovery_codes = self._activate(db_path)
            LoginRateLimiter.reset()
            result = service.login(
                "member@example.invalid",
                "correct horse battery staple",
                recovery_codes[0],
                now=self.now + timedelta(minutes=1),
            )
            self.assertEqual(account_id, result.account_id)
            with self.assertRaisesRegex(LocalAuthError, GENERIC_LOGIN_MESSAGE):
                service.login(
                    "member@example.invalid",
                    "correct horse battery staple",
                    recovery_codes[0],
                    now=self.now + timedelta(minutes=2),
                )

            recovery = OperatorAuthService(db_path).recover(account_id=account_id, now=self.now)
            new_secret = pyotp.random_base32()
            new_code = pyotp.TOTP(new_secret).at(self.now)
            _account, new_codes = service.complete_recovery(
                recovery.token,
                "a-new-correct-horse-password",
                new_secret,
                new_code,
                now=self.now,
            )
            self.assertEqual(10, len(new_codes))
            LoginRateLimiter.reset()
            self.assertEqual(
                account_id,
                service.login(
                    "member@example.invalid",
                    "a-new-correct-horse-password",
                    new_code,
                    now=self.now + timedelta(seconds=30),
                ).account_id,
            )
            with self.assertRaisesRegex(LocalAuthError, "abgelaufen"):
                service.complete_recovery(
                    recovery.token,
                    "another-password",
                    new_secret,
                    new_code,
                    now=self.now,
                )

    def test_recovery_code_cannot_succeed_twice_in_parallel(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, account_id, _secret, recovery_codes = self._activate(db_path)
            LoginRateLimiter.reset()

            def attempt() -> bool:
                try:
                    return (
                        service.login(
                            "member@example.invalid",
                            "correct horse battery staple",
                            recovery_codes[0],
                            now=self.now,
                        ).account_id
                        == account_id
                    )
                except LocalAuthError:
                    return False

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _unused: attempt(), range(2)))
            self.assertEqual([True, False], sorted(results, reverse=True))

    def test_expired_tokens_and_disabled_accounts_fail_closed(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            issued = OperatorAuthService(db_path).invite("expired@example.invalid", now=self.now)
            service = LocalAuthService(db_path)
            with self.assertRaisesRegex(LocalAuthError, "abgelaufen"):
                service.prepare_invitation(
                    issued.token,
                    now=self.now + timedelta(days=2),
                )

            service, account_id, secret, _codes = self._activate(db_path)
            credentials = service.authentication.create_session(account_id, now=self.now)
            OperatorAuthService(db_path).disable(account_id)
            self.assertIsNone(service.authentication.authenticate(credentials.token, now=self.now))

    def test_unknown_and_passwordless_accounts_perform_dummy_hash_verification(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            OperatorAuthService(db_path).invite("pending@example.invalid", now=self.now)
            service = LocalAuthService(db_path)
            for email in ("unknown@example.invalid", "pending@example.invalid"):
                with (
                    self.subTest(email=email),
                    patch.object(
                        local_auth, "PASSWORD_HASHER", wraps=local_auth.PASSWORD_HASHER
                    ) as hasher,
                    self.assertRaises(LocalAuthError) as raised,
                ):
                    service.login(email, "wrong password", "000000", now=self.now)
                self.assertEqual("login_failed", raised.exception.code)
                self.assertEqual(GENERIC_LOGIN_MESSAGE, str(raised.exception))
                hasher.verify.assert_called_once_with(
                    local_auth._DUMMY_PASSWORD_HASH, "wrong password"
                )

    def test_login_failure_rolls_back_factor_rehash_and_session_revocation(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, account_id, secret, recovery_codes = self._activate(db_path)
            previous = service.authentication.create_session(account_id, now=self.now)
            with closing(sqlite3.connect(db_path)) as connection:
                original_hash = connection.execute(
                    "SELECT password_hash FROM user_account WHERE id = ?", (account_id,)
                ).fetchone()[0]

            for factor in (pyotp.TOTP(secret).at(self.now), recovery_codes[0]):
                with self.subTest(factor_kind="totp" if len(factor) == 6 else "recovery"):
                    with (
                        patch.object(
                            local_auth.PasswordHasher, "check_needs_rehash", return_value=True
                        ),
                        patch.object(
                            service.authentication,
                            "_create_session",
                            side_effect=RuntimeError("test failure"),
                        ),
                        self.assertRaisesRegex(RuntimeError, "test failure"),
                    ):
                        service.login(
                            "member@example.invalid",
                            "correct horse battery staple",
                            factor,
                            now=self.now,
                        )
                    self.assertIsNotNone(
                        service.authentication.authenticate(previous.token, now=self.now)
                    )
                    with closing(sqlite3.connect(db_path)) as connection:
                        state = connection.execute(
                            "SELECT password_hash, totp_last_step, last_login_at "
                            "FROM user_account WHERE id = ?",
                            (account_id,),
                        ).fetchone()
                        self.assertEqual((original_hash, None, None), state)
                        self.assertEqual(
                            0,
                            connection.execute(
                                "SELECT count(*) FROM auth_recovery_code "
                                "WHERE consumed_at IS NOT NULL"
                            ).fetchone()[0],
                        )

            current = service.login(
                "member@example.invalid",
                "correct horse battery staple",
                pyotp.TOTP(secret).at(self.now),
                now=self.now,
            )
            self.assertIsNone(service.authentication.authenticate(previous.token, now=self.now))
            self.assertIsNotNone(
                service.authentication.authenticate(current.credentials.token, now=self.now)
            )
            self.assertIsNone(
                LoginRateLimiter.retry_after("local:member@example.invalid", self.now)
            )

    def test_totp_cannot_succeed_twice_in_parallel(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, _account_id, secret, _codes = self._activate(db_path)
            factor = pyotp.TOTP(secret).at(self.now)

            def attempt() -> bool:
                try:
                    service.login(
                        "member@example.invalid",
                        "correct horse battery staple",
                        factor,
                        now=self.now,
                    )
                    return True
                except LocalAuthError as error:
                    self.assertEqual("login_failed", error.code)
                    return False

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda _: attempt(), range(2)))
            self.assertEqual([False, True], sorted(outcomes))

    def test_login_rate_limit_does_not_reveal_unknown_accounts(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            service, _account_id, _secret, _codes = self._activate(db_path)
            for email in ("unknown@example.invalid", "member@example.invalid"):
                LoginRateLimiter.reset()
                statuses: list[str] = []
                for _ in range(LoginRateLimiter.max_failures + 1):
                    try:
                        service.login(email, "wrong password", "000000", now=self.now)
                    except LocalAuthError as error:
                        statuses.append(error.code)
                self.assertEqual("rate_limited", statuses[-1])


if __name__ == "__main__":
    unittest.main()
