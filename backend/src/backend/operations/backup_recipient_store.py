"""Operations-owned persistence contract for backup-recipient state."""

from __future__ import annotations

from typing import Protocol


class BackupRecipientStore(Protocol):
    def inspect(self) -> dict[str, str] | None: ...

    def migrate(self, recipient: str, fingerprint: str) -> None: ...

    def change(
        self,
        recipient: str,
        fingerprint: str,
        *,
        replace: bool,
    ) -> dict[str, str]: ...
