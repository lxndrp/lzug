"""Local password, TOTP, and recovery-factor authentication for #266.

Authentication rules live here; persistence and key storage are supplied through
Identity-owned ports so no SQL, ORM, or filesystem values cross this boundary.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import threading
from collections import defaultdict, deque
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from backend.identity.auth import SESSION_TTL, SessionCredentials

PASSWORD_TIME_COST = 3
PASSWORD_MEMORY_COST = 65_536
PASSWORD_PARALLELISM = 4
PASSWORD_HASH_LENGTH = 32
PASSWORD_SALT_LENGTH = 16
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 1024
TOTP_DIGITS = 6
TOTP_PERIOD = 30
TOTP_VALID_WINDOW = 1
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
GENERIC_LOGIN_MESSAGE = "Anmeldung nicht möglich. Bitte Zugangsdaten prüfen."
GENERIC_FACTOR_MESSAGE = "Die Einrichtung konnte nicht abgeschlossen werden."
GENERIC_TOKEN_MESSAGE = "Der Vorgang ist ungültig, abgelaufen oder bereits abgeschlossen."

PASSWORD_HASHER = PasswordHasher(
    time_cost=PASSWORD_TIME_COST,
    memory_cost=PASSWORD_MEMORY_COST,
    parallelism=PASSWORD_PARALLELISM,
    hash_len=PASSWORD_HASH_LENGTH,
    salt_len=PASSWORD_SALT_LENGTH,
)
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$ho+VvdxQRbUqBsMUGbxbLw$"
    "Tdkd4YiLNQMCXB+dTaAuSm4asMGsDjboW89iU1T5KJ8"
)


class LocalAuthError(ValueError):
    """Safe error that contains no secret or account enumeration detail."""

    def __init__(self, code: str, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class AuthPreparation:
    email: str
    expires_at: str
    totp_secret: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class LocalAuthResult:
    credentials: SessionCredentials
    account_id: int


@dataclass(frozen=True)
class LocalAuthAccount:
    id: int
    person_id: int | None
    email: str
    is_operator: bool
    is_active: bool
    password_hash: str | None
    totp_enabled: bool
    totp_secret_encrypted: str | None
    totp_last_step: int | None
    updated_at: str | None
    created_at: str | None = None

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "email": self.email,
            "is_operator": self.is_operator,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class LocalAuthToken:
    account_id: int
    expires_at: str


@dataclass(frozen=True)
class LocalAuthRecoveryCode:
    id: int
    code_hash: str


class LocalAuthUnitOfWork(Protocol):
    """Identity operations that must share one authentication transaction."""

    def account_by_email(self, email: str) -> LocalAuthAccount | None: ...
    def account(self, account_id: int) -> LocalAuthAccount | None: ...
    def valid_token(
        self, token_hash: str, kind: str, now: str
    ) -> tuple[LocalAuthToken, LocalAuthAccount] | None: ...
    def consume_token(self, token_hash: str, kind: str, now: str) -> LocalAuthAccount | None: ...
    def set_factors(
        self, account_id: int, password_hash: str, encrypted_secret: str, now: str
    ) -> None: ...
    def recovery_codes(self, account_id: int) -> tuple[LocalAuthRecoveryCode, ...]: ...
    def add_recovery_codes(self, account_id: int, values: tuple[str, ...], now: str) -> None: ...
    def clear_recovery_codes(self, account_id: int) -> None: ...
    def consume_recovery_code(self, code_id: int, now: str) -> bool: ...
    def consume_totp_step(self, account_id: int, step: int) -> bool: ...
    def update_password_hash(self, account_id: int, password_hash: str) -> None: ...
    def set_last_login(self, account_id: int, now: str) -> None: ...
    def revoke_sessions(self, account_id: int, reason: str) -> None: ...
    def create_session(
        self, account_id: int, now: datetime, ttl: timedelta
    ) -> SessionCredentials: ...


class LocalAuthUnitOfWorkFactory(Protocol):
    def unit_of_work(self) -> AbstractContextManager[LocalAuthUnitOfWork]: ...


class LocalAuthenticationKey(Protocol):
    def get_key(self) -> bytes: ...


class LoginRateLimiter:
    """Small process-local limiter for one self-hosted HTTP instance."""

    max_failures = 5
    window = timedelta(minutes=5)
    lock = threading.Lock()
    failures: dict[str, deque[datetime]] = defaultdict(deque)

    @classmethod
    def retry_after(cls, key: str, now: datetime) -> int | None:
        with cls.lock:
            attempts = cls.failures[key]
            cls._prune(attempts, now)
            return (
                max(1, int((attempts[0] + cls.window - now).total_seconds()))
                if len(attempts) >= cls.max_failures
                else None
            )

    @classmethod
    def failed(cls, key: str, now: datetime) -> None:
        with cls.lock:
            attempts = cls.failures[key]
            cls._prune(attempts, now)
            attempts.append(now)

    @classmethod
    def succeeded(cls, key: str) -> None:
        with cls.lock:
            cls.failures.pop(key, None)

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.failures.clear()

    @classmethod
    def _prune(cls, attempts: deque[datetime], now: datetime) -> None:
        while attempts and attempts[0] <= now - cls.window:
            attempts.popleft()


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _normalize_email(value: str) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _normalize_secret(value: str) -> str:
    if not isinstance(value, str):
        raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
    secret = "".join(value.split()).upper()
    try:
        decoded = base64.b32decode(secret, casefold=True)
    except (binascii.Error, ValueError) as error:
        raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE) from error
    if len(decoded) < 10 or len(secret) < 16:
        raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
    return secret


def _validate_password(password: str) -> None:
    if (
        not isinstance(password, str)
        or not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
    ):
        raise LocalAuthError(
            "invalid_factor",
            f"Das Kennwort muss mindestens {PASSWORD_MIN_LENGTH} Zeichen enthalten.",
        )


def _validate_totp_code(code: str) -> str:
    if not isinstance(code, str):
        raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
    normalized = code.strip()
    if len(normalized) != TOTP_DIGITS or not normalized.isascii() or not normalized.isdigit():
        raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
    return normalized


def _verify_totp(secret: str, code: str, current: datetime) -> int | None:
    normalized = _validate_totp_code(code)
    timestamp = int(current.timestamp())
    current_step = timestamp // TOTP_PERIOD
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD)
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        step = current_step + offset
        if step >= 0 and hmac.compare_digest(totp.at(timestamp + offset * TOTP_PERIOD), normalized):
            return step
    return None


def _recovery_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(RECOVERY_CODE_LENGTH))


class LocalAuthService:
    """Transactional local authentication and first-factor activation."""

    def __init__(
        self,
        *,
        session_ttl: timedelta = SESSION_TTL,
        unit_of_work_factory: LocalAuthUnitOfWorkFactory,
        key_provider: LocalAuthenticationKey,
    ):
        if session_ttl <= timedelta(0):
            raise ValueError("Session lifetime must be positive")
        self.session_ttl = session_ttl
        self.unit_of_work_factory = unit_of_work_factory
        self.key_provider = key_provider

    def prepare_invitation(self, token: str, *, now: datetime | None = None) -> AuthPreparation:
        email, expiry = self._valid_token(token, "invitation", _now(now))
        return AuthPreparation(email, expiry, pyotp.random_base32(length=32))

    def activate_invitation(
        self,
        token: str,
        password: str,
        totp_secret: str,
        totp_code: str,
        *,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        current = _now(now)
        _validate_password(password)
        secret = _normalize_secret(totp_secret)
        if _verify_totp(secret, totp_code, current) is None:
            raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
        with self.unit_of_work_factory.unit_of_work() as uow:
            account = uow.consume_token(self._token_hash(token), "invitation", _timestamp(current))
            if account is None or account.password_hash or account.totp_enabled:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            self._set_factors(uow, account.id, password, secret, current)
            codes = self._replace_recovery_codes(uow, account.id, current)
            updated = uow.account(account.id)
            assert updated is not None
            return updated.view(), codes

    def prepare_recovery(self, token: str, *, now: datetime | None = None) -> AuthPreparation:
        email, expiry = self._valid_token(token, "recovery", _now(now))
        return AuthPreparation(email, expiry, pyotp.random_base32(length=32))

    def complete_recovery(
        self,
        token: str,
        password: str,
        totp_secret: str,
        totp_code: str,
        *,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        current = _now(now)
        _validate_password(password)
        secret = _normalize_secret(totp_secret)
        if _verify_totp(secret, totp_code, current) is None:
            raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
        with self.unit_of_work_factory.unit_of_work() as uow:
            account = uow.consume_token(self._token_hash(token), "recovery", _timestamp(current))
            if account is None:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            self._set_factors(uow, account.id, password, secret, current)
            uow.revoke_sessions(account.id, "recovery")
            uow.clear_recovery_codes(account.id)
            codes = self._replace_recovery_codes(uow, account.id, current)
            updated = uow.account(account.id)
            assert updated is not None
            return updated.view(), codes

    def login(
        self,
        email: str,
        password: str,
        second_factor: str,
        *,
        remote_key: str = "local",
        now: datetime | None = None,
    ) -> LocalAuthResult:
        current = _now(now)
        normalized_email = _normalize_email(email)
        key = f"{remote_key}:{normalized_email}"
        retry_after = LoginRateLimiter.retry_after(key, current)
        if retry_after is not None:
            raise LocalAuthError(
                "rate_limited",
                "Zu viele Versuche. Bitte später erneut versuchen.",
                retry_after=retry_after,
            )
        success = False
        try:
            with self.unit_of_work_factory.unit_of_work() as uow:
                account = uow.account_by_email(normalized_email)
                account = self._require_login_password(account, password)
                assert account.password_hash is not None
                if PASSWORD_HASHER.check_needs_rehash(account.password_hash):
                    uow.update_password_hash(account.id, PASSWORD_HASHER.hash(password))
                self._consume_login_factor(uow, account, second_factor, current)
                uow.set_last_login(account.id, _timestamp(current))
                uow.revoke_sessions(account.id, "new-login")
                credentials = uow.create_session(account.id, current, self.session_ttl)
                success = True
                return LocalAuthResult(credentials, account.id)
        finally:
            LoginRateLimiter.succeeded(key) if success else LoginRateLimiter.failed(key, current)

    def _require_login_password(
        self, account: LocalAuthAccount | None, password: str
    ) -> LocalAuthAccount:
        if account is None or not account.password_hash:
            self._dummy_password_check(password)
            raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
        if not account.is_active or not account.totp_enabled or not account.totp_secret_encrypted:
            raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
        try:
            valid = PASSWORD_HASHER.verify(account.password_hash, password)
        except InvalidHashError, VerificationError, VerifyMismatchError:
            valid = False
        if not valid:
            raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
        return account

    def _consume_login_factor(
        self, uow: LocalAuthUnitOfWork, account: LocalAuthAccount, factor: str, current: datetime
    ) -> None:
        accepted = self._login_totp_step(account, factor, current)
        if accepted is not None:
            if not uow.consume_totp_step(account.id, accepted):
                raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
        elif not self._consume_recovery_code(uow, account.id, factor, current):
            raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)

    def _login_totp_step(
        self, account: LocalAuthAccount, factor: str, current: datetime
    ) -> int | None:
        try:
            assert account.totp_secret_encrypted is not None
            return _verify_totp(
                self._decrypt_secret(account.totp_secret_encrypted), factor, current
            )
        except InvalidToken, LocalAuthError:
            return None

    def _valid_token(self, token: str, kind: str, current: datetime) -> tuple[str, str]:
        if not isinstance(token, str) or not token or len(token) > 256:
            raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
        with self.unit_of_work_factory.unit_of_work() as uow:
            value = uow.valid_token(self._token_hash(token), kind, _timestamp(current))
            if value is None:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            record, account = value
            return account.email, record.expires_at

    def _set_factors(
        self,
        uow: LocalAuthUnitOfWork,
        account_id: int,
        password: str,
        secret: str,
        current: datetime,
    ) -> None:
        uow.set_factors(
            account_id,
            PASSWORD_HASHER.hash(password),
            self._encrypt_secret(secret),
            _timestamp(current),
        )

    def _replace_recovery_codes(
        self, uow: LocalAuthUnitOfWork, account_id: int, current: datetime
    ) -> list[str]:
        values = tuple(_recovery_code() for _ in range(RECOVERY_CODE_COUNT))
        uow.add_recovery_codes(
            account_id, tuple(PASSWORD_HASHER.hash(code) for code in values), _timestamp(current)
        )
        return list(values)

    def _consume_recovery_code(
        self, uow: LocalAuthUnitOfWork, account_id: int, code: str, current: datetime
    ) -> bool:
        normalized = code.strip().upper() if isinstance(code, str) else ""
        if len(normalized) != RECOVERY_CODE_LENGTH:
            return False
        for candidate in uow.recovery_codes(account_id):
            try:
                matches = PASSWORD_HASHER.verify(candidate.code_hash, normalized)
            except InvalidHashError, VerificationError, VerifyMismatchError:
                matches = False
            if matches:
                return uow.consume_recovery_code(candidate.id, _timestamp(current))
        return False

    @staticmethod
    def _dummy_password_check(password: str) -> None:
        try:
            PASSWORD_HASHER.verify(
                _DUMMY_PASSWORD_HASH, password if isinstance(password, str) else ""
            )
        except InvalidHashError, VerificationError, VerifyMismatchError:
            pass

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _encrypt_secret(self, secret: str) -> str:
        return Fernet(self.key_provider.get_key()).encrypt(secret.encode("ascii")).decode("ascii")

    def _decrypt_secret(self, encrypted: str) -> str:
        return (
            Fernet(self.key_provider.get_key()).decrypt(encrypted.encode("ascii")).decode("ascii")
        )
