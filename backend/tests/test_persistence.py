from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database import (
    PersistenceConfigurationError,
    PersistencePaths,
    persistence_paths,
    validate_persistence,
)
from backend.document_storage import (
    DocumentStorageCollisionError,
    DocumentStorageError,
    FileSystemDocumentStorage,
    InvalidDocumentFilenameError,
    InvalidStorageIdError,
    validate_document_filename,
)
from backend.documents import (
    DocumentService,
    DocumentSizeLimitError,
    UnsupportedDocumentMediaTypeError,
    document_upload_policy,
)
from backend.tests.helpers import TempDatabase


class PersistenceConfigurationTests(unittest.TestCase):
    def test_defaults_follow_the_data_contract(self) -> None:
        paths = persistence_paths()

        self.assertEqual(Path("/data/lzug.sqlite"), paths.database)
        self.assertEqual(Path("/data/documents"), paths.documents)
        self.assertEqual(Path("/data/backups"), paths.backups)

    def test_custom_data_directory_derives_all_children(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = persistence_paths(data_dir=directory)

            self.assertEqual(Path(directory) / "lzug.sqlite", paths.database)
            self.assertEqual(Path(directory) / "documents", paths.documents)
            self.assertEqual(Path(directory) / "backups", paths.backups)

    def test_validation_creates_directories_and_checks_free_space(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = persistence_paths(data_dir=directory)

            validate_persistence(paths, minimum_free_bytes=0)

            self.assertTrue(paths.documents.is_dir())
            self.assertTrue(paths.backups.is_dir())

    def test_validation_reports_unwritable_or_invalid_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "database-is-a-directory"
            database_path.mkdir()
            paths = PersistencePaths(
                data_dir=Path(directory) / "data",
                database=database_path,
                documents=Path(directory) / "documents",
                backups=Path(directory) / "backups",
            )

            with self.assertRaisesRegex(PersistenceConfigurationError, "directory"):
                validate_persistence(paths, minimum_free_bytes=0)

    def test_validation_reports_insufficient_space(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = persistence_paths(data_dir=directory)
            with patch("backend.database.shutil.disk_usage") as disk_usage:
                disk_usage.return_value.free = 1
                with self.assertRaisesRegex(PersistenceConfigurationError, "free space"):
                    validate_persistence(paths, minimum_free_bytes=2)

    def test_validation_reports_a_missing_database_after_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = persistence_paths(data_dir=directory)

            with self.assertRaisesRegex(PersistenceConfigurationError, "does not exist"):
                validate_persistence(paths, minimum_free_bytes=0, require_database=True)

    def test_validation_checks_an_existing_database_file_for_write_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = persistence_paths(data_dir=directory)
            paths.database.touch()
            with patch(
                "backend.database._ensure_writable_file",
                side_effect=PersistenceConfigurationError("database is read-only"),
            ):
                with self.assertRaisesRegex(PersistenceConfigurationError, "read-only"):
                    validate_persistence(paths, minimum_free_bytes=0)


class FilesystemDocumentStorageTests(unittest.TestCase):
    def test_put_read_and_delete_are_atomic_and_content_addressed_by_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            stored = storage.put("a" * 32, io.BytesIO(b"hello"))

            self.assertEqual(5, stored.size_bytes)
            self.assertEqual(
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
                stored.checksum_sha256,
            )
            self.assertEqual(b"hello", storage.read("a" * 32))
            self.assertTrue(storage.delete("a" * 32))
            self.assertFalse(storage.delete("a" * 32))

    def test_collisions_and_path_manipulation_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            storage.put("b" * 32, b"first")

            with self.assertRaises(DocumentStorageCollisionError):
                storage.put("b" * 32, b"second")
            with self.assertRaises(InvalidStorageIdError):
                storage.read("../outside")

    def test_failed_write_does_not_publish_a_partial_document(self) -> None:
        class BrokenContent:
            def read(self, _size: int) -> bytes:
                raise OSError("read failed")

        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            with self.assertRaises(DocumentStorageError):
                storage.put("c" * 32, BrokenContent())

            self.assertEqual([], list(Path(directory).glob("*")))

    def test_cleanup_failure_does_not_mask_a_successful_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            with patch("pathlib.Path.unlink", side_effect=OSError("cleanup failed")):
                stored = storage.put("e" * 32, b"content")

            self.assertEqual(7, stored.size_bytes)
            self.assertEqual(b"content", storage.read("e" * 32))

    def test_fdopen_failure_closes_the_open_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            storage.put("f" * 32, b"content")
            with patch(
                "backend.document_storage.os.fdopen",
                side_effect=OSError("fdopen failed"),
            ):
                with patch("backend.document_storage.os.close") as close:
                    with self.assertRaisesRegex(DocumentStorageError, "opened"):
                        storage.read("f" * 32)

            close.assert_called_once()

    def test_display_filenames_cannot_become_paths(self) -> None:
        self.assertEqual("report.pdf", validate_document_filename("report.pdf"))
        for filename in (
            "../report.pdf",
            "folder/report.pdf",
            "folder\\report.pdf",
            "report\x00.pdf",
        ):
            with self.assertRaises(InvalidDocumentFilenameError):
                validate_document_filename(filename)


class DocumentServiceTests(unittest.TestCase):
    def test_metadata_and_content_are_created_and_deleted_together(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            service = DocumentService(FileSystemDocumentStorage(Path(directory)), db_path)
            metadata = service.create(
                b"contract",
                original_filename="contract.pdf",
                media_type="application/pdf",
            )

            loaded_metadata, content = service.get(metadata["id"])
            self.assertEqual(metadata["storage_id"], loaded_metadata["storage_id"])
            self.assertEqual(b"contract", content)
            self.assertTrue(service.delete(metadata["id"]))
            with self.assertRaises(KeyError):
                service.get(metadata["id"])

    def test_database_failure_cleans_up_published_content(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            service = DocumentService(storage, db_path)
            with patch("backend.documents.Store.create", side_effect=RuntimeError("db failed")):
                with self.assertRaisesRegex(RuntimeError, "db failed"):
                    with patch("backend.documents.new_storage_id", return_value="d" * 32):
                        service.create(
                            b"content",
                            original_filename="document.txt",
                            media_type="text/plain",
                        )
            self.assertEqual([], list(Path(directory).glob("*")))

    def test_missing_content_is_an_inconsistency_not_a_silent_success(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            service = DocumentService(storage, db_path)
            metadata = service.create(
                b"content", original_filename="document.txt", media_type="text/plain"
            )
            storage.delete(metadata["storage_id"])

            with self.assertRaises(DocumentStorageError):
                service.delete(metadata["id"])

    def test_failed_metadata_delete_restores_content(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            service = DocumentService(storage, db_path)
            metadata = service.create(
                b"content", original_filename="document.txt", media_type="text/plain"
            )
            with patch("backend.documents.Store.delete", side_effect=RuntimeError("db failed")):
                with self.assertRaisesRegex(RuntimeError, "db failed"):
                    service.delete(metadata["id"])
            self.assertEqual(b"content", storage.read(metadata["storage_id"]))

    def test_upload_size_is_enforced_for_bytes_and_streams_before_metadata(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            storage = FileSystemDocumentStorage(Path(directory))
            service = DocumentService(storage, db_path, max_size_bytes=4)

            with self.assertRaises(DocumentSizeLimitError):
                service.create(
                    b"12345", original_filename="large.pdf", media_type="application/pdf"
                )
            with self.assertRaises(DocumentSizeLimitError):
                service.create(
                    io.BytesIO(b"12345"),
                    original_filename="stream.pdf",
                    media_type="application/pdf",
                )

            self.assertEqual([], list(Path(directory).glob("*")))

    def test_upload_media_type_uses_an_exact_allowlist(self) -> None:
        with TempDatabase() as db_path, tempfile.TemporaryDirectory() as directory:
            service = DocumentService(FileSystemDocumentStorage(Path(directory)), db_path)

            with self.assertRaises(UnsupportedDocumentMediaTypeError):
                service.create(
                    b"<svg/>",
                    original_filename="active.svg",
                    media_type="image/svg+xml",
                )

    def test_upload_policy_rejects_wildcards_and_unbounded_sizes(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact media types"):
            document_upload_policy({"LZUG_ALLOWED_UPLOAD_MEDIA_TYPES": "image/*"})
        with self.assertRaisesRegex(ValueError, "between"):
            document_upload_policy({"LZUG_MAX_UPLOAD_BYTES": "0"})
