"""Operator-only account bootstrap, invitation, and recovery operations.

This module is deliberately not an HTTP handler.  It uses the same SQLAlchemy
session boundary and authentication repository as the application while
returning one-time token material only to its direct caller.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .auth import EMAIL_PATTERN, AuthenticationError, AuthenticationRepository
from .database import DEFAULT_DB_PATH, session_scope
from .models import AuthToken, UserAccount

INVITATION_TTL = timedelta(hours=24)
RECOVERY_TTL = timedelta(minutes=30)
TokenKind = Literal["invitation", "recovery"]


class AdminOperationError(ValueError):
    """A safe, stable operator operation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IssuedAuthToken:
    """Token material returned once by an issue operation."""

    account: dict[str, object]
    kind: TokenKind
    token: str = field(repr=False)
    expires_at: str = ""


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise AdminOperationError("invalid_request", "A valid account email is required")
    return normalized


class OperatorAuthService:
    """Transactional account and one-time token operations for the CLI."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.authentication = AuthenticationRepository(db_path)

    def bootstrap(self, email: str, *, now: datetime | None = None) -> IssuedAuthToken:
        """Create the sole first operator and its initial invitation."""
        normalized_email = _email(email)
        current = _now(now)
        try:
            with session_scope(self.db_path) as session:
                if session.scalar(select(UserAccount.id).limit(1)) is not None:
                    raise AdminOperationError(
                        "bootstrap_not_empty", "Bootstrap requires an instance without accounts"
                    )
                account = UserAccount(
                    email=normalized_email,
                    person_id=None,
                    is_operator=1,
                    is_active=1,
                )
                session.add(account)
                session.flush()
                return self._issue_token(session, account, "invitation", current)
        except AdminOperationError:
            raise
        except IntegrityError as error:
            raise AdminOperationError(
                "bootstrap_not_empty", "Bootstrap could not create a second operator"
            ) from error
        except (OSError, AuthenticationError) as error:
            raise AdminOperationError("persistence_error", "Account bootstrap failed") from error

    def invite(self, email: str, *, now: datetime | None = None) -> IssuedAuthToken:
        """Create a non-operator account and a 24-hour invitation token."""
        normalized_email = _email(email)
        current = _now(now)
        try:
            with session_scope(self.db_path) as session:
                if (
                    session.scalar(
                        select(UserAccount.id).where(UserAccount.email == normalized_email)
                    )
                    is not None
                ):
                    raise AdminOperationError("account_exists", "An account already exists")
                account = UserAccount(
                    email=normalized_email,
                    person_id=None,
                    is_operator=0,
                    is_active=1,
                )
                session.add(account)
                session.flush()
                return self._issue_token(session, account, "invitation", current)
        except AdminOperationError:
            raise
        except IntegrityError as error:
            raise AdminOperationError("account_exists", "An account already exists") from error
        except (OSError, AuthenticationError) as error:
            raise AdminOperationError(
                "persistence_error", "Invitation could not be created"
            ) from error

    def disable(self, account_id: int) -> tuple[dict[str, object], int]:
        """Disable an account and revoke all of its active sessions atomically."""
        if account_id <= 0:
            raise AdminOperationError("invalid_request", "Account id must be positive")
        account, revoked_sessions = self.authentication.disable_account(account_id)
        if account is None:
            raise AdminOperationError("account_not_found", "Account was not found")
        return account, revoked_sessions

    def recover(
        self,
        *,
        account_id: int | None = None,
        email: str | None = None,
        now: datetime | None = None,
    ) -> IssuedAuthToken:
        """Issue a 30-minute recovery token for one active account."""
        if (account_id is None) == (email is None):
            raise AdminOperationError("invalid_request", "Provide exactly one account id or email")
        current = _now(now)
        normalized_email = _email(email) if email is not None else None
        with session_scope(self.db_path) as session:
            query = select(UserAccount)
            if account_id is not None:
                if account_id <= 0:
                    raise AdminOperationError("invalid_request", "Account id must be positive")
                query = query.where(UserAccount.id == account_id)
            else:
                query = query.where(UserAccount.email == normalized_email)
            account = session.scalars(query).first()
            if account is None or not account.is_active:
                raise AdminOperationError("account_not_found", "Active account was not found")
            return self._issue_token(session, account, "recovery", current)

    def consume(
        self,
        token: str,
        kind: TokenKind,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Atomically consume one unexpired token for a later auth flow."""
        if kind not in ("invitation", "recovery") or not token or len(token) > 256:
            raise AdminOperationError("token_invalid", "Token is invalid, expired, or already used")
        current = _now(now)
        token_hash = _digest(token)
        with session_scope(self.db_path) as session:
            consumed_at = _timestamp(current)
            changed = session.execute(
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
                raise AdminOperationError(
                    "token_invalid", "Token is invalid, expired, or already used"
                )
            record = session.scalars(
                select(AuthToken).where(
                    AuthToken.kind == kind,
                    AuthToken.token_hash == token_hash,
                )
            ).first()
            if record is None or not hmac.compare_digest(record.token_hash, token_hash):
                raise AdminOperationError(
                    "token_invalid", "Token is invalid, expired, or already used"
                )
            account = session.get(UserAccount, record.account_id)
            if account is None or not account.is_active:
                raise AdminOperationError(
                    "token_invalid", "Token is invalid, expired, or already used"
                )
            return AuthenticationRepository._account_view(account)

    @staticmethod
    def _issue_token(
        session,
        account: UserAccount,
        kind: TokenKind,
        current: datetime,
    ) -> IssuedAuthToken:
        token = secrets.token_urlsafe(32)
        expires_at = _timestamp(
            current + (INVITATION_TTL if kind == "invitation" else RECOVERY_TTL)
        )
        session.add(
            AuthToken(
                account_id=account.id,
                kind=kind,
                token_hash=_digest(token),
                created_at=_timestamp(current),
                expires_at=expires_at,
            )
        )
        session.flush()
        return IssuedAuthToken(
            account=AuthenticationRepository._account_view(account),
            kind=kind,
            token=token,
            expires_at=expires_at,
        )
