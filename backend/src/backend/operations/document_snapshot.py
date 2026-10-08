"""Operations-owned technical document snapshot contracts."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol


class DocumentExportProjection(Protocol):
    """Explicit portable export fields, materialized without ORM objects."""

    id: int
    storage_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    checksum_sha256: str


class DocumentSnapshotQueries(Protocol):
    """Restricted technical snapshot view; it exposes no ORM models or sessions."""

    def copy_content_to(self, destination: Path) -> int: ...

    def content_count(self) -> int: ...

    def content_size_bytes(self) -> int: ...

    def inspect_package(self, database: Path, content: Path) -> int | None:
        """Return None for size/digest mismatch; raise ValueError for bad relations."""

    def export_metadata(self, database: Path) -> tuple[DocumentExportProjection, ...]: ...


class DocumentSnapshotFactory(Protocol):
    """Operations-owned port implemented by the SQLite adapter."""

    def snapshot(self) -> AbstractContextManager[DocumentSnapshotQueries]: ...

    def inspect(self, database: Path, content: Path) -> int | None: ...

    def export_metadata(self, database: Path) -> tuple[DocumentExportProjection, ...]: ...
