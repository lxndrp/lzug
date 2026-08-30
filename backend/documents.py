"""Document metadata/content coordination through SQLAlchemy and storage."""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, BinaryIO

from .database import DEFAULT_DB_PATH, mutation_scope, session_scope
from .document_storage import (
    DocumentStorage,
    DocumentStorageError,
    new_storage_id,
    validate_document_filename,
)
from .models import DOCUMENT
from .store import Store


class DocumentConsistencyError(DocumentStorageError):
    """Database metadata and content could not be kept in agreement."""


class DocumentSizeLimitError(ValueError):
    """Document content exceeds the configured upload boundary."""


class UnsupportedDocumentMediaTypeError(ValueError):
    """Document content type is outside the explicit upload allowlist."""


DEFAULT_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DEFAULT_ALLOWED_DOCUMENT_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
    }
)
MEDIA_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class _LimitedReader:
    def __init__(self, source: BinaryIO, maximum_bytes: int):
        self.source = source
        self.maximum_bytes = maximum_bytes
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        remaining_with_probe = self.maximum_bytes + 1 - self.bytes_read
        requested = remaining_with_probe if size < 0 else min(size, remaining_with_probe)
        chunk = self.source.read(requested)
        self.bytes_read += len(chunk)
        if self.bytes_read > self.maximum_bytes:
            raise DocumentSizeLimitError(f"Document exceeds {self.maximum_bytes} bytes.")
        return chunk


def document_upload_policy(
    environment: Mapping[str, str] | None = None,
) -> tuple[int, frozenset[str]]:
    values = os.environ if environment is None else environment
    raw_maximum = values.get("LZUG_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_DOCUMENT_BYTES))
    try:
        maximum = int(raw_maximum)
    except ValueError as error:
        raise ValueError("LZUG_MAX_UPLOAD_BYTES must be an integer") from error
    if not 1024 <= maximum <= 100 * 1024 * 1024:
        raise ValueError("LZUG_MAX_UPLOAD_BYTES must be between 1024 and 104857600")

    configured_types = values.get("LZUG_ALLOWED_UPLOAD_MEDIA_TYPES")
    allowed_types = (
        frozenset(value.strip().lower() for value in configured_types.split(",") if value.strip())
        if configured_types is not None
        else DEFAULT_ALLOWED_DOCUMENT_MEDIA_TYPES
    )
    if not allowed_types or any(
        MEDIA_TYPE_PATTERN.fullmatch(value) is None for value in allowed_types
    ):
        raise ValueError(
            "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES must contain comma-separated exact media types"
        )
    return maximum, allowed_types


class DocumentService:
    """Keep one metadata transaction and one content operation consistent."""

    def __init__(
        self,
        storage: DocumentStorage,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        max_size_bytes: int | None = None,
        allowed_media_types: Collection[str] | None = None,
    ):
        configured_maximum, configured_types = document_upload_policy()
        self.storage = storage
        self.db_path = db_path
        self.max_size_bytes = configured_maximum if max_size_bytes is None else max_size_bytes
        selected_media_types = (
            configured_types if allowed_media_types is None else allowed_media_types
        )
        self.allowed_media_types = frozenset(
            media_type.strip().lower() for media_type in selected_media_types
        )
        if (
            self.max_size_bytes <= 0
            or not self.allowed_media_types
            or any(
                MEDIA_TYPE_PATTERN.fullmatch(media_type) is None
                for media_type in self.allowed_media_types
            )
        ):
            raise ValueError("Document upload policy must contain a positive size and exact types")

    def create(
        self,
        content: bytes | bytearray | memoryview | BinaryIO,
        *,
        original_filename: str,
        media_type: str,
    ) -> dict[str, Any]:
        with mutation_scope(self.db_path):
            validate_document_filename(original_filename)
            self._validate_media_type(media_type)
            if media_type.lower() not in self.allowed_media_types:
                raise UnsupportedDocumentMediaTypeError(
                    f"Document media type is not allowed: {media_type}"
                )
            bounded_content = self._bounded_content(content)
            storage_id = new_storage_id()
            stored = self.storage.put(storage_id, bounded_content)
            try:
                with session_scope(self.db_path) as session:
                    return Store(session).create(
                        DOCUMENT,
                        {
                            "storage_id": storage_id,
                            "original_filename": original_filename,
                            "media_type": media_type,
                            "size_bytes": stored.size_bytes,
                            "checksum_sha256": stored.checksum_sha256,
                        },
                    )
            except Exception:
                try:
                    self.storage.delete(storage_id)
                except Exception as cleanup_error:
                    raise DocumentConsistencyError(
                        f"Document metadata failed and content cleanup also failed: {storage_id}"
                    ) from cleanup_error
                raise

    def get(self, document_id: int) -> tuple[dict[str, Any], bytes]:
        with session_scope(self.db_path) as session:
            metadata = Store(session).get(DOCUMENT, document_id)
        if metadata is None:
            raise KeyError(document_id)
        content = self.storage.read(metadata["storage_id"])
        return metadata, content

    def delete(self, document_id: int) -> bool:
        with mutation_scope(self.db_path):
            with session_scope(self.db_path) as session:
                metadata = Store(session).get(DOCUMENT, document_id)
            if metadata is None:
                return False
            content = self.storage.read(metadata["storage_id"])
            if not self.storage.delete(metadata["storage_id"]):
                raise DocumentConsistencyError(
                    f"Document metadata exists but content is missing: {metadata['storage_id']}"
                )
            try:
                with session_scope(self.db_path) as session:
                    deleted = Store(session).delete(DOCUMENT, document_id)
                    if not deleted:
                        raise DocumentConsistencyError(
                            f"Document metadata disappeared: {document_id}"
                        )
                    return True
            except Exception:
                try:
                    self.storage.put(metadata["storage_id"], content)
                except Exception as restore_error:
                    raise DocumentConsistencyError(
                        f"Document metadata deletion failed and content restore also failed: "
                        f"{metadata['storage_id']}"
                    ) from restore_error
                raise

    @staticmethod
    def _validate_media_type(media_type: str) -> None:
        if (
            not isinstance(media_type, str)
            or not media_type
            or len(media_type) > 255
            or any(ord(character) < 32 or ord(character) == 127 for character in media_type)
        ):
            raise ValueError("Media type must contain 1 to 255 printable characters")

    def _bounded_content(
        self, content: bytes | bytearray | memoryview | BinaryIO
    ) -> bytes | _LimitedReader:
        if isinstance(content, (bytes, bytearray, memoryview)):
            value = bytes(content)
            if len(value) > self.max_size_bytes:
                raise DocumentSizeLimitError(f"Document exceeds {self.max_size_bytes} bytes.")
            return value
        return _LimitedReader(content, self.max_size_bytes)
