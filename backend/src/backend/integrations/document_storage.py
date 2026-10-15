"""Safe document storage boundary and its local filesystem implementation."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from backend.documents.storage import (
    DocumentNotFoundError,
    DocumentStorage,
    DocumentStorageCollisionError,
    DocumentStorageError,
    InvalidDocumentFilenameError,
    InvalidStorageIdError,
    StoredDocument,
    validate_document_filename,
)

STORAGE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
__all__ = [
    "DocumentNotFoundError",
    "DocumentStorageCollisionError",
    "DocumentStorageError",
    "FileSystemDocumentStorage",
    "FilesystemDocumentStorage",
    "InvalidDocumentFilenameError",
    "InvalidStorageIdError",
    "StoredDocument",
    "new_storage_id",
    "validate_document_filename",
    "validate_storage_id",
]


def new_storage_id() -> str:
    """Create an opaque, non-user-controlled file name."""
    return uuid4().hex


def validate_storage_id(storage_id: str) -> str:
    if not isinstance(storage_id, str) or STORAGE_ID_PATTERN.fullmatch(storage_id) is None:
        raise InvalidStorageIdError("Storage ID must be a 32-character lowercase hexadecimal value")
    return storage_id


class FilesystemDocumentStorage(DocumentStorage):
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

    @staticmethod
    def new_id() -> str:
        """Create an opaque, non-user-controlled file name."""
        return uuid4().hex

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
                with suppress(OSError):
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
            document = os.fdopen(descriptor, "rb")
        except OSError as error:
            with suppress(OSError):
                os.close(descriptor)
            raise DocumentStorageError(f"Document could not be opened: {storage_id}") from error
        try:
            with document:
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
