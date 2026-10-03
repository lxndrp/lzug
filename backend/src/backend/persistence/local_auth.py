"""SQLite adapter for the Identity local-authentication ports."""

from __future__ import annotations

import binascii
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import or_, select, update

from backend.identity.auth import SessionCredentials
from backend.identity.local_auth import (
    LocalAuthAccount,
    LocalAuthRecoveryCode,
    LocalAuthToken,
    LocalAuthUnitOfWork,
)
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import DEFAULT_DB_PATH, mutation_scope, session_scope
from backend.persistence.models import AuthRecoveryCode, AuthToken, UserAccount
from backend.settings import LocalAuthSettings, RuntimeSettings


def _timestamp(value: datetime) -> str:
    current = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return current.isoformat(timespec="seconds")


def _account(row: UserAccount) -> LocalAuthAccount:
    return LocalAuthAccount(
        id=row.id,
        person_id=row.person_id,
        email=row.email,
        is_operator=bool(row.is_operator),
        is_active=bool(row.is_active),
        password_hash=row.password_hash,
        totp_enabled=bool(row.totp_enabled),
        totp_secret_encrypted=row.totp_secret_encrypted,
        totp_last_step=row.totp_last_step,
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


class SQLiteLocalAuthUnitOfWorkFactory:
    """Create a single transaction spanning factor changes and session replacement."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        authentication: SQLiteAuthenticationRepository | None = None,
    ):
        self.db_path = Path(db_path)
        self.authentication = authentication or SQLiteAuthenticationRepository(self.db_path)

    @contextmanager
    def unit_of_work(self) -> Iterator[LocalAuthUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield _SQLiteLocalAuthUnitOfWork(session, self.authentication)


class _SQLiteLocalAuthUnitOfWork:
    def __init__(self, session, authentication: SQLiteAuthenticationRepository):
        self.session = session
        self.authentication = authentication

    def account_by_email(self, email: str) -> LocalAuthAccount | None:
        row = self.session.scalars(select(UserAccount).where(UserAccount.email == email)).first()
        return _account(row) if row else None

    def account(self, account_id: int) -> LocalAuthAccount | None:
        row = self.session.get(UserAccount, account_id)
        return _account(row) if row else None

    def valid_token(self, token_hash: str, kind: str, now: str):
        token = self.session.scalars(
            select(AuthToken).where(
                AuthToken.kind == kind,
                AuthToken.token_hash == token_hash,
                AuthToken.consumed_at.is_(None),
                AuthToken.expires_at > now,
            )
        ).first()
        account = self.session.get(UserAccount, token.account_id) if token else None
        if token is None or account is None or not account.is_active:
            return None
        return LocalAuthToken(token.account_id, token.expires_at), _account(account)

    def consume_token(self, token_hash: str, kind: str, now: str) -> LocalAuthAccount | None:
        changed = self.session.execute(
            update(AuthToken)
            .where(
                AuthToken.kind == kind,
                AuthToken.token_hash == token_hash,
                AuthToken.consumed_at.is_(None),
                AuthToken.expires_at > now,
            )
            .values(consumed_at=now)
        ).rowcount
        if changed != 1:
            return None
        token = self.session.scalars(
            select(AuthToken).where(
                AuthToken.kind == kind,
                AuthToken.token_hash == token_hash,
            )
        ).first()
        account = self.session.get(UserAccount, token.account_id) if token else None
        return _account(account) if account and account.is_active else None

    def set_factors(
        self, account_id: int, password_hash: str, encrypted_secret: str, now: str
    ) -> None:
        row = self.session.get(UserAccount, account_id)
        if row is None:
            return
        row.password_hash = password_hash
        row.totp_secret_encrypted = encrypted_secret
        row.totp_last_step = None
        row.totp_enabled = 1
        row.two_factor_enabled = 0
        row.updated_at = now

    def recovery_codes(self, account_id: int) -> tuple[LocalAuthRecoveryCode, ...]:
        rows = self.session.scalars(
            select(AuthRecoveryCode).where(
                AuthRecoveryCode.account_id == account_id,
                AuthRecoveryCode.consumed_at.is_(None),
            )
        ).all()
        return tuple(LocalAuthRecoveryCode(row.id, row.code_hash) for row in rows)

    def add_recovery_codes(self, account_id: int, values: tuple[str, ...], now: str) -> None:
        self.session.add_all(
            AuthRecoveryCode(account_id=account_id, code_hash=value, created_at=now)
            for value in values
        )

    def clear_recovery_codes(self, account_id: int) -> None:
        self.session.query(AuthRecoveryCode).filter(
            AuthRecoveryCode.account_id == account_id
        ).delete(synchronize_session=False)

    def consume_recovery_code(self, code_id: int, now: str) -> bool:
        changed = self.session.execute(
            update(AuthRecoveryCode)
            .where(
                AuthRecoveryCode.id == code_id,
                AuthRecoveryCode.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        ).rowcount
        return changed == 1

    def consume_totp_step(self, account_id: int, step: int) -> bool:
        changed = self.session.execute(
            update(UserAccount)
            .where(
                UserAccount.id == account_id,
                or_(UserAccount.totp_last_step.is_(None), UserAccount.totp_last_step < step),
            )
            .values(totp_last_step=step)
        ).rowcount
        return changed == 1

    def update_password_hash(self, account_id: int, password_hash: str) -> None:
        self.session.execute(
            update(UserAccount)
            .where(UserAccount.id == account_id)
            .values(password_hash=password_hash)
        )

    def set_last_login(self, account_id: int, now: str) -> None:
        self.session.execute(
            update(UserAccount).where(UserAccount.id == account_id).values(last_login_at=now)
        )

    def revoke_sessions(self, account_id: int, reason: str) -> None:
        self.authentication._revoke_account_sessions(self.session, account_id, reason)

    def create_session(self, account_id: int, now: datetime, ttl: timedelta) -> SessionCredentials:
        account = self.session.get(UserAccount, account_id)
        if account is None or not account.is_active:
            raise ValueError("Account is not active")
        return self.authentication._create_session(self.session, account, now, ttl)


class SQLiteLocalAuthenticationKey:
    """Persistent, instance-local TOTP encryption key provider."""

    def __init__(
        self, db_path: Path = DEFAULT_DB_PATH, *, settings: LocalAuthSettings | None = None
    ):
        self.db_path = Path(db_path)
        self.settings = settings

    @property
    def path(self) -> Path:
        return self.db_path.with_name(".lzug-auth.key")

    def get_key(self) -> bytes:
        with mutation_scope(self.db_path):
            try:
                if self.path.exists():
                    key = self.path.read_bytes()
                else:
                    configured = self.settings or RuntimeSettings.from_environment().local_auth
                    value = configured.encryption_key_value
                    key = value.encode("ascii") if value else Fernet.generate_key()
                    try:
                        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    except FileExistsError:
                        key = self.path.read_bytes()
                    else:
                        try:
                            os.write(descriptor, key)
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
                os.chmod(self.path, 0o600)
                Fernet(key)
                return key
            except (OSError, ValueError, binascii.Error) as error:
                from backend.identity.local_auth import LocalAuthError

                raise LocalAuthError(
                    "persistence_error", "Lokale Authentifizierung ist nicht verfügbar."
                ) from error
