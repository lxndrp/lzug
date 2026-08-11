"""Local password, TOTP, and recovery-factor authentication for #266.

The public HTTP adapter calls this service with request bodies only.  Passwords
and recovery codes use Argon2id; TOTP secrets are encrypted with an instance
key kept outside SQLite because verification requires the secret itself.  No
value in this module is logged or included in an exception message.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
import secrets
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select, update

from .auth import SESSION_TTL, AuthenticationRepository, SessionCredentials
from .database import DEFAULT_DB_PATH, session_scope
from .models import AuthRecoveryCode, AuthToken, UserAccount

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
            if len(attempts) < cls.max_failures:
                return None
            return max(1, int((attempts[0] + cls.window - now).total_seconds()))

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
        threshold = now - cls.window
        while attempts and attempts[0] <= threshold:
            attempts.popleft()


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


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
    normalized_code = _validate_totp_code(code)
    timestamp = int(current.timestamp())
    current_step = timestamp // TOTP_PERIOD
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD)
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        step = current_step + offset
        if step >= 0 and hmac.compare_digest(
            totp.at(timestamp + offset * TOTP_PERIOD), normalized_code
        ):
            return step
    return None


def _recovery_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(RECOVERY_CODE_LENGTH))


class LocalAuthService:
    """Transactional local authentication and first-factor activation."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.authentication = AuthenticationRepository(self.db_path)

    def prepare_invitation(self, token: str, *, now: datetime | None = None) -> AuthPreparation:
        current = _now(now)
        email, expires_at = self._valid_token(token, "invitation", current)
        secret = pyotp.random_base32(length=32)
        return AuthPreparation(email, expires_at, secret)

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
        accepted_step = _verify_totp(secret, totp_code, current)
        if accepted_step is None:
            raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
        with session_scope(self.db_path) as session:
            account = self._consume_token(session, token, "invitation", current)
            if account.password_hash or account.totp_enabled:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            self._set_factors(session, account, password, secret, current)
            codes = self._replace_recovery_codes(session, account.id, current)
            session.flush()
            return AuthenticationRepository._account_view(account), codes

    def prepare_recovery(self, token: str, *, now: datetime | None = None) -> AuthPreparation:
        email, expires_at = self._valid_token(token, "recovery", _now(now))
        return AuthPreparation(email, expires_at, pyotp.random_base32(length=32))

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
        accepted_step = _verify_totp(secret, totp_code, current)
        if accepted_step is None:
            raise LocalAuthError("invalid_factor", GENERIC_FACTOR_MESSAGE)
        with session_scope(self.db_path) as session:
            account = self._consume_token(session, token, "recovery", current)
            self._set_factors(session, account, password, secret, current)
            self.authentication._revoke_account_sessions(session, account.id, "recovery")
            session.query(AuthRecoveryCode).filter(
                AuthRecoveryCode.account_id == account.id
            ).delete(synchronize_session=False)
            codes = self._replace_recovery_codes(session, account.id, current)
            session.flush()
            return AuthenticationRepository._account_view(account), codes

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
            with session_scope(self.db_path) as session:
                account = session.scalars(
                    select(UserAccount).where(UserAccount.email == normalized_email)
                ).first()
                if account is None or not account.password_hash:
                    self._dummy_password_check(password)
                    raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
                if (
                    not account.is_active
                    or not account.totp_enabled
                    or not account.totp_secret_encrypted
                ):
                    raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
                try:
                    password_ok = PASSWORD_HASHER.verify(account.password_hash, password)
                except InvalidHashError, VerificationError, VerifyMismatchError:
                    password_ok = False
                if not password_ok:
                    raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
                if PASSWORD_HASHER.check_needs_rehash(account.password_hash):
                    account.password_hash = PASSWORD_HASHER.hash(password)

                recovery_consumed = False
                accepted_step = None
                try:
                    secret = self._decrypt_secret(account.totp_secret_encrypted)
                    accepted_step = _verify_totp(secret, second_factor, current)
                except InvalidToken, LocalAuthError:
                    accepted_step = None
                if accepted_step is not None:
                    changed = session.execute(
                        update(UserAccount)
                        .where(
                            UserAccount.id == account.id,
                            or_(
                                UserAccount.totp_last_step.is_(None),
                                UserAccount.totp_last_step < accepted_step,
                            ),
                        )
                        .values(totp_last_step=accepted_step)
                    ).rowcount
                    if changed != 1:
                        raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)
                else:
                    recovery_consumed = self._consume_recovery_code(
                        session, account.id, second_factor, current
                    )
                    if not recovery_consumed:
                        raise LocalAuthError("login_failed", GENERIC_LOGIN_MESSAGE)

                account.last_login_at = _timestamp(current)
                self.authentication._revoke_account_sessions(session, account.id, "new-login")
                credentials = self.authentication._create_session(
                    session, account, current, SESSION_TTL
                )
                success = True
                return LocalAuthResult(credentials, account.id)
        finally:
            if success:
                LoginRateLimiter.succeeded(key)
            else:
                LoginRateLimiter.failed(key, current)

    def _valid_token(self, token: str, kind: str, current: datetime) -> tuple[str, str]:
        if not isinstance(token, str) or not token or len(token) > 256:
            raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
        with session_scope(self.db_path) as session:
            record = session.scalars(
                select(AuthToken).where(
                    AuthToken.kind == kind,
                    AuthToken.token_hash == self._token_hash(token),
                    AuthToken.consumed_at.is_(None),
                )
            ).first()
            if record is None or _parse_timestamp(record.expires_at) <= current:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            account = session.get(UserAccount, record.account_id)
            if account is None or not account.is_active:
                raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
            return account.email, record.expires_at

    def _consume_token(self, session, token: str, kind: str, current: datetime) -> UserAccount:
        if not isinstance(token, str) or not token or len(token) > 256:
            raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
        consumed_at = _timestamp(current)
        changed = session.execute(
            update(AuthToken)
            .where(
                AuthToken.kind == kind,
                AuthToken.token_hash == self._token_hash(token),
                AuthToken.consumed_at.is_(None),
                AuthToken.expires_at > consumed_at,
            )
            .values(consumed_at=consumed_at)
        ).rowcount
        if changed != 1:
            raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
        record = session.scalars(
            select(AuthToken).where(
                AuthToken.kind == kind,
                AuthToken.token_hash == self._token_hash(token),
            )
        ).first()
        account = session.get(UserAccount, record.account_id) if record else None
        if account is None or not account.is_active:
            raise LocalAuthError("token_invalid", GENERIC_TOKEN_MESSAGE)
        return account

    def _set_factors(
        self,
        session,
        account: UserAccount,
        password: str,
        secret: str,
        current: datetime,
    ) -> None:
        account.password_hash = PASSWORD_HASHER.hash(password)
        account.totp_secret_encrypted = self._encrypt_secret(secret)
        # Setup validates a code but does not consume the first login window.
        # Replay protection starts with the first successful authentication.
        account.totp_last_step = None
        account.totp_enabled = 1
        account.two_factor_enabled = 0
        account.updated_at = _timestamp(current)

    def _replace_recovery_codes(self, session, account_id: int, current: datetime) -> list[str]:
        codes: list[str] = []
        for _ in range(RECOVERY_CODE_COUNT):
            code = _recovery_code()
            codes.append(code)
            session.add(
                AuthRecoveryCode(
                    account_id=account_id,
                    code_hash=PASSWORD_HASHER.hash(code),
                    created_at=_timestamp(current),
                )
            )
        return codes

    def _consume_recovery_code(
        self, session, account_id: int, code: str, current: datetime
    ) -> bool:
        normalized = code.strip().upper() if isinstance(code, str) else ""
        if len(normalized) != RECOVERY_CODE_LENGTH:
            return False
        candidates = session.scalars(
            select(AuthRecoveryCode).where(
                AuthRecoveryCode.account_id == account_id,
                AuthRecoveryCode.consumed_at.is_(None),
            )
        ).all()
        for candidate in candidates:
            try:
                matches = PASSWORD_HASHER.verify(candidate.code_hash, normalized)
            except InvalidHashError, VerificationError, VerifyMismatchError:
                matches = False
            if not matches:
                continue
            changed = session.execute(
                update(AuthRecoveryCode)
                .where(
                    AuthRecoveryCode.id == candidate.id,
                    AuthRecoveryCode.consumed_at.is_(None),
                )
                .values(consumed_at=_timestamp(current))
            ).rowcount
            return changed == 1
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
        import hashlib

        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _key(self) -> bytes:
        configured = os.environ.get("LZUG_AUTH_ENCRYPTION_KEY")
        if configured:
            try:
                Fernet(configured.encode("ascii"))
            except (ValueError, binascii.Error) as error:
                raise LocalAuthError(
                    "persistence_error", "Lokale Authentifizierung ist nicht verfügbar."
                ) from error
            return configured.encode("ascii")
        key_path = self.db_path.with_name(".lzug-auth.key")
        try:
            key = key_path.read_bytes() if key_path.exists() else None
            if key is None:
                key = Fernet.generate_key()
                try:
                    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    key = key_path.read_bytes()
                else:
                    try:
                        os.write(descriptor, key)
                    finally:
                        os.close(descriptor)
            os.chmod(key_path, 0o600)
            Fernet(key)
            return key
        except (OSError, ValueError, binascii.Error) as error:
            raise LocalAuthError(
                "persistence_error", "Lokale Authentifizierung ist nicht verfügbar."
            ) from error

    def _encrypt_secret(self, secret: str) -> str:
        return Fernet(self._key()).encrypt(secret.encode("ascii")).decode("ascii")

    def _decrypt_secret(self, encrypted: str) -> str:
        return Fernet(self._key()).decrypt(encrypted.encode("ascii")).decode("ascii")
