"""SQLAlchemy adapter for the Operations backup-recipient store contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.persistence.database import DEFAULT_DB_PATH, connection_scope, session_scope
from backend.persistence.models import BackupRecipient, BackupRecipientAudit


class BackupRecipientStoreError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SQLiteBackupRecipientStore:
    def __init__(self, database: Path = DEFAULT_DB_PATH) -> None:
        self.database = Path(database)

    def inspect(self) -> dict[str, str] | None:
        with connection_scope(self.database) as connection:
            present = inspect(connection).has_table(BackupRecipient.__tablename__)
        if not present:
            return None
        with session_scope(self.database) as session:
            row = session.get(BackupRecipient, 1)
            return self._projection(row) if row is not None else None

    def migrate(self, recipient: str, fingerprint: str) -> None:
        try:
            with session_scope(self.database) as session:
                if session.get(BackupRecipient, 1) is not None:
                    return
                session.add(BackupRecipient(id=1, recipient=recipient, fingerprint=fingerprint))
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

    def change(
        self,
        recipient: str,
        fingerprint: str,
        *,
        replace: bool,
    ) -> dict[str, str]:
        try:
            with session_scope(self.database) as session:
                current = session.get(BackupRecipient, 1)
                if current is None and replace:
                    raise BackupRecipientStoreError(
                        "recipient_not_configured", "No backup recipient is configured"
                    )
                if current is not None and not replace:
                    raise BackupRecipientStoreError(
                        "recipient_already_configured", "A backup recipient is configured"
                    )
                previous = current.fingerprint if current is not None else None
                now = datetime.now(UTC).isoformat(timespec="seconds")
                if current is None:
                    current = BackupRecipient(
                        id=1,
                        recipient=recipient,
                        fingerprint=fingerprint,
                        activated_at=now,
                        updated_at=now,
                    )
                    session.add(current)
                else:
                    current.recipient = recipient
                    current.fingerprint = fingerprint
                    current.activated_at = now
                    current.updated_at = now
                session.add(
                    BackupRecipientAudit(
                        action="replace" if replace else "set",
                        previous_fingerprint=previous,
                        fingerprint=fingerprint,
                    )
                )
                session.flush()
                result = self._projection(current)
                if previous is not None:
                    result["previous_fingerprint"] = previous
                return result
        except IntegrityError as error:
            raise BackupRecipientStoreError(
                "recipient_already_configured", "A backup recipient is configured"
            ) from error

    @staticmethod
    def _projection(row: BackupRecipient) -> dict[str, str]:
        result = {
            "recipient": row.recipient,
            "protection": "age-x25519-v1",
            "fingerprint": row.fingerprint,
        }
        if row.activated_at is not None:
            result["activated_at"] = row.activated_at
        return result
