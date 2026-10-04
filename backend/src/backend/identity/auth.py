"""Transport-neutral identity and session contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

SESSION_TTL = timedelta(hours=8)


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
    """Validated identity used by authorization and transport adapters."""

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


class AuthenticationRepository(Protocol):
    """Identity-owned account/session operations implemented by persistence."""

    def create_account(
        self,
        email: str,
        *,
        person_id: int | None = None,
        is_operator: bool = False,
        password_hash: str | None = None,
    ) -> dict[str, Any]: ...

    def get_account(self, account_id: int) -> dict[str, Any] | None: ...

    def set_account_active(self, account_id: int, is_active: bool) -> bool: ...

    def disable_account(self, account_id: int) -> tuple[dict[str, Any] | None, int]: ...

    def create_session(
        self, account_id: int, *, now: datetime | None = None, ttl: timedelta = SESSION_TTL
    ) -> SessionCredentials: ...

    def authenticate(
        self, token: str | None, *, now: datetime | None = None
    ) -> AuthContext | None: ...

    def verify_csrf(self, context: AuthContext, csrf_token: str | None) -> bool: ...

    def rotate_session(
        self, token: str | None, *, now: datetime | None = None, ttl: timedelta = SESSION_TTL
    ) -> SessionCredentials | None: ...

    def revoke_session(self, token: str | None, *, reason: str = "logout") -> bool: ...

    def revoke_account_sessions(
        self, account_id: int, *, reason: str = "account-revoked"
    ) -> int: ...
