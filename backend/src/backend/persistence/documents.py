"""SQLite adapters for the consumer-owned document contracts."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from backend.documents.contracts import (
    DocumentMetadata,
    DocumentUnitOfWork,
    DocumentUnitOfWorkFactory,
)
from backend.persistence.database import (
    DEFAULT_DB_PATH,
    mutation_scope,
    session_scope,
)
from backend.persistence.models import DOCUMENT
from backend.persistence.store import Store


def _metadata(row: dict[str, object] | None) -> DocumentMetadata | None:
    return DocumentMetadata(**row) if row is not None else None


class _SQLiteDocumentRepository:
    def __init__(self, session: Session):
        self.store = Store(session)

    def get(self, document_id: int) -> DocumentMetadata | None:
        return _metadata(self.store.get(DOCUMENT, document_id))

    def create(
        self,
        *,
        storage_id: str,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> DocumentMetadata:
        row = self.store.create(
            DOCUMENT,
            {
                "storage_id": storage_id,
                "original_filename": original_filename,
                "media_type": media_type,
                "size_bytes": size_bytes,
                "checksum_sha256": checksum_sha256,
            },
        )
        result = _metadata(row)
        assert result is not None
        return result

    def delete(self, document_id: int) -> bool:
        return self.store.delete(DOCUMENT, document_id)


@dataclass(frozen=True)
class _SQLiteDocumentExportProjection:
    id: int
    storage_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    checksum_sha256: str


class _SQLiteDocumentUnitOfWork:
    def __init__(self, session: Session):
        self.documents = _SQLiteDocumentRepository(session)


class SQLiteDocumentUnitOfWorkFactory(DocumentUnitOfWorkFactory):
    """Open one explicit SQLite snapshot or locked metadata write UoW."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    @contextmanager
    def read(self) -> Iterator[DocumentUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield _SQLiteDocumentUnitOfWork(session)

    @contextmanager
    def write(self) -> Iterator[DocumentUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield _SQLiteDocumentUnitOfWork(session)

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Hold the snapshot lock through commit and any caller compensation."""
        with mutation_scope(self.db_path):
            yield


class SQLiteDocumentSnapshotQueries:
    """Restricted document snapshot capability used by Operations."""

    def __init__(self, database: Path, content: Path):
        self.database = Path(database)
        self.content = Path(content)

    def copy_content_to(self, destination: Path) -> int:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        count = 0
        for entry in self.content.iterdir():
            if entry.is_symlink() or not entry.is_file() or entry.name.startswith("."):
                raise ValueError("Document snapshot content is invalid")
            (destination / entry.name).hardlink_to(entry)
            count += 1
        return count

    def content_count(self) -> int:
        return sum(1 for entry in self.content.iterdir() if entry.is_file())

    def content_size_bytes(self) -> int:
        total = 0
        for entry in self.content.iterdir():
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("Document snapshot content is invalid")
            total += entry.stat().st_size
        return total

    def inspect_package(self, database: Path, content: Path) -> int | None:
        """Validate the metadata/content relation and return only its count."""
        database_path = Path(database)
        content_path = Path(content)
        try:
            with closing(sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)) as connection:
                rows = connection.execute(
                    "SELECT storage_id, size_bytes, checksum_sha256 FROM document"
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            raise ValueError("Document snapshot metadata is invalid") from error
        expected: dict[str, tuple[int, str]] = {}
        for storage_id, size_bytes, checksum in rows:
            if (
                not isinstance(storage_id, str)
                or not isinstance(size_bytes, int)
                or not isinstance(checksum, str)
            ):
                raise ValueError("Document snapshot metadata is invalid")
            expected[storage_id] = size_bytes, checksum
        if len(expected) != len(rows):
            raise ValueError("Document snapshot metadata is invalid")
        try:
            entries = list(content_path.iterdir())
        except OSError as error:
            raise OSError("Document snapshot content is unavailable") from error
        if any(
            entry.name.startswith(".") or entry.is_symlink() or not entry.is_file()
            for entry in entries
        ):
            raise ValueError("Document snapshot content is invalid")
        if {entry.name for entry in entries} != set(expected):
            raise ValueError("Document snapshot content is incomplete")
        for entry in entries:
            size_bytes, checksum = expected[entry.name]
            if entry.stat().st_size != size_bytes or _sha256(entry) != checksum:
                return None
        return len(expected)

    def export_metadata(self, database: Path) -> tuple[_SQLiteDocumentExportProjection, ...]:
        try:
            with closing(sqlite3.connect(f"file:{Path(database)}?mode=ro", uri=True)) as connection:
                rows = connection.execute(
                    "SELECT id, storage_id, original_filename, media_type, size_bytes, "
                    "checksum_sha256 FROM document ORDER BY id"
                ).fetchall()
        except sqlite3.Error as error:
            raise ValueError("Document export metadata is invalid") from error
        return tuple(_SQLiteDocumentExportProjection(*row) for row in rows)


class SQLiteDocumentSnapshotFactory:
    """Create metadata-free snapshot capabilities from configured paths."""

    def __init__(self, db_path: Path, documents_path: Path):
        self.db_path = Path(db_path)
        self.documents_path = Path(documents_path)

    @contextmanager
    def snapshot(self) -> Iterator[SQLiteDocumentSnapshotQueries]:
        yield SQLiteDocumentSnapshotQueries(self.db_path, self.documents_path)

    def inspect(self, database: Path, content: Path) -> int | None:
        return SQLiteDocumentSnapshotQueries(database, content).inspect_package(database, content)

    def export_metadata(self, database: Path) -> tuple[_SQLiteDocumentExportProjection, ...]:
        return SQLiteDocumentSnapshotQueries(self.db_path, self.documents_path).export_metadata(
            database
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
