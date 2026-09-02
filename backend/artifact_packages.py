"""Cleartext artifact package boundary used only by the local streaming protocol.

The files created here live in the backend's restricted temporary workspace and
are removed before the administration process exits. Cryptographic protection
is deliberately owned by the Go CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from .backup_restore import (
    ARTIFACT_FORMAT_VERSION,
    DATABASE_NAME,
    FULL_EXPORT_SCHEMA,
    KEY_NAME,
    MANIFEST_NAME,
    STREAM_CHUNK_BYTES,
    ArtifactError,
    ArtifactService,
    LoadedArtifact,
    _canonical_json,
    _document_rows,
    _totp_key_binding,
)
from .database import activation_scope


class ClearArtifactService(ArtifactService):
    """Create and consume validated package streams without cryptography."""

    def write_backup_package(self, output, recipient_fingerprint: str) -> dict[str, Any]:
        try:
            with self._capture_snapshot(include_authentication_key=True) as snapshot:
                entries: dict[str, Path] = {DATABASE_NAME: snapshot.database}
                for document in sorted(snapshot.documents.iterdir()):
                    entries[f"payload/documents/{document.name}"] = document
                if snapshot.authentication_key is None:
                    raise ArtifactError(
                        "authentication_key_missing", "Authentication key is missing"
                    )
                key_file = snapshot.root / "key-1.bin"
                key_file.write_bytes(snapshot.authentication_key)
                os.chmod(key_file, 0o600)
                entries[KEY_NAME] = key_file
                artifact_id = str(uuid4())
                manifest = self._manifest(
                    snapshot,
                    artifact_id=artifact_id,
                    artifact_type="backup",
                    entries=entries,
                    authentication_key_binding=_totp_key_binding(
                        snapshot.database, snapshot.authentication_key
                    ),
                    purpose="complete_instance_restore",
                )
                self._write_package(output, manifest, entries)
                result = self._result(
                    manifest,
                    recipient_fingerprint,
                    records=snapshot.database_records,
                    documents=snapshot.document_count,
                )
            self._record_operation("backup", result=result)
            return result
        except ArtifactError as error:
            self._record_operation("backup", error=error)
            raise

    def write_export_package(self, output, recipient_fingerprint: str) -> dict[str, Any]:
        try:
            with self._capture_snapshot(include_authentication_key=False) as snapshot:
                export_root = snapshot.root / "export"
                export_root.mkdir(mode=0o700)
                data, value_lists = self._export_data(snapshot)
                documents = _document_rows(snapshot.database)
                document_list = {
                    "format": "lzug-full-export-documents",
                    "format_version": 1,
                    "documents": [
                        {
                            "export_id": f"document:{row['id']}",
                            "source_document_id": row["id"],
                            "content_path": f"documents/{row['storage_id']}",
                            "original_filename": row["original_filename"],
                            "media_type": row["media_type"],
                            "size_bytes": row["size_bytes"],
                            "checksum_sha256": row["checksum_sha256"],
                            "relationships": [],
                        }
                        for row in documents
                    ],
                }
                files = {
                    "export/data.json": _canonical_json(data),
                    "export/documents.json": _canonical_json(document_list),
                    "export/value-lists.json": _canonical_json(value_lists),
                    "export/full-export-v1.schema.json": _canonical_json(FULL_EXPORT_SCHEMA),
                    "export/README.txt": b"lzug Vollexport Format 1\n",
                }
                entries: dict[str, Path] = {}
                for name, content in files.items():
                    target = export_root / name.removeprefix("export/")
                    target.write_bytes(content)
                    entries[name] = target
                for document in sorted(snapshot.documents.iterdir()):
                    entries[f"export/documents/{document.name}"] = document
                artifact_id = str(uuid4())
                manifest = self._manifest(
                    snapshot,
                    artifact_id=artifact_id,
                    artifact_type="full_export",
                    entries=entries,
                    authentication_key_binding=None,
                    purpose="authorized_portable_full_export",
                    database_records=data["record_count"],
                )
                self._write_package(output, manifest, entries)
                result = self._result(
                    manifest,
                    recipient_fingerprint,
                    records=data["record_count"],
                    documents=snapshot.document_count,
                )
            self._record_operation("full_export", result=result)
            return result
        except ArtifactError as error:
            self._record_operation("full_export", error=error)
            raise

    def verify_package(self, package: Path, *, expected_type: str | None = None) -> dict[str, Any]:
        with self._loaded_package(package) as loaded:
            if expected_type is not None and loaded.manifest["artifact_type"] != expected_type:
                raise ArtifactError(
                    "artifact_type_mismatch", "Artifact type does not match command"
                )
            return self._verify_loaded(loaded)

    def restore_package(
        self,
        package: Path,
        *,
        replace: bool,
        safety_artifact: str | None,
        recipient_fingerprint: str,
    ) -> dict[str, Any]:
        phase = "precheck"
        manifest: dict[str, Any] | None = None
        try:
            self._fault(phase)
            with self._loaded_package(package) as loaded:
                manifest = loaded.manifest
                if manifest.get("artifact_type") != "backup":
                    raise ArtifactError("restore_requires_backup", "Only a backup can be restored")
                verification = self._verify_loaded(loaded)
                target_empty = self._target_is_empty()
                if not target_empty and not replace:
                    raise ArtifactError(
                        "replace_confirmation_required",
                        "Target contains data and explicit replacement was not confirmed",
                    )
                if replace and not target_empty and not safety_artifact:
                    raise ArtifactError(
                        "safety_artifact_required",
                        "Replacement requires a completed safety artifact",
                    )
                phase = "prepared_restore"
                self._fault(phase)
                with self._prepared_restore(loaded) as prepared:
                    prepared_db, prepared_documents, prepared_key, migrations, reset = prepared
                    phase = "migration"
                    self._fault(phase)
                    phase = "postcheck"
                    self._fault(phase)
                    self._verify_prepared(prepared_db, prepared_documents, prepared_key, manifest)
                    configuration = self._configuration_report(manifest)
                    phase = "activation"
                    with activation_scope(self.paths.database):
                        if not replace and not self._target_is_empty():
                            raise ArtifactError(
                                "target_changed",
                                "Target changed while the restore was prepared",
                                phase=phase,
                            )
                        self._activate_restore(
                            prepared_db,
                            prepared_documents,
                            prepared_key,
                            manifest,
                        )
            result = {
                "artifact_id": manifest["artifact_id"],
                "artifact_type": "backup",
                "source_application_version": manifest["application_version"],
                "target_application_version": verification["target_application_version"],
                "source_schema_version": verification["source_schema_version"],
                "target_schema_version": verification["target_schema_version"],
                "snapshot_at": manifest["snapshot_at"],
                "records": manifest["counts"]["database_records"],
                "documents": manifest["counts"]["documents"],
                "migrations": migrations,
                "reset_security_state": reset,
                "configuration": configuration,
                "readiness": configuration["readiness"],
                "safety_artifact": safety_artifact,
                "recipient_key_fingerprint": recipient_fingerprint,
                "phases": ["precheck", "prepared_restore", "migration", "postcheck", "activation"],
            }
            self._record_operation("restore", result=result)
            return result
        except ArtifactError as error:
            if error.phase == "precheck" and phase != "precheck":
                error.phase = phase
            self._record_operation("restore", error=error, manifest=manifest)
            raise

    @staticmethod
    def _write_package(output, manifest: Mapping[str, Any], entries: Mapping[str, Path]) -> None:
        try:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as package:
                package.writestr(MANIFEST_NAME, _canonical_json(manifest))
                for name, source in sorted(entries.items()):
                    package.write(source, name)
        except (OSError, zipfile.BadZipFile) as error:
            raise ArtifactError(
                "artifact_write_failed", "Clear artifact stream could not be produced"
            ) from error

    @contextmanager
    def _loaded_package(self, package_path: Path) -> Iterator[LoadedArtifact]:
        self._ensure_runtime_paths()
        root = Path(tempfile.mkdtemp(prefix=".lzug-clear-verify-", dir=self.paths.backups))
        os.chmod(root, 0o700)
        try:
            with zipfile.ZipFile(package_path) as package:
                members = package.infolist()
                names = [member.filename for member in members]
                if len(names) != len(set(names)) or MANIFEST_NAME not in names:
                    raise ArtifactError("artifact_content_invalid", "Artifact package is invalid")
                for member in members:
                    path = PurePosixPath(member.filename)
                    if (
                        member.compress_type != zipfile.ZIP_STORED
                        or path.is_absolute()
                        or ".." in path.parts
                        or not path.parts
                        or member.is_dir()
                        or (member.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ArtifactError(
                            "artifact_content_invalid", "Artifact package is invalid"
                        )
                    target = root.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(member) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination, STREAM_CHUNK_BYTES)
            try:
                manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArtifactError("manifest_invalid", "Protected manifest is invalid") from error
            self._validate_manifest(root, manifest)
            yield LoadedArtifact(root, manifest, {})
        except zipfile.BadZipFile as error:
            raise ArtifactError(
                "artifact_content_invalid", "Artifact package is invalid"
            ) from error
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _result(
        manifest: Mapping[str, Any],
        recipient_fingerprint: str,
        *,
        records: int,
        documents: int,
    ) -> dict[str, Any]:
        return {
            "artifact_id": manifest["artifact_id"],
            "artifact_type": manifest["artifact_type"],
            "snapshot_at": manifest["snapshot_at"],
            "records": records,
            "documents": documents,
            "manifest_version": ARTIFACT_FORMAT_VERSION,
            "recipient_key_fingerprint": recipient_fingerprint,
        }
