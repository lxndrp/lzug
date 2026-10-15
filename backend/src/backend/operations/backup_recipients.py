"""Persistent, secret-free configuration of the active age backup recipient."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping

from backend.operations.backup_recipient_store import BackupRecipientStore
from backend.operations.backup_restore import BACKUP_PUBLIC_KEY_ENV, ArtifactError

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
    """Validate public recipient changes and delegate durable state to its port."""

    def __init__(
        self,
        store: BackupRecipientStore,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.store = store
        self.environment = environment or {}

    def show(self) -> dict[str, str] | None:
        self.migrate_environment()
        return self.store.inspect()

    def inspect(self) -> dict[str, str] | None:
        """Read a recipient on a pending schema without persisting environment migration."""
        current = self.store.inspect()
        if current is not None:
            return current
        value = self.environment.get(BACKUP_PUBLIC_KEY_ENV)
        if not value:
            return None
        recipient = _migrate_legacy_recipient(value)
        return {
            "recipient": recipient,
            "fingerprint": recipient_fingerprint(recipient),
            "protection": "age-x25519-v1",
        }

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
        self.store.migrate(recipient, fingerprint)

    def _change(self, recipient: str, fingerprint: str, *, replace: bool) -> dict[str, str]:
        self.migrate_environment()
        canonical = validate_recipient(recipient)
        expected = recipient_fingerprint(canonical)
        if fingerprint != expected:
            raise ArtifactError("recipient_key_mismatch", "Recipient fingerprint does not match")
        try:
            return self.store.change(canonical, expected, replace=replace)
        except RuntimeError as error:
            raise ArtifactError(getattr(error, "code", "persistence_error"), str(error)) from error


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
