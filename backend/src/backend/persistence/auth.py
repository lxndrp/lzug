"""SQLite persistence adapter for Identity account and session operations."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.models import AuthSession, AuthToken, UserAccount

SESSION_TTL = timedelta(hours=8)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthenticationError(ValueError):
    """Raised for invalid internal account or session operations."""


@dataclass(frozen=True)
class SessionCredentials:
    """One-time bearer material returned only to the caller creating a session."""

    session_id: int
    account_id: int
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: str = ""


@dataclass(frozen=True)
class AuthContext:
    """Validated identity used by the HTTP layer and later authorization."""

    session_id: int
    account_id: int
    person_id: int | None
    is_operator: bool


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SQLiteAuthenticationRepository:
    """Internal account/session repository using the shared SQLAlchemy boundary."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def create_account(
        self,
        email: str,
        *,
        person_id: int | None = None,
        is_operator: bool = False,
        password_hash: str | None = None,
    ) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized_email):
            raise AuthenticationError("A valid account email is required")
        with session_scope(self.db_path) as session:
            account = UserAccount(
                email=normalized_email,
                person_id=person_id,
                password_hash=password_hash,
                is_operator=int(is_operator),
                is_active=1,
            )
            session.add(account)
            session.flush()
            return self._account_view(account)

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            account = session.get(UserAccount, account_id)
            return self._account_view(account) if account else None

    def set_account_active(self, account_id: int, is_active: bool) -> bool:
        with session_scope(self.db_path) as session:
            account = session.get(UserAccount, account_id)
            if account is None:
                return False
            account.is_active = int(is_active)
            account.updated_at = _timestamp(datetime.now(UTC))
            if not is_active:
                self._revoke_account_sessions(session, account_id, "account-disabled")
            return True

    def disable_account(self, account_id: int) -> tuple[dict[str, Any] | None, int]:
        """Disable one account and revoke its sessions in the same transaction."""
        with session_scope(self.db_path) as session:
            account = session.get(UserAccount, account_id)
            if account is None:
                return None, 0
            account.is_active = 0
            account.updated_at = _timestamp(datetime.now(UTC))
            revoked_sessions = self._revoke_account_sessions(
                session, account_id, "account-disabled"
            )
            return self._account_view(account), revoked_sessions

    def create_session(
        self,
        account_id: int,
        *,
        now: datetime | None = None,
        ttl: timedelta = SESSION_TTL,
    ) -> SessionCredentials:
        current = _now(now)
        if ttl <= timedelta(0):
            raise AuthenticationError("Session lifetime must be positive")
        with session_scope(self.db_path) as session:
            account = self._active_account(session, account_id)
            if account is None:
                raise AuthenticationError("Account is not active")
            return self._create_session(session, account, current, ttl)

    def authenticate(self, token: str | None, *, now: datetime | None = None) -> AuthContext | None:
        if not token or len(token) > 256:
            return None
        current = _now(now)
        with session_scope(self.db_path) as session:
            auth_session = session.scalars(
                select(AuthSession).where(AuthSession.token_hash == _digest(token))
            ).first()
            if auth_session is None:
                return None
            if not hmac.compare_digest(auth_session.token_hash, _digest(token)):
                return None
            if (
                auth_session.revoked_at is not None
                or _parse_timestamp(auth_session.expires_at) <= current
            ):
                return None
            account = self._active_account(session, auth_session.account_id)
            if account is None:
                return None
            return self._context(auth_session, account)

    def verify_csrf(self, context: AuthContext, csrf_token: str | None) -> bool:
        if not csrf_token or len(csrf_token) > 256:
            return False
        with session_scope(self.db_path) as session:
            auth_session = session.get(AuthSession, context.session_id)
            return bool(
                auth_session
                and hmac.compare_digest(auth_session.csrf_token_hash, _digest(csrf_token))
            )

    def rotate_session(
        self,
        token: str | None,
        *,
        now: datetime | None = None,
        ttl: timedelta = SESSION_TTL,
    ) -> SessionCredentials | None:
        if not token or len(token) > 256 or ttl <= timedelta(0):
            return None
        current = _now(now)
        with session_scope(self.db_path) as session:
            old = session.scalars(
                select(AuthSession).where(AuthSession.token_hash == _digest(token))
            ).first()
            if (
                old is None
                or old.revoked_at is not None
                or _parse_timestamp(old.expires_at) <= current
            ):
                return None
            account = self._active_account(session, old.account_id)
            if account is None:
                return None
            old.revoked_at = _timestamp(current)
            old.revoke_reason = "rotated"
            return self._create_session(session, account, current, ttl, rotated_from_id=old.id)

    def revoke_session(self, token: str | None, *, reason: str = "logout") -> bool:
        if not token or len(token) > 256:
            return False
        with session_scope(self.db_path) as session:
            auth_session = session.scalars(
                select(AuthSession).where(AuthSession.token_hash == _digest(token))
            ).first()
            if auth_session is None or auth_session.revoked_at is not None:
                return False
            auth_session.revoked_at = _timestamp(datetime.now(UTC))
            auth_session.revoke_reason = reason
            return True

    def revoke_account_sessions(self, account_id: int, *, reason: str = "account-revoked") -> int:
        with session_scope(self.db_path) as session:
            return self._revoke_account_sessions(session, account_id, reason)

    def _create_session(
        self,
        session,
        account: UserAccount,
        current: datetime,
        ttl: timedelta,
        rotated_from_id: int | None = None,
    ) -> SessionCredentials:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        auth_session = AuthSession(
            account_id=account.id,
            token_hash=_digest(token),
            csrf_token_hash=_digest(csrf_token),
            created_at=_timestamp(current),
            expires_at=_timestamp(current + ttl),
            last_seen_at=_timestamp(current),
            rotated_from_id=rotated_from_id,
        )
        session.add(auth_session)
        session.flush()
        return SessionCredentials(
            session_id=auth_session.id,
            account_id=account.id,
            token=token,
            csrf_token=csrf_token,
            expires_at=auth_session.expires_at,
        )

    def _active_account(self, session, account_id: int) -> UserAccount | None:
        account = session.get(UserAccount, account_id)
        return account if account and account.is_active else None

    def _context(self, auth_session: AuthSession, account: UserAccount) -> AuthContext:
        return AuthContext(
            session_id=auth_session.id,
            account_id=account.id,
            person_id=account.person_id,
            is_operator=bool(account.is_operator),
        )

    def _revoke_account_sessions(self, session, account_id: int, reason: str) -> int:
        current = _timestamp(datetime.now(UTC))
        active = session.scalars(
            select(AuthSession).where(
                AuthSession.account_id == account_id,
                AuthSession.revoked_at.is_(None),
            )
        ).all()
        for auth_session in active:
            auth_session.revoked_at = current
            auth_session.revoke_reason = reason
        return len(active)

    @staticmethod
    def _account_view(account: UserAccount) -> dict[str, Any]:
        return {
            "id": account.id,
            "person_id": account.person_id,
            "email": account.email,
            "is_operator": bool(account.is_operator),
            "is_active": bool(account.is_active),
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }


