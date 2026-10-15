"""Document-owned content storage port and stable storage errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

MAX_FILENAME_LENGTH = 255


class InvalidDocumentFilenameError(ValueError):
    """A display filename contains path or control characters."""


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


class DocumentStorageError(RuntimeError):
    """Base error for document content adapter failures."""


class DocumentNotFoundError(DocumentStorageError):
    """The content referenced by document metadata is absent."""


class DocumentStorageCollisionError(DocumentStorageError):
    """A generated storage identifier is already occupied."""


class InvalidStorageIdError(DocumentStorageError):
    """The consumer supplied an invalid opaque storage identifier."""


@dataclass(frozen=True)
class StoredDocument:
    size_bytes: int
    checksum_sha256: str


class DocumentStorage(Protocol):
    """Content capability required by the documents use cases.

    ``put`` reads a supplied stream from its current position through EOF and
    never closes it; the caller retains ownership and controls its lifetime.
    Byte strings are consumed in full.
    """

    def new_id(self) -> str: ...

    def put(
        self,
        storage_id: str,
        content: bytes | bytearray | memoryview | BinaryIO,
    ) -> StoredDocument: ...

    def read(self, storage_id: str) -> bytes: ...

    def delete(self, storage_id: str) -> bool: ...
