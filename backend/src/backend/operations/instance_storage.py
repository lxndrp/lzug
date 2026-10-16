"""Operations-owned contracts for durable instance data and maintenance."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.settings import LocalAuthSettings


@dataclass(frozen=True)
class InstanceSchema:
    current: str
    pending: tuple[str, ...]
    target: str


class InstanceStorage(Protocol):
    """Technical capabilities required to snapshot, inspect, and activate data."""

    def integrity(self, database: Path) -> None: ...

    def instance_id(self, database: Path) -> str: ...

    def snapshot_instance_id(self, database: Path, fallback: str) -> str: ...

    def totp_key_binding(self, database: Path, key: bytes) -> str: ...

    def record_count(self, database: Path) -> int: ...

    def database_size(self, database: Path) -> int: ...

    def database_file_size(self, database: Path) -> int: ...

    def ensure_paths(self, data: Path, documents: Path, backups: Path) -> None: ...

    def authentication_key(self, database: Path, settings: LocalAuthSettings | None) -> bytes: ...

    def existing_authentication_key(self, database: Path) -> bytes | None: ...

    def authentication_key_path(self, database: Path) -> Path: ...

    def read_key(self, path: Path) -> bytes: ...

    def free_space(self, directory: Path) -> int: ...

    def writable_directory(self, directory: Path) -> bool: ...

    def writable_database(self, database: Path) -> bool: ...

    def resolve_artifact(self, directory: Path, name: str) -> Path | None: ...

    def create_workspace(self, directory: Path, prefix: str) -> Path: ...

    def export_tables(
        self, database: Path, excluded_tables: frozenset[str]
    ) -> dict[str, dict[str, Any]]: ...

    def prepare_restore(self, database: Path, instance_id: str) -> dict[str, int]: ...

    def validate_authentication_key(self, database: Path, key: bytes) -> int: ...

    def copy_database(self, source: Path, destination: Path) -> None: ...

    def snapshot_lease(self, database: Path) -> AbstractContextManager[None]: ...

    def activation_lease(self, database: Path) -> AbstractContextManager[None]: ...

    def checkpoint(self, database: Path) -> None: ...

    def seal_prepared_database(self, database: Path) -> None: ...

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
    ) -> None: ...

    def is_empty(self, database: Path, documents: Path) -> bool: ...

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
    ) -> None: ...


class InstanceMaintenance(Protocol):
    """Operations-owned schema and migration contract for the active process."""

    def schema(self, database: Path, minimum_supported: str) -> InstanceSchema: ...

    def latest_schema(self) -> str: ...

    def schema_status(self, database: Path) -> dict[str, Any]: ...

    def apply(self, database: Path, backup_directory: Path | None) -> None: ...

    def readiness(self, database: Path) -> dict[str, Any]: ...
