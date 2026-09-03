"""Persistent, secret-free configuration of the active age backup recipient."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from .backup_restore import BACKUP_PUBLIC_KEY_ENV, ArtifactError
from .database import DEFAULT_DB_PATH, session_scope
from .models import BackupRecipient, BackupRecipientAudit

_AGE_X25519 = re.compile(r"^age1[023456789acdefghjklmnpqrstuvwxyz]{58}$")


def recipient_fingerprint(recipient: str) -> str:
    """Return the canonical public-recipient fingerprint used by every layer."""
    canonical = validate_recipient(recipient)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_recipient(recipient: object) -> str:
    if (
        not isinstance(recipient, str)
        or _AGE_X25519.fullmatch(recipient) is None
        or not _valid_age_recipient_checksum(recipient)
    ):
        raise ArtifactError("recipient_key_invalid", "Age recipient is invalid")
    return recipient


class BackupRecipientRepository:
    """Manage the singleton public recipient and append-only audit evidence."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.environment = environment or {}

    def show(self) -> dict[str, str] | None:
        self.migrate_environment()
        with session_scope(self.db_path) as session:
            current = session.get(BackupRecipient, 1)
            return self._result(current) if current is not None else None

    def set(self, recipient: str, fingerprint: str) -> dict[str, str]:
        return self._change(recipient, fingerprint, replace=False)

    def replace(self, recipient: str, fingerprint: str) -> dict[str, str]:
        return self._change(recipient, fingerprint, replace=True)

    def migrate_environment(self) -> None:
        value = self.environment.get(BACKUP_PUBLIC_KEY_ENV)
        if not value:
            return
        recipient = _migrate_legacy_recipient(value)
        fingerprint = recipient_fingerprint(recipient)
        try:
            with session_scope(self.db_path) as session:
                if session.get(BackupRecipient, 1) is not None:
                    return
                current = BackupRecipient(
                    id=1,
                    recipient=recipient,
                    fingerprint=fingerprint,
                )
                session.add(current)
                session.add(
                    BackupRecipientAudit(
                        action="migrate",
                        previous_fingerprint=None,
                        fingerprint=fingerprint,
                    )
                )
        except IntegrityError:
            # A concurrent initializer won the singleton insertion.
            return

    def _change(self, recipient: str, fingerprint: str, *, replace: bool) -> dict[str, str]:
        self.migrate_environment()
        canonical = validate_recipient(recipient)
        expected = recipient_fingerprint(canonical)
        if fingerprint != expected:
            raise ArtifactError("recipient_key_mismatch", "Recipient fingerprint does not match")
        try:
            with session_scope(self.db_path) as session:
                current = session.get(BackupRecipient, 1)
                if current is None and replace:
                    raise ArtifactError(
                        "recipient_not_configured", "No backup recipient is configured"
                    )
                if current is not None and not replace:
                    raise ArtifactError(
                        "recipient_already_configured", "A backup recipient is configured"
                    )
                previous = current.fingerprint if current is not None else None
                now = datetime.now(UTC).isoformat(timespec="seconds")
                if current is None:
                    current = BackupRecipient(
                        id=1,
                        recipient=canonical,
                        fingerprint=expected,
                        activated_at=now,
                        updated_at=now,
                    )
                    session.add(current)
                else:
                    current.recipient = canonical
                    current.fingerprint = expected
                    current.activated_at = now
                    current.updated_at = now
                session.add(
                    BackupRecipientAudit(
                        action="replace" if replace else "set",
                        previous_fingerprint=previous,
                        fingerprint=expected,
                    )
                )
                session.flush()
                result = self._result(current)
                if previous is not None:
                    result["previous_fingerprint"] = previous
                return result
        except IntegrityError as error:
            raise ArtifactError(
                "recipient_already_configured", "A backup recipient is configured"
            ) from error

    @staticmethod
    def _result(recipient: BackupRecipient) -> dict[str, str]:
        return {
            "recipient": recipient.recipient,
            "protection": "age-x25519-v1",
            "fingerprint": recipient.fingerprint,
            "activated_at": recipient.activated_at,
        }


def _migrate_legacy_recipient(value: str) -> str:
    if value.startswith("age1"):
        return validate_recipient(value)
    if not value.startswith("x25519:"):
        raise ArtifactError("recipient_key_invalid", "Configured backup recipient is invalid")
    encoded = value.removeprefix("x25519:")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except ValueError as error:
        raise ArtifactError(
            "recipient_key_invalid", "Configured backup recipient is invalid"
        ) from error
    if len(raw) != 32:
        raise ArtifactError("recipient_key_invalid", "Configured backup recipient is invalid")
    return _bech32("age", raw)


def _bech32(hrp: str, payload: bytes) -> str:
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    values: list[int] = []
    accumulator = 0
    bits = 0
    for byte in payload:
        accumulator = (accumulator << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            values.append((accumulator >> bits) & 31)
    if bits:
        values.append((accumulator << (5 - bits)) & 31)
    expanded = [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]
    polymod = _bech32_polymod(expanded + values + [0] * 6) ^ 1
    checksum = [(polymod >> (5 * (5 - index))) & 31 for index in range(6)]
    return hrp + "1" + "".join(alphabet[value] for value in values + checksum)


def _bech32_polymod(values: list[int]) -> int:
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def _valid_age_recipient_checksum(value: str) -> bool:
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    separator = value.rfind("1")
    if separator <= 0:
        return False
    try:
        payload = [alphabet.index(char) for char in value[separator + 1 :]]
    except ValueError:
        return False
    expanded = [ord(char) >> 5 for char in value[:separator]]
    expanded += [0]
    expanded += [ord(char) & 31 for char in value[:separator]]
    return len(payload) == 58 and _bech32_polymod(expanded + payload) == 1
