"""Operator-only account bootstrap, invitation, and recovery use cases."""

from __future__ import annotations

import hashlib
import secrets
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from backend.identity.errors import AdminOperationError
from backend.identity.validation import EMAIL_PATTERN

INVITATION_TTL = timedelta(hours=24)
RECOVERY_TTL = timedelta(minutes=30)
TokenKind = Literal["invitation", "recovery"]


class OperatorAuthUnitOfWork(Protocol):
    """Identity-owned account and token writes within a single transaction."""

    def account_exists(self, email: str | None = None) -> bool: ...

    def create_account(self, email: str, *, is_operator: bool) -> dict[str, object] | None: ...

    def active_account(
        self, *, account_id: int | None = None, email: str | None = None
    ) -> dict[str, object] | None: ...

    def issue_token(
        self,
        account_id: int,
        kind: str,
        token_hash: str,
        created_at: str,
        expires_at: str,
    ) -> None: ...

    def consume_token(
        self, token_hash: str, kind: str, consumed_at: str
    ) -> dict[str, object] | None: ...

    def disable_account(
        self, account_id: int, now: str
    ) -> tuple[dict[str, object] | None, int]: ...


class OperatorAuthUnitOfWorkFactory(Protocol):
    """Create an Identity authentication write transaction."""

    def unit_of_work(self) -> AbstractContextManager[OperatorAuthUnitOfWork]: ...


@dataclass(frozen=True)
class IssuedAuthToken:
    """Token material returned once to the operator."""

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
    """Operator commands expressed against Identity-owned persistence ports."""

    def __init__(self, unit_of_work_factory: OperatorAuthUnitOfWorkFactory):
        self.unit_of_work_factory = unit_of_work_factory

    def bootstrap(self, email: str, *, now: datetime | None = None) -> IssuedAuthToken:
        """Create the sole first operator and its initial invitation atomically."""
        normalized_email = _email(email)
        current = _now(now)
        try:
            with self.unit_of_work_factory.unit_of_work() as uow:
                if uow.account_exists():
                    raise AdminOperationError(
                        "bootstrap_not_empty", "Bootstrap requires an instance without accounts"
                    )
                account = uow.create_account(normalized_email, is_operator=True)
                if account is None:
                    raise AdminOperationError(
                        "bootstrap_not_empty", "Bootstrap could not create the first operator"
                    )
                return self._issue_token(uow, account, "invitation", current)
        except AdminOperationError:
            raise
        except Exception as error:
            raise AdminOperationError("persistence_error", "Account bootstrap failed") from error

    def invite(self, email: str, *, now: datetime | None = None) -> IssuedAuthToken:
        """Create a non-operator account and a 24-hour invitation token atomically."""
        normalized_email = _email(email)
        current = _now(now)
        try:
            with self.unit_of_work_factory.unit_of_work() as uow:
                if uow.account_exists(normalized_email):
                    raise AdminOperationError("account_exists", "An account already exists")
                account = uow.create_account(normalized_email, is_operator=False)
                if account is None:
                    raise AdminOperationError("account_exists", "An account already exists")
                return self._issue_token(uow, account, "invitation", current)
        except AdminOperationError:
            raise
        except Exception as error:
            raise AdminOperationError(
                "persistence_error", "Invitation could not be created"
            ) from error

    def disable(self, account_id: int) -> tuple[dict[str, object], int]:
        """Disable an account and revoke its sessions in one Identity UoW."""
        if account_id <= 0:
            raise AdminOperationError("invalid_request", "Account id must be positive")
        with self.unit_of_work_factory.unit_of_work() as uow:
            account, revoked_sessions = uow.disable_account(account_id, _timestamp(_now()))
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
        if account_id is not None and account_id <= 0:
            raise AdminOperationError("invalid_request", "Account id must be positive")
        current = _now(now)
        normalized_email = _email(email) if email is not None else None
        with self.unit_of_work_factory.unit_of_work() as uow:
            account = uow.active_account(account_id=account_id, email=normalized_email)
            if account is None:
                raise AdminOperationError("account_not_found", "Active account was not found")
            return self._issue_token(uow, account, "recovery", current)

    def consume(
        self,
        token: str,
        kind: TokenKind,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Atomically consume one unexpired invitation or recovery token."""
        if kind not in ("invitation", "recovery") or not token or len(token) > 256:
            raise AdminOperationError("token_invalid", "Token is invalid, expired, or already used")
        with self.unit_of_work_factory.unit_of_work() as uow:
            account = uow.consume_token(_digest(token), kind, _timestamp(_now(now)))
            if account is None:
                raise AdminOperationError(
                    "token_invalid", "Token is invalid, expired, or already used"
                )
            return account

    @staticmethod
    def _issue_token(
        uow: OperatorAuthUnitOfWork,
        account: dict[str, object],
        kind: TokenKind,
        current: datetime,
    ) -> IssuedAuthToken:
        token = secrets.token_urlsafe(32)
        expires_at = _timestamp(
            current + (INVITATION_TTL if kind == "invitation" else RECOVERY_TTL)
        )
        uow.issue_token(int(account["id"]), kind, _digest(token), _timestamp(current), expires_at)
        return IssuedAuthToken(account, kind, token, expires_at)