class SQLiteOperatorAuthUnitOfWork:
    """Account-bootstrap and one-time-token operations on one SQLite session."""

    def __init__(self, session) -> None:
        self._session = session

    def account_exists(self, email: str | None = None) -> bool:
        statement = select(UserAccount.id)
        if email is not None:
            statement = statement.where(UserAccount.email == email)
        return self._session.scalar(statement.limit(1)) is not None

    def create_account(self, email: str, *, is_operator: bool) -> dict[str, Any] | None:
        account = UserAccount(
            email=email,
            person_id=None,
            is_operator=int(is_operator),
            is_active=1,
        )
        try:
            with self._session.begin_nested():
                self._session.add(account)
                self._session.flush()
        except IntegrityError:
            return None
        return SQLiteAuthenticationRepository._account_view(account)

    def active_account(
        self, *, account_id: int | None = None, email: str | None = None
    ) -> dict[str, Any] | None:
        statement = select(UserAccount).where(UserAccount.is_active == 1)
        if account_id is not None:
            statement = statement.where(UserAccount.id == account_id)
        if email is not None:
            statement = statement.where(UserAccount.email == email)
        account = self._session.scalars(statement).first()
        return SQLiteAuthenticationRepository._account_view(account) if account else None

    def issue_token(
        self,
        account_id: int,
        kind: str,
        token_hash: str,
        created_at: str,
        expires_at: str,
    ) -> None:
        self._session.add(
            AuthToken(
                account_id=account_id,
                kind=kind,
                token_hash=token_hash,
                created_at=created_at,
                expires_at=expires_at,
            )
        )
        self._session.flush()

    def consume_token(self, token_hash: str, kind: str, consumed_at: str) -> dict[str, Any] | None:
        changed = self._session.execute(
            update(AuthToken)
            .where(
                AuthToken.kind == kind,
                AuthToken.token_hash == token_hash,
                AuthToken.consumed_at.is_(None),
                AuthToken.expires_at > consumed_at,
            )
            .values(consumed_at=consumed_at)
        ).rowcount
        if changed != 1:
            return None
        record = self._session.scalars(
            select(AuthToken).where(
                AuthToken.kind == kind,
                AuthToken.token_hash == token_hash,
            )
        ).first()
        account = self._session.get(UserAccount, record.account_id) if record else None
        if account is None or not account.is_active:
            return None
        return SQLiteAuthenticationRepository._account_view(account)

    def disable_account(self, account_id: int, now: str) -> tuple[dict[str, Any] | None, int]:
        account = self._session.get(UserAccount, account_id)
        if account is None:
            return None, 0
        account.is_active = 0
        account.updated_at = now
        active = self._session.scalars(
            select(AuthSession).where(
                AuthSession.account_id == account_id,
                AuthSession.revoked_at.is_(None),
            )
        ).all()
        for auth_session in active:
            auth_session.revoked_at = now
            auth_session.revoke_reason = "account-disabled"
        return SQLiteAuthenticationRepository._account_view(account), len(active)


class SQLiteOperatorAuthUnitOfWorkFactory:
    """Open account and token writes within one SQLAlchemy transaction."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def unit_of_work(self) -> Iterator[SQLiteOperatorAuthUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield SQLiteOperatorAuthUnitOfWork(session)
