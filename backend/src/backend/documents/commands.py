"""Document use cases and the policy governing content/metadata consistency."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import BinaryIO

from backend.documents.contracts import (
    DocumentMetadata,
    DocumentUnitOfWorkFactory,
)
from backend.documents.storage import (
    DocumentStorage,
    DocumentStorageError,
    validate_document_filename,
)
from backend.settings import DocumentSettings, RuntimeSettings

DEFAULT_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DEFAULT_ALLOWED_DOCUMENT_MEDIA_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "text/plain"}
)
MEDIA_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class DocumentConsistencyError(DocumentStorageError):
    """Database metadata and content could not be kept in agreement."""


class DocumentSizeLimitError(ValueError):
    """Document content exceeds the configured upload boundary."""


class UnsupportedDocumentMediaTypeError(ValueError):
    """Document content type is outside the explicit upload allowlist."""


@dataclass(frozen=True)
class CreateDocument:
    """Upload content from its current stream position through EOF.

    A supplied stream remains owned by the caller and is left open.
    """

    content: bytes | bytearray | memoryview | BinaryIO
    original_filename: str
    media_type: str


@dataclass(frozen=True)
class GetDocument:
    document_id: int


@dataclass(frozen=True)
class DeleteDocument:
    document_id: int


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
    *,
    settings: DocumentSettings | None = None,
) -> tuple[int, frozenset[str]]:
    configured = settings or RuntimeSettings.from_environment(environment).documents
    maximum = configured.max_upload_bytes
    allowed_types = configured.allowed_upload_media_types
    if not allowed_types or any(
        MEDIA_TYPE_PATTERN.fullmatch(value) is None for value in allowed_types
    ):
        raise ValueError(
            "LZUG_ALLOWED_UPLOAD_MEDIA_TYPES must contain comma-separated exact media types"
        )
    return maximum, allowed_types


class DocumentUseCases:
    """Coordinate metadata transactions with the document content port."""

    def __init__(
        self,
        unit_of_work_factory: DocumentUnitOfWorkFactory,
        storage: DocumentStorage,
        *,
        settings: DocumentSettings | None = None,
        max_size_bytes: int | None = None,
        allowed_media_types: Collection[str] | None = None,
    ):
        configured_maximum, configured_types = document_upload_policy(settings=settings)
        self.unit_of_work_factory = unit_of_work_factory
        self.storage = storage
        self.max_size_bytes = configured_maximum if max_size_bytes is None else max_size_bytes
        selected = configured_types if allowed_media_types is None else allowed_media_types
        self.allowed_media_types = frozenset(value.strip().lower() for value in selected)
        if (
            self.max_size_bytes <= 0
            or not self.allowed_media_types
            or any(
                MEDIA_TYPE_PATTERN.fullmatch(value) is None for value in self.allowed_media_types
            )
        ):
            raise ValueError("Document upload policy must contain a positive size and exact types")

    def create(self, command: CreateDocument) -> DocumentMetadata:
        validate_document_filename(command.original_filename)
        self._validate_media_type(command.media_type)
        if command.media_type.lower() not in self.allowed_media_types:
            raise UnsupportedDocumentMediaTypeError(
                f"Document media type is not allowed: {command.media_type}"
            )
        bounded_content = self._bounded_content(command.content)
        storage_id = self.storage.new_id()
        content_published = False
        with self.unit_of_work_factory.mutation():
            try:
                with self.unit_of_work_factory.write() as work:
                    stored = self.storage.put(storage_id, bounded_content)
                    content_published = True
                    return work.documents.create(
                        storage_id=storage_id,
                        original_filename=command.original_filename,
                        media_type=command.media_type,
                        size_bytes=stored.size_bytes,
                        checksum_sha256=stored.checksum_sha256,
                    )
            except Exception:
                if content_published:
                    try:
                        self.storage.delete(storage_id)
                    except Exception as cleanup_error:
                        raise DocumentConsistencyError(
                            "Document metadata failed and content cleanup also failed: "
                            f"{storage_id}"
                        ) from cleanup_error
                raise

    def get(self, query: GetDocument) -> tuple[DocumentMetadata, bytes]:
        with self.unit_of_work_factory.read() as work:
            metadata = work.documents.get(query.document_id)
        if metadata is None:
            raise KeyError(query.document_id)
        return metadata, self.storage.read(metadata.storage_id)

    def delete(self, command: DeleteDocument) -> bool:
        deleted_content: tuple[str, bytes] | None = None
        with self.unit_of_work_factory.mutation():
            try:
                with self.unit_of_work_factory.write() as work:
                    metadata = work.documents.get(command.document_id)
                    if metadata is None:
                        return False
                    content = self.storage.read(metadata.storage_id)
                    if not self.storage.delete(metadata.storage_id):
                        raise DocumentConsistencyError(
                            "Document metadata exists but content is missing: "
                            f"{metadata.storage_id}"
                        )
                    deleted_content = metadata.storage_id, content
                    if not work.documents.delete(command.document_id):
                        raise DocumentConsistencyError(
                            f"Document metadata disappeared: {command.document_id}"
                        )
                return True
            except Exception:
                if deleted_content is not None:
                    try:
                        self.storage.put(*deleted_content)
                    except Exception as restore_error:
                        raise DocumentConsistencyError(
                            "Document metadata deletion failed and content restore also failed: "
                            f"{deleted_content[0]}"
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

    def _bounded_content(self, content: bytes | bytearray | memoryview | BinaryIO):
        if isinstance(content, (bytes, bytearray, memoryview)):
            value = bytes(content)
            if len(value) > self.max_size_bytes:
                raise DocumentSizeLimitError(f"Document exceeds {self.max_size_bytes} bytes.")
            return value
        return _LimitedReader(content, self.max_size_bytes)
