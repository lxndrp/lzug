"""Safe document storage boundary and its local filesystem implementation."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import uuid4

STORAGE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_FILENAME_LENGTH = 255


class DocumentStorageError(RuntimeError):
    """Base error for document storage failures."""


class DocumentNotFoundError(DocumentStorageError):
    """The requested internal document does not exist."""


class DocumentStorageCollisionError(DocumentStorageError):
    """A storage ID is already occupied and will never be overwritten."""


class InvalidStorageIdError(DocumentStorageError):
    """The caller supplied a value that is not an internal storage ID."""


class InvalidDocumentFilenameError(ValueError):
    """A display filename contains path or control characters."""


@dataclass(frozen=True)
class StoredDocument:
    size_bytes: int
    checksum_sha256: str


class DocumentStorage(Protocol):
    """Minimal content boundary usable by a future remote adapter."""

    def put(
        self,
        storage_id: str,
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> StoredDocument: ...

    def read(self, storage_id: str) -> bytes: ...

    def delete(self, storage_id: str) -> bool: ...


def new_storage_id() -> str:
    """Create an opaque, non-user-controlled file name."""
    return uuid4().hex


def validate_storage_id(storage_id: str) -> str:
    if not isinstance(storage_id, str) or STORAGE_ID_PATTERN.fullmatch(storage_id) is None:
        raise InvalidStorageIdError("Storage ID must be a 32-character lowercase hexadecimal value")
    return storage_id


def validate_document_filename(filename: str) -> str:
    if not isinstance(filename, str) or not filename or len(filename) > MAX_FILENAME_LENGTH:
        raise InvalidDocumentFilenameError("Document filename must contain 1 to 255 characters")
    if filename in {".", ".."} or "/" in filename or "\\" in filename or "\x00" in filename:
        raise InvalidDocumentFilenameError("Document filename must not contain a path")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise InvalidDocumentFilenameError("Document filename must not contain control characters")
    if filename.endswith((".", " ")):
        raise InvalidDocumentFilenameError("Document filename must not end with a dot or space")
    return filename


class FilesystemDocumentStorage:
    """Store opaque document IDs as atomically published files in one directory."""

    def __init__(self, root: Path):
        root = Path(root).expanduser()
        if root.exists() and root.is_symlink():
            raise DocumentStorageError(f"Document storage root must not be a symlink: {root}")
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DocumentStorageError(
                f"Document storage root cannot be created: {root}"
            ) from error
        if not root.is_dir():
            raise DocumentStorageError(f"Document storage root is not a directory: {root}")
        self.root = root.resolve()

    def _path(self, storage_id: str) -> Path:
        validate_storage_id(storage_id)
        path = self.root / storage_id
        if path.parent != self.root:
            raise InvalidStorageIdError("Storage ID escapes the document storage root")
        if path.is_symlink():
            raise DocumentStorageError(f"Document storage entry is a symlink: {storage_id}")
        return path

    def put(
        self,
        storage_id: str,
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> StoredDocument:
        target = self._path(storage_id)
        temporary_path: Path | None = None
        size = 0
        digest = hashlib.sha256()
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=".lzug-document-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                os.chmod(temporary.fileno(), 0o600)
                for chunk in self._chunks(content):
                    if not chunk:
                        continue
                    temporary.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.link(temporary_path, target)
            except FileExistsError as error:
                raise DocumentStorageCollisionError(
                    f"Storage ID already exists: {storage_id}"
                ) from error
            return StoredDocument(size_bytes=size, checksum_sha256=digest.hexdigest())
        except OSError as error:
            raise DocumentStorageError(f"Document could not be stored: {storage_id}") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def read(self, storage_id: str) -> bytes:
        path = self._path(storage_id)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError as error:
            raise DocumentNotFoundError(f"Document does not exist: {storage_id}") from error
        except OSError as error:
            raise DocumentStorageError(f"Document could not be opened: {storage_id}") from error
        try:
            with os.fdopen(descriptor, "rb") as document:
                return document.read()
        except OSError as error:
            raise DocumentStorageError(f"Document could not be read: {storage_id}") from error

    def delete(self, storage_id: str) -> bool:
        path = self._path(storage_id)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            raise DocumentStorageError(f"Document could not be deleted: {storage_id}") from error

    def _chunks(self, content: bytes | bytearray | memoryview | BinaryIO):
        if isinstance(content, (bytes, bytearray, memoryview)):
            yield bytes(content)
            return
        while chunk := content.read(1024 * 1024):
            yield chunk


FileSystemDocumentStorage = FilesystemDocumentStorage
