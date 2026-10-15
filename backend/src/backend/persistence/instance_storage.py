"""SQLite and filesystem adapter for Operations instance-storage contracts."""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.persistence.artifact_limits import configure_artifact_database
from backend.persistence.database import (
    MIGRATIONS_PATH,
    activation_scope,
    apply_migrations,
    database_readiness,
    migration_status,
    mutation_scope,
    snapshot_scope,
)
from backend.persistence.local_auth import SQLiteLocalAuthenticationKey


class InstanceStorageError(RuntimeError):
    """Safe technical failure returned by the instance-storage adapter."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Schema:
    current: str
    pending: tuple[str, ...]
    target: str


class SQLiteFileInstanceStorage:
    """Implement instance persistence and maintenance with SQLite and local files."""

    def __init__(self, *, busy_timeout_ms: int = 5000) -> None:
        self.busy_timeout_ms = busy_timeout_ms

    def _connection(self, path: Path, *, read_only: bool = True) -> sqlite3.Connection:
        if read_only:
            uri = f"file:{path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=self.busy_timeout_ms / 1000)
        else:
            connection = sqlite3.connect(path, timeout=self.busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            configure_artifact_database(connection, path)
        except Exception:
            connection.close()
            raise
        return connection

    @staticmethod
    def _latest_schema() -> str:
        available = tuple(
            migration.name
            for migration in sorted(MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql"))
            if not migration.name.startswith("000_")
        )
        if not available:
            raise InstanceStorageError("schema_incompatible", "No schema is available")
        return available[-1]

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> list[str]:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    def _schema(self, database: Path, minimum_supported: str) -> _Schema:
        available = tuple(
            migration.name
            for migration in sorted(MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql"))
            if not migration.name.startswith("000_")
        )
        try:
            with closing(self._connection(database)) as connection:
                applied = tuple(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM schema_migration ORDER BY rowid"
                    ).fetchall()
                )
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "schema_incompatible", "Schema history is unavailable"
            ) from error
        if not applied or applied != available[: len(applied)]:
            code = "source_newer" if set(applied) - set(available) else "schema_incompatible"
            raise InstanceStorageError(code, "Artifact schema is not supported")
        if minimum_supported not in available or available.index(applied[-1]) < available.index(
            minimum_supported
        ):
            raise InstanceStorageError(
                "source_unsupported", "Artifact source schema is no longer supported"
            )
        status = migration_status(database)
        if status["state"] not in {"ready", "migration_required"}:
            raise InstanceStorageError("schema_incompatible", "Artifact schema metadata is invalid")
        current, pending = status.get("current"), status.get("pending")
        if current != applied[-1] or not isinstance(pending, list):
            raise InstanceStorageError("schema_incompatible", "Artifact schema metadata is invalid")
        return _Schema(str(current), tuple(str(item) for item in pending), available[-1])

    def integrity(self, database: Path) -> None:
        try:
            with closing(self._connection(database)) as connection:
                if [row[0] for row in connection.execute("PRAGMA integrity_check")] != ["ok"]:
                    raise InstanceStorageError(
                        "database_integrity_failed", "Database integrity check failed"
                    )
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise InstanceStorageError(
                        "database_integrity_failed", "Database relations are invalid"
                    )
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "database_integrity_failed", "Database integrity check failed"
            ) from error

    def instance_id(self, database: Path) -> str:
        try:
            with closing(self._connection(database)) as connection:
                row = connection.execute(
                    "SELECT instance_id FROM instance_metadata WHERE id = 1"
                ).fetchone()
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "schema_incompatible", "Instance identity is unavailable"
            ) from error
        if row is None or not isinstance(row[0], str):
            raise InstanceStorageError("schema_incompatible", "Instance identity is unavailable")
        return str(row[0])

    def snapshot_instance_id(self, database: Path, fallback: str) -> str:
        try:
            with closing(self._connection(database)) as connection:
                migrated = connection.execute(
                    "SELECT 1 FROM schema_migration WHERE name = ?",
                    ("024_add_artifact_operations.sql",),
                ).fetchone()
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "schema_incompatible", "Instance identity is unavailable"
            ) from error
        return self.instance_id(database) if migrated else fallback

    def totp_key_binding(self, database: Path, key: bytes) -> str:
        digest = hashlib.sha256()
        try:
            with database.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        except OSError as error:
            raise InstanceStorageError(
                "database_integrity_failed", "Database content could not be read"
            ) from error
        return "hmac-sha256:" + hmac.new(key, digest.digest(), hashlib.sha256).hexdigest()

    def record_count(self, database: Path) -> int:
        with closing(self._connection(database)) as connection:
            return sum(
                int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
                for table in self._table_names(connection)
            )

    def database_size(self, database: Path) -> int:
        with closing(self._connection(database)) as connection:
            return int(connection.execute("PRAGMA page_count").fetchone()[0]) * int(
                connection.execute("PRAGMA page_size").fetchone()[0]
            )

    @staticmethod
    def database_file_size(database: Path) -> int:
        return database.stat().st_size if database.exists() else 0

    @staticmethod
    def ensure_paths(data: Path, documents: Path, backups: Path) -> None:
        for directory in (data, documents, backups):
            if directory.exists() and directory.is_symlink():
                raise InstanceStorageError("persistence_error", "Persistent directory is invalid")
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise InstanceStorageError("persistence_error", "Persistent path is invalid")

    @staticmethod
    def authentication_key(database: Path, settings: object | None) -> bytes:
        return SQLiteLocalAuthenticationKey(database, settings=settings).get_key()

    @staticmethod
    def existing_authentication_key(database: Path) -> bytes | None:
        path = SQLiteLocalAuthenticationKey(database).path
        return path.read_bytes() if path.exists() else None

    @staticmethod
    def authentication_key_path(database: Path) -> Path:
        return SQLiteLocalAuthenticationKey(database).path

    @staticmethod
    def read_key(path: Path) -> bytes:
        return path.read_bytes()

    @staticmethod
    def free_space(directory: Path) -> int:
        return shutil.disk_usage(directory).free

    @staticmethod
    def writable_directory(directory: Path) -> bool:
        if directory.is_symlink() or not directory.is_dir():
            return False
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".lzug-doctor-") as probe:
                probe.write(b"lzug")
                probe.flush()
                os.fsync(probe.fileno())
        except OSError:
            return False
        return True

    @staticmethod
    def writable_database(database: Path) -> bool:
        if not database.is_file() or database.is_symlink():
            return False
        try:
            descriptor = os.open(database, os.O_WRONLY | os.O_APPEND)
        except OSError:
            return False
        os.close(descriptor)
        return True

    @staticmethod
    def resolve_artifact(directory: Path, name: str) -> Path | None:
        candidate = directory / name
        if candidate.is_symlink() or not candidate.is_file():
            return None
        return candidate

    @staticmethod
    def create_workspace(directory: Path, prefix: str) -> Path:
        path = Path(tempfile.mkdtemp(prefix=prefix, dir=directory))
        os.chmod(path, 0o700)
        return path

    def export_tables(
        self, database: Path, excluded_tables: frozenset[str]
    ) -> dict[str, dict[str, Any]]:
        with closing(self._connection(database)) as connection:
            included = [
                table for table in self._table_names(connection) if table not in excluded_tables
            ]
            result: dict[str, dict[str, Any]] = {}
            for table in included:
                columns = [
                    str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
                ]
                foreign_keys = {
                    str(row[3]): (str(row[2]), str(row[4]))
                    for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
                    if str(row[2]) in included
                }
                order = "id" if "id" in columns else "rowid"
                rows = [
                    dict(row)
                    for row in connection.execute(
                        f'SELECT * FROM "{table}" ORDER BY "{order}"'
                    ).fetchall()
                ]
                result[table] = {
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "rows": rows,
                }
            return result

    def prepare_restore(self, database: Path, instance_id: str) -> dict[str, int]:
        try:
            with closing(self._connection(database, read_only=False)) as connection:
                connection.execute(
                    "UPDATE instance_metadata SET instance_id = ? WHERE id = 1",
                    (instance_id,),
                )
                reset = {
                    "sessions": connection.execute("DELETE FROM auth_session").rowcount,
                    "invitations": connection.execute(
                        "DELETE FROM auth_token WHERE kind = 'invitation' "
                        "AND consumed_at IS NULL"
                    ).rowcount,
                    "recovery_operations": connection.execute(
                        "DELETE FROM auth_token WHERE kind = 'recovery' " "AND consumed_at IS NULL"
                    ).rowcount,
                    "recovery_codes": connection.execute("DELETE FROM auth_recovery_code").rowcount,
                    "technical_claims": connection.execute(
                        "UPDATE notification_delivery SET claim_token = NULL, claimed_at = NULL, "
                        "claim_expires_at = NULL WHERE claim_token IS NOT NULL"
                    ).rowcount,
                }
                now = datetime.now(UTC).isoformat(timespec="seconds")
                for task_table, reopening_table in (
                    ("exam_day_task", "exam_day_reopening"),
                    ("exam_round_task", "exam_round_reopening"),
                ):
                    connection.execute(
                        f"UPDATE \"{task_table}\" SET status = 'completed', completed_at = ? "
                        f"WHERE status = 'open' AND reopening_id IN "
                        f"(SELECT id FROM \"{reopening_table}\" WHERE status != 'open')",
                        (now,),
                    )
                connection.commit()
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                return {key: int(value) for key, value in reset.items()}
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "restore_prepare_failed", "Prepared restore could not be initialized"
            ) from error

    def validate_authentication_key(self, database: Path, key: bytes) -> int:
        try:
            cipher = Fernet(key)
            with closing(self._connection(database)) as connection:
                rows = connection.execute(
                    "SELECT totp_secret_encrypted FROM user_account "
                    "WHERE totp_secret_encrypted IS NOT NULL"
                ).fetchall()
            for row in rows:
                secret = cipher.decrypt(str(row[0]).encode("ascii"))
                if not secret or not secret.isascii():
                    raise InvalidToken
            return len(rows)
        except (InvalidToken, ValueError, OSError, sqlite3.Error) as error:
            raise InstanceStorageError(
                "authentication_key_invalid", "Authentication key validation failed"
            ) from error

    def copy_database(self, source: Path, destination: Path) -> None:
        try:
            with closing(self._connection(source)) as source_connection:
                with closing(self._connection(destination, read_only=False)) as target:
                    source_connection.backup(target)
                    target.commit()
        except (OSError, sqlite3.Error) as error:
            raise InstanceStorageError("snapshot_failed", "Instance snapshot failed") from error

    def snapshot_lease(self, database: Path):
        return snapshot_scope(database)

    def activation_lease(self, database: Path):
        return activation_scope(database)

    def checkpoint(self, database: Path) -> None:
        if not database.exists():
            return
        with closing(self._connection(database, read_only=False)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def seal_prepared_database(self, database: Path) -> None:
        self.checkpoint(database)
        Path(f"{database}-wal").unlink(missing_ok=True)
        Path(f"{database}-shm").unlink(missing_ok=True)

    def activate_restore(
        self,
        database: Path,
        documents: Path,
        key: Path,
        active_database: Path,
        active_documents: Path,
        target_key: Path,
        retirement_directory: Path,
        validate: Callable[[], None],
    ) -> None:
        retired = self.create_workspace(retirement_directory, ".lzug-retired-")
        moved: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        try:
            self.checkpoint(active_database)
            for target in (
                active_database,
                Path(f"{active_database}-wal"),
                Path(f"{active_database}-shm"),
                active_documents,
                target_key,
            ):
                if target.exists():
                    destination = retired / target.name
                    os.replace(target, destination)
                    moved.append((destination, target))
            for source, target in (
                (database, active_database),
                (documents, active_documents),
                (key, target_key),
            ):
                os.replace(source, target)
                installed.append(target)
            validate()
        except Exception as error:
            for target in reversed(installed):
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            for source, target in reversed(moved):
                if source.exists():
                    os.replace(source, target)
            if isinstance(error, InstanceStorageError):
                raise
            raise InstanceStorageError("activation_failed", "Restore activation failed") from error
        finally:
            self._cleanup_retired_workspace(retired)

    @staticmethod
    def _cleanup_retired_workspace(retired: Path) -> None:
        """Preserve the socket cleanup fence when retired restore data remains."""
        try:
            shutil.rmtree(retired)
        except OSError as error:
            raise InstanceStorageError(
                "artifact_cleanup_failed", "Restore cleanup failed"
            ) from error

    def is_empty(self, database: Path, documents: Path) -> bool:
        if any(documents.iterdir()):
            return False
        if not database.exists() or database.stat().st_size == 0:
            return True
        try:
            with closing(self._connection(database)) as connection:
                excluded = {
                    "artifact_operation",
                    "exam_venue_migration_report",
                    "instance_metadata",
                    "schema_migration",
                    "schema_migration_checksum",
                }
                for table in self._table_names(connection):
                    if (
                        table not in excluded
                        and connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                    ):
                        return False
            return True
        except sqlite3.Error as error:
            raise InstanceStorageError(
                "target_invalid", "Existing target cannot be inspected safely"
            ) from error

    def record_artifact_operation(
        self,
        database: Path,
        *,
        operation_type: str,
        artifact_id: str | None,
        artifact_type: str | None,
        snapshot_at: str | None,
        recipient_fingerprint: str | None,
        succeeded: bool,
        error_code: str | None,
    ) -> None:
        if not database.exists():
            return
        try:
            with mutation_scope(database):
                with closing(self._connection(database, read_only=False)) as connection:
                    if "artifact_operation" not in self._table_names(connection):
                        return
                    connection.execute(
                        "INSERT INTO artifact_operation "
                        "(operation_type, artifact_id, artifact_type, snapshot_at, "
                        "recipient_key_fingerprint, result, error_code) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation_type,
                            artifact_id,
                            artifact_type,
                            snapshot_at,
                            recipient_fingerprint,
                            "succeeded" if succeeded else "failed",
                            error_code,
                        ),
                    )
                    connection.commit()
        except sqlite3.Error:
            return


class SQLiteInstanceMaintenance:
    """Migration contract used by Operations while the runtime owns admission."""

    def __init__(self, storage: SQLiteFileInstanceStorage | None = None) -> None:
        self.storage = storage or SQLiteFileInstanceStorage()

    def schema(self, database: Path, minimum_supported: str) -> _Schema:
        return self.storage._schema(database, minimum_supported)

    def latest_schema(self) -> str:
        return self.storage._latest_schema()

    @staticmethod
    def schema_status(database: Path) -> dict[str, Any]:
        return migration_status(database)

    @staticmethod
    def apply(database: Path, backup_directory: Path | None) -> None:
        apply_migrations(database, backup_directory)

    @staticmethod
    def readiness(database: Path) -> dict[str, Any]:
        return database_readiness(database)
