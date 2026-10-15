"""Consumer-owned document metadata and transaction contracts."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DocumentMetadata:
    id: int
    storage_id: str
    original_filename: str
    media_type: str
    size_bytes: int
    checksum_sha256: str
    created_at: str
    updated_at: str

    def public_projection(self) -> dict[str, object]:
        """Expose API metadata without leaking the adapter's storage key."""
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@runtime_checkable
class DocumentRepository(Protocol):
    def get(self, document_id: int) -> DocumentMetadata | None: ...

    def create(
        self,
        *,
        storage_id: str,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> DocumentMetadata: ...

    def delete(self, document_id: int) -> bool: ...


class DocumentUnitOfWork(Protocol):
    documents: DocumentRepository


class DocumentUnitOfWorkFactory(Protocol):
    def read(self) -> AbstractContextManager[DocumentUnitOfWork]: ...

    def write(self) -> AbstractContextManager[DocumentUnitOfWork]: ...

    def mutation(self) -> AbstractContextManager[None]:
        """Exclude snapshots until the use case and its failure compensation finish."""
        ...
