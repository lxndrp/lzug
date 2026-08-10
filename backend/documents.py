"""Document metadata/content coordination through SQLAlchemy and storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

from .database import DEFAULT_DB_PATH, session_scope
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


class DocumentService:
    """Keep one metadata transaction and one content operation consistent."""

    def __init__(self, storage: DocumentStorage, db_path: Path = DEFAULT_DB_PATH):
        self.storage = storage
        self.db_path = db_path

    def create(
        self,
        content: bytes | bytearray | memoryview | BinaryIO,
        *,
        original_filename: str,
        media_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        validate_document_filename(original_filename)
        self._validate_media_type(media_type)
        storage_id = new_storage_id()
        stored = self.storage.put(storage_id, content)
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
                    raise DocumentConsistencyError(f"Document metadata disappeared: {document_id}")
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
