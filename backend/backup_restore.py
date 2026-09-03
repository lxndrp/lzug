"""Clear artifact package, restore, and full-export domain contract.

The backend owns SQLite and document consistency, package validation, restore
staging, and activation. Cryptographic protection is exclusively owned by the
Go operator CLI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken

from .database import (
    BUSY_TIMEOUT_MS,
    MIGRATIONS_PATH,
    PersistencePaths,
    apply_migrations,
    database_readiness,
    migration_status,
    mutation_scope,
    persistence_paths,
    snapshot_scope,
)
from .local_auth import authentication_key, authentication_key_path
from .version import application_version

ARTIFACT_FORMAT_VERSION = 1
STREAM_CHUNK_BYTES = 1024 * 1024
MIN_SUPPORTED_SCHEMA = "009_harden_migration_history.sql"
KEY_NAME = "payload/keys/key-1.bin"
DATABASE_NAME = "payload/database.sqlite"
MANIFEST_NAME = "manifest.json"
ARTIFACT_SUFFIX = ".lzug"
REQUIRED_CONFIG_ENV = "LZUG_REQUIRED_EXTERNAL_CONFIG"
BACKUP_PUBLIC_KEY_ENV = "LZUG_BACKUP_RECIPIENT_PUBLIC_KEY"

_EXCLUDED_EXPORT_TABLES = frozenset(
    {
        "artifact_operation",
        "auth_recovery_code",
        "auth_session",
        "auth_token",
        "calendar_feed",
        "committee_admin_operation",
        "instance_metadata",
        "notification_delivery",
        "push_subscription",
        "schema_migration",
        "schema_migration_checksum",
        "user_account",
    }
)
_FORBIDDEN_EXPORT_FIELDS = frozenset(
    {
        "claim_expires_at",
        "claim_token",
        "claimed_at",
        "code_hash",
        "csrf_token_hash",
        "endpoint",
        "password_hash",
        "token_hash",
        "totp_secret_encrypted",
    }
)
_ARTIFACT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,180}\.lzug$")
_ENV_NAME = re.compile(r"^LZUG_[A-Z0-9_]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

FULL_EXPORT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/lxndrp/lzug/full-export-v1.schema.json",
    "title": "lzug full export data",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "format",
        "format_version",
        "snapshot_at",
        "instance_id",
        "record_count",
        "tables",
    ],
    "properties": {
        "format": {"const": "lzug-full-export"},
        "format_version": {"const": 1},
        "snapshot_at": {"type": "string", "format": "date-time"},
        "instance_id": {"type": "string"},
        "record_count": {"type": "integer", "minimum": 0},
        "tables": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "required": ["columns", "rows"],
                "properties": {
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["export_id", "attributes", "relationships"],
                            "properties": {
                                "export_id": {"type": "string"},
                                "attributes": {"type": "object"},
                                "relationships": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["export_id", "target_column"],
                                        "properties": {
                                            "export_id": {"type": "string"},
                                            "target_column": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


class ArtifactError(RuntimeError):
    """Secret-free, protocol-stable artifact operation error."""

    def __init__(self, code: str, message: str, *, phase: str = "precheck") -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase


@dataclass(frozen=True)
class CapturedSnapshot:
    root: Path
    database: Path
    documents: Path
    authentication_key: bytes | None
    snapshot_at: str
    instance_id: str
    schema_version: str
    database_records: int
    document_count: int


@dataclass(frozen=True)
class LoadedArtifact:
    root: Path
    manifest: dict[str, Any]
    header: dict[str, Any]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(STREAM_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise ArtifactError(
            "artifact_content_invalid", "Artifact content could not be read"
        ) from error
    return digest.hexdigest()


def _database_connection(path: Path, *, read_only: bool = True) -> sqlite3.Connection:
    if read_only:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000)
    else:
        connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _database_integrity(path: Path) -> None:
    try:
        with closing(_database_connection(path)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchall()
            if [row[0] for row in result] != ["ok"]:
                raise ArtifactError("database_integrity_failed", "Database integrity check failed")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ArtifactError("database_integrity_failed", "Database relations are invalid")
    except ArtifactError:
        raise
    except sqlite3.Error as error:
        raise ArtifactError(
            "database_integrity_failed", "Database integrity check failed"
        ) from error


def _migration_names(path: Path) -> tuple[str, ...]:
    try:
        with closing(_database_connection(path)) as connection:
            rows = connection.execute("SELECT name FROM schema_migration ORDER BY rowid").fetchall()
    except sqlite3.Error as error:
        raise ArtifactError("schema_incompatible", "Schema history is unavailable") from error
    return tuple(str(row[0]) for row in rows)


def _available_migrations() -> tuple[str, ...]:
    return tuple(
        migration.name
        for migration in sorted(MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql"))
        if not migration.name.startswith("000_")
    )


def _schema_compatibility(path: Path) -> tuple[str, list[str]]:
    available = _available_migrations()
    applied = _migration_names(path)
    if not applied or applied != available[: len(applied)]:
        unknown = set(applied) - set(available)
        code = "source_newer" if unknown else "schema_incompatible"
        raise ArtifactError(code, "Artifact schema is not supported")
    if available.index(applied[-1]) < available.index(MIN_SUPPORTED_SCHEMA):
        raise ArtifactError("source_unsupported", "Artifact source schema is no longer supported")
    status = migration_status(path)
    if status["state"] not in {"ready", "migration_required"}:
        raise ArtifactError("schema_incompatible", "Artifact schema metadata is invalid")
    current = status.get("current")
    pending = status.get("pending")
    if current != applied[-1] or not isinstance(pending, list):
        raise ArtifactError("schema_incompatible", "Artifact schema metadata is invalid")
    return applied[-1], [str(name) for name in pending]


def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    ]


def _database_record_count(path: Path) -> int:
    with closing(_database_connection(path)) as connection:
        total = 0
        for table in _table_names(connection):
            total += int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        return total


def _instance_id(path: Path) -> str:
    try:
        with closing(_database_connection(path)) as connection:
            value = connection.execute(
                "SELECT instance_id FROM instance_metadata WHERE id = 1"
            ).fetchone()
    except sqlite3.Error as error:
        raise ArtifactError("schema_incompatible", "Instance identity is unavailable") from error
    if value is None or not isinstance(value[0], str):
        raise ArtifactError("schema_incompatible", "Instance identity is unavailable")
    return value[0]


def _snapshot_instance_id(path: Path) -> str:
    if "024_add_artifact_operations.sql" not in _migration_names(path):
        return str(uuid4())
    return _instance_id(path)


def _document_rows(path: Path) -> list[dict[str, Any]]:
    try:
        with closing(_database_connection(path)) as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id, storage_id, original_filename, media_type, size_bytes, "
                    "checksum_sha256 FROM document ORDER BY id"
                )
            ]
    except sqlite3.Error as error:
        raise ArtifactError("document_relation_failed", "Document metadata is invalid") from error


def _validate_document_snapshot(database: Path, documents: Path) -> list[dict[str, Any]]:
    rows = _document_rows(database)
    expected = {str(row["storage_id"]): row for row in rows}
    try:
        entries = list(documents.iterdir())
    except OSError as error:
        raise ArtifactError(
            "document_relation_failed", "Document storage is unavailable"
        ) from error
    actual: set[str] = set()
    for entry in entries:
        if entry.name.startswith("."):
            raise ArtifactError("document_relation_failed", "Temporary document content remains")
        if entry.is_symlink() or not entry.is_file():
            raise ArtifactError("document_relation_failed", "Document storage entry is invalid")
        actual.add(entry.name)
    if actual != set(expected):
        raise ArtifactError("document_relation_failed", "Document references are incomplete")
    for storage_id, row in expected.items():
        content = documents / storage_id
        if (
            content.stat().st_size != row["size_bytes"]
            or _sha256(content) != row["checksum_sha256"]
        ):
            raise ArtifactError("document_integrity_failed", "Document integrity check failed")
    return rows


def _totp_key_binding(database: Path, key: bytes) -> str:
    database_digest = bytes.fromhex(_sha256(database))
    return "hmac-sha256:" + hmac.new(key, database_digest, hashlib.sha256).hexdigest()


def _validate_totp_secrets(database: Path, key: bytes) -> int:
    try:
        cipher = Fernet(key)
        with closing(_database_connection(database)) as connection:
            rows = connection.execute(
                "SELECT totp_secret_encrypted FROM user_account "
                "WHERE totp_secret_encrypted IS NOT NULL"
            ).fetchall()
        for row in rows:
            secret = cipher.decrypt(str(row[0]).encode("ascii"))
            if not secret or not secret.isascii():
                raise InvalidToken
        return len(rows)
    except (InvalidToken, ValueError, OSError, sqlite3.Error) as error:
        raise ArtifactError(
            "authentication_key_invalid", "Authentication key validation failed"
        ) from error


class ArtifactService:
    """Clear-package domain service shared by the backend stream boundary."""

    def __init__(
        self,
        paths: PersistencePaths | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.paths = paths or persistence_paths()
        self.environment = environment if environment is not None else os.environ
        self.fault_injector = fault_injector

    @contextmanager
    def _capture_snapshot(self, *, include_authentication_key: bool) -> Iterator[CapturedSnapshot]:
        self._ensure_runtime_paths()
        estimated = self.paths.database.stat().st_size if self.paths.database.exists() else 0
        estimated += sum(
            entry.stat().st_size
            for entry in self.paths.documents.iterdir()
            if entry.is_file() and not entry.is_symlink()
        )
        self._ensure_space(self.paths.backups, max(estimated * 3, 1024 * 1024))
        key = authentication_key(self.paths.database) if include_authentication_key else None
        root = Path(tempfile.mkdtemp(prefix=".lzug-snapshot-", dir=self.paths.backups))
        os.chmod(root, 0o700)
        try:
            with snapshot_scope(self.paths.database):
                snapshot = self._copy_snapshot_locked(root, key)
            self._verify_snapshot(snapshot)
            yield snapshot
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @contextmanager
    def _capture_snapshot_locked(self) -> Iterator[CapturedSnapshot]:
        root = Path(tempfile.mkdtemp(prefix=".lzug-safety-", dir=self.paths.backups))
        os.chmod(root, 0o700)
        try:
            with snapshot_scope(self.paths.database):
                key_path = authentication_key_path(self.paths.database)
                key = key_path.read_bytes() if key_path.exists() else Fernet.generate_key()
                snapshot = self._copy_snapshot_locked(root, key)
            self._verify_snapshot(snapshot)
            yield snapshot
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _copy_snapshot_locked(self, root: Path, key: bytes | None) -> CapturedSnapshot:
        if not self.paths.database.is_file():
            raise ArtifactError("database_not_ready", "Database is not available")
        database = root / "database.sqlite"
        documents = root / "documents"
        documents.mkdir(mode=0o700)
        try:
            with closing(_database_connection(self.paths.database)) as source:
                with closing(_database_connection(database, read_only=False)) as target:
                    source.backup(target)
                    target.commit()
        except sqlite3.Error as error:
            raise ArtifactError("snapshot_failed", "SQLite snapshot failed") from error
        snapshot_at = _timestamp()
        rows = _document_rows(database)
        expected = {str(row["storage_id"]) for row in rows}
        actual = {
            entry.name
            for entry in self.paths.documents.iterdir()
            if entry.is_file() and not entry.is_symlink() and not entry.name.startswith(".")
        }
        invalid = [
            entry
            for entry in self.paths.documents.iterdir()
            if entry.name.startswith(".") or entry.is_symlink() or not entry.is_file()
        ]
        if invalid or actual != expected:
            raise ArtifactError("document_relation_failed", "Document references are incomplete")
        try:
            for storage_id in sorted(expected):
                os.link(self.paths.documents / storage_id, documents / storage_id)
        except OSError as error:
            raise ArtifactError("snapshot_failed", "Document snapshot failed") from error
        schema_version, _pending = _schema_compatibility(database)
        return CapturedSnapshot(
            root=root,
            database=database,
            documents=documents,
            authentication_key=key,
            snapshot_at=snapshot_at,
            instance_id=_snapshot_instance_id(database),
            schema_version=schema_version,
            database_records=_database_record_count(database),
            document_count=len(rows),
        )

    def _verify_snapshot(self, snapshot: CapturedSnapshot) -> None:
        _database_integrity(snapshot.database)
        _validate_document_snapshot(snapshot.database, snapshot.documents)
        if snapshot.authentication_key is not None:
            _validate_totp_secrets(snapshot.database, snapshot.authentication_key)

    def _manifest(
        self,
        snapshot: CapturedSnapshot,
        *,
        artifact_id: str,
        artifact_type: str,
        entries: Mapping[str, Path],
        authentication_key_binding: str | None,
        purpose: str,
        database_records: int | None = None,
    ) -> dict[str, Any]:
        return {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "application_version": application_version(),
            "schema_version": snapshot.schema_version,
            "format_version": ARTIFACT_FORMAT_VERSION,
            "created_at": _timestamp(),
            "snapshot_at": snapshot.snapshot_at,
            "instance_id": snapshot.instance_id,
            "contents": [
                {
                    "path": name,
                    "size_bytes": path.stat().st_size,
                    "checksum_sha256": _sha256(path),
                }
                for name, path in sorted(entries.items())
            ],
            "counts": {
                "database_records": (
                    snapshot.database_records if database_records is None else database_records
                ),
                "documents": snapshot.document_count,
            },
            "authentication_key_binding": authentication_key_binding,
            "operator_configuration": self._configuration_manifest(),
            "compatibility": {
                "minimum_schema": MIN_SUPPORTED_SCHEMA,
                "maximum_schema": _available_migrations()[-1],
                "restore": artifact_type == "backup",
                "purpose": purpose,
            },
        }

    def _validate_manifest(self, root: Path, manifest: object) -> None:
        manifest = self._validated_manifest_shape(manifest)
        artifact_type = self._validated_manifest_identity(manifest)
        self._validate_manifest_counts(manifest)
        self._validate_manifest_key_binding(manifest, artifact_type)
        self._validate_manifest_configuration(manifest)
        self._validate_manifest_compatibility(manifest, artifact_type)
        self._validate_manifest_contents(root, manifest)

    def _validated_manifest_shape(self, manifest: object) -> dict[str, Any]:
        fields = {
            "artifact_id",
            "artifact_type",
            "application_version",
            "schema_version",
            "format_version",
            "created_at",
            "snapshot_at",
            "instance_id",
            "contents",
            "counts",
            "authentication_key_binding",
            "operator_configuration",
            "compatibility",
        }
        if not isinstance(manifest, dict) or set(manifest) != fields:
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        return manifest

    def _validated_manifest_identity(self, manifest: dict[str, Any]) -> str:
        artifact_type = manifest.get("artifact_type")
        if (
            artifact_type not in {"backup", "full_export"}
            or manifest.get("format_version") != ARTIFACT_FORMAT_VERSION
            or not isinstance(manifest.get("application_version"), str)
            or not manifest["application_version"]
            or len(manifest["application_version"]) > 200
            or not isinstance(manifest.get("schema_version"), str)
            or not manifest["schema_version"]
            or not isinstance(manifest.get("contents"), list)
        ):
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        try:
            UUID(str(manifest.get("artifact_id")))
            UUID(str(manifest.get("instance_id")))
            for name in ("created_at", "snapshot_at"):
                timestamp = datetime.fromisoformat(str(manifest.get(name)))
                if timestamp.tzinfo is None:
                    raise ValueError
        except TypeError, ValueError:
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid") from None
        return artifact_type

    def _validate_manifest_counts(self, manifest: dict[str, Any]) -> None:
        counts = manifest.get("counts")
        if not isinstance(counts, dict) or set(counts) != {
            "database_records",
            "documents",
        }:
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        ):
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")

    def _validate_manifest_key_binding(self, manifest: dict[str, Any], artifact_type: str) -> None:
        binding = manifest.get("authentication_key_binding")
        if artifact_type == "backup":
            if (
                not isinstance(binding, str)
                or not binding.startswith("hmac-sha256:")
                or _SHA256.fullmatch(binding.removeprefix("hmac-sha256:")) is None
            ):
                raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        elif binding is not None:
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")

    def _validate_manifest_configuration(self, manifest: dict[str, Any]) -> None:
        configuration = manifest.get("operator_configuration")
        if (
            not isinstance(configuration, dict)
            or set(configuration) != {"dependencies", "effective_settings"}
            or not isinstance(configuration["dependencies"], list)
            or not isinstance(configuration["effective_settings"], dict)
            or set(configuration["effective_settings"])
            != {"LZUG_EXTERNAL_URL", "LZUG_TIMEZONE", "LZUG_CALENDAR_TIMEZONE"}
        ):
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        for dependency in configuration["dependencies"]:
            if (
                not isinstance(dependency, dict)
                or set(dependency) != {"name", "kind", "required", "configured"}
                or not isinstance(dependency["name"], str)
                or dependency["kind"] not in {"external_runtime_configuration", "optional_channel"}
                or not isinstance(dependency["required"], bool)
                or not isinstance(dependency["configured"], bool)
            ):
                raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        for fingerprint in configuration["effective_settings"].values():
            if fingerprint is not None and (
                not isinstance(fingerprint, str)
                or not fingerprint.startswith("sha256:")
                or _SHA256.fullmatch(fingerprint.removeprefix("sha256:")) is None
            ):
                raise ArtifactError("manifest_invalid", "Protected manifest is invalid")

    def _validate_manifest_compatibility(
        self, manifest: dict[str, Any], artifact_type: str
    ) -> None:
        compatibility = manifest.get("compatibility")
        expected_purpose = (
            "complete_instance_restore"
            if artifact_type == "backup"
            else "authorized_portable_full_export"
        )
        if (
            not isinstance(compatibility, dict)
            or set(compatibility) != {"minimum_schema", "maximum_schema", "restore", "purpose"}
            or compatibility["minimum_schema"] != MIN_SUPPORTED_SCHEMA
            or not isinstance(compatibility["maximum_schema"], str)
            or compatibility["restore"] is not (artifact_type == "backup")
            or compatibility["purpose"] != expected_purpose
        ):
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")

    def _validate_manifest_contents(self, root: Path, manifest: dict[str, Any]) -> None:
        declared: set[str] = set()
        for entry in manifest["contents"]:
            self._validate_manifest_content(root, entry, declared)
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != "package.zip" and path.name != MANIFEST_NAME
        }
        if actual != declared:
            raise ArtifactError("manifest_invalid", "Protected manifest content list is incomplete")

    def _validate_manifest_content(self, root: Path, entry: object, declared: set[str]) -> None:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "size_bytes",
            "checksum_sha256",
        }:
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        name = entry["path"]
        size = entry["size_bytes"]
        checksum = entry["checksum_sha256"]
        path = PurePosixPath(name) if isinstance(name, str) else None
        if (
            path is None
            or path.is_absolute()
            or ".." in path.parts
            or name in declared
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(checksum, str)
            or _SHA256.fullmatch(checksum) is None
        ):
            raise ArtifactError("manifest_invalid", "Protected manifest is invalid")
        declared.add(name)
        target = root.joinpath(*path.parts)
        if not target.is_file() or target.stat().st_size != size or _sha256(target) != checksum:
            raise ArtifactError("artifact_content_invalid", "Artifact content is invalid")

    def _verify_loaded(self, loaded: LoadedArtifact) -> dict[str, Any]:
        manifest = loaded.manifest
        if manifest["artifact_type"] == "backup":
            database = loaded.root / DATABASE_NAME
            key_path = loaded.root / KEY_NAME
            documents = loaded.root / "payload/documents"
            if manifest["counts"]["documents"] == 0 and not documents.exists():
                documents.mkdir(parents=True)
            if not database.is_file() or not key_path.is_file() or not documents.is_dir():
                raise ArtifactError("artifact_content_invalid", "Backup content is incomplete")
            source_schema, pending = _schema_compatibility(database)
            _database_integrity(database)
            rows = _validate_document_snapshot(database, documents)
            key = key_path.read_bytes()
            totp_count = _validate_totp_secrets(database, key)
            if manifest["authentication_key_binding"] != _totp_key_binding(database, key):
                raise ArtifactError(
                    "authentication_key_invalid", "Authentication key binding is invalid"
                )
            if len(rows) != manifest["counts"]["documents"]:
                raise ArtifactError("manifest_invalid", "Backup document count is invalid")
            if _database_record_count(database) != manifest["counts"]["database_records"]:
                raise ArtifactError("manifest_invalid", "Backup record count is invalid")
        else:
            source_schema = str(manifest["schema_version"])
            pending = []
            totp_count = 0
            self._validate_export(loaded.root, manifest)
        configuration = self._configuration_report(manifest)
        return {
            "artifact_id": manifest["artifact_id"],
            "artifact_type": manifest["artifact_type"],
            "source_application_version": manifest["application_version"],
            "target_application_version": application_version(),
            "source_schema_version": source_schema,
            "target_schema_version": _available_migrations()[-1],
            "pending_migrations": pending,
            "snapshot_at": manifest["snapshot_at"],
            "records": manifest["counts"]["database_records"],
            "documents": manifest["counts"]["documents"],
            "totp_secrets_verified": totp_count,
            "configuration": configuration,
            "readiness": configuration["readiness"],
        }

    def _validate_export(self, root: Path, manifest: dict[str, Any]) -> None:
        declared = self._validate_export_paths(manifest)
        data, documents, value_lists, schema = self._load_export_payloads(root)
        self._validate_export_contract(data, documents, value_lists, schema, manifest)
        self._validate_export_tables(data, manifest)
        self._validate_export_documents(root, documents, declared, manifest)

    def _validate_export_paths(self, manifest: dict[str, Any]) -> set[str]:
        required = {
            "export/data.json",
            "export/documents.json",
            "export/value-lists.json",
            "export/full-export-v1.schema.json",
            "export/README.txt",
        }
        declared = {entry["path"] for entry in manifest["contents"]}
        if not required.issubset(declared) or any(name.startswith("payload/") for name in declared):
            raise ArtifactError("export_invalid", "Full export content is invalid")
        return declared

    def _load_export_payloads(self, root: Path) -> tuple[object, object, object, object]:
        try:
            data = json.loads((root / "export/data.json").read_text(encoding="utf-8"))
            documents = json.loads((root / "export/documents.json").read_text(encoding="utf-8"))
            value_lists = json.loads((root / "export/value-lists.json").read_text(encoding="utf-8"))
            schema = json.loads(
                (root / "export/full-export-v1.schema.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArtifactError("export_invalid", "Full export JSON is invalid") from error
        return data, documents, value_lists, schema

    def _validate_export_contract(
        self,
        data: object,
        documents: object,
        value_lists: object,
        schema: object,
        manifest: dict[str, Any],
    ) -> None:
        self._validate_export_data_contract(data, manifest)
        if schema != FULL_EXPORT_SCHEMA:
            raise ArtifactError("export_invalid", "Full export contract is invalid")
        self._validate_export_documents_contract(documents)
        self._validate_export_value_lists_contract(value_lists)

    def _validate_export_data_contract(self, data: object, manifest: dict[str, Any]) -> None:
        if (
            not isinstance(data, dict)
            or set(data)
            != {
                "format",
                "format_version",
                "snapshot_at",
                "instance_id",
                "record_count",
                "tables",
            }
            or data.get("format") != "lzug-full-export"
            or data.get("format_version") != 1
            or data.get("snapshot_at") != manifest["snapshot_at"]
            or data.get("instance_id") != manifest["instance_id"]
            or isinstance(data.get("record_count"), bool)
            or not isinstance(data.get("record_count"), int)
            or not isinstance(data.get("tables"), dict)
        ):
            raise ArtifactError("export_invalid", "Full export contract is invalid")

    def _validate_export_documents_contract(self, documents: object) -> None:
        if (
            not isinstance(documents, dict)
            or set(documents) != {"format", "format_version", "documents"}
            or documents.get("format") != "lzug-full-export-documents"
            or documents.get("format_version") != 1
            or not isinstance(documents.get("documents"), list)
        ):
            raise ArtifactError("export_invalid", "Full export contract is invalid")

    def _validate_export_value_lists_contract(self, value_lists: object) -> None:
        if (
            not isinstance(value_lists, dict)
            or set(value_lists) != {"format", "format_version", "lists"}
            or value_lists.get("format") != "lzug-full-export-value-lists"
            or value_lists.get("format_version") != 1
            or not isinstance(value_lists.get("lists"), dict)
        ):
            raise ArtifactError("export_invalid", "Full export contract is invalid")

    def _validate_export_tables(self, data: object, manifest: dict[str, Any]) -> None:
        assert isinstance(data, dict)
        if set(data["tables"]) & _EXCLUDED_EXPORT_TABLES:
            raise ArtifactError("export_secret_detected", "Full export contains excluded tables")
        export_ids: set[str] = set()
        relationships: list[dict[str, Any]] = []
        record_count = 0
        for table_name, table in data["tables"].items():
            record_count += self._validate_export_table(
                table_name, table, export_ids, relationships
            )
        for relationship in relationships:
            self._validate_export_relationship(relationship, export_ids)
        if (
            record_count != data["record_count"]
            or record_count != manifest["counts"]["database_records"]
        ):
            raise ArtifactError("export_invalid", "Full export record count is invalid")

    def _validate_export_table(
        self,
        table_name: object,
        table: object,
        export_ids: set[str],
        relationships: list[dict[str, Any]],
    ) -> int:
        if (
            not isinstance(table_name, str)
            or not isinstance(table, dict)
            or set(table) != {"columns", "rows"}
            or not isinstance(table["columns"], list)
            or not all(isinstance(column, str) for column in table["columns"])
            or len(table["columns"]) != len(set(table["columns"]))
            or not isinstance(table["rows"], list)
        ):
            raise ArtifactError("export_invalid", "Full export table is invalid")
        columns = set(table["columns"])
        if columns & _FORBIDDEN_EXPORT_FIELDS:
            raise ArtifactError("export_secret_detected", "Full export contains secret fields")
        for row in table["rows"]:
            self._validate_export_row(row, table_name, columns, export_ids, relationships)
        return len(table["rows"])

    def _validate_export_row(
        self,
        row: object,
        table_name: str,
        columns: set[str],
        export_ids: set[str],
        relationships: list[dict[str, Any]],
    ) -> None:
        if (
            not isinstance(row, dict)
            or set(row) != {"export_id", "attributes", "relationships"}
            or not isinstance(row["export_id"], str)
            or not row["export_id"].startswith(f"{table_name}:")
            or row["export_id"] in export_ids
            or not isinstance(row["attributes"], dict)
            or set(row["attributes"]) != columns
            or not isinstance(row["relationships"], dict)
        ):
            raise ArtifactError("export_invalid", "Full export row is invalid")
        export_ids.add(row["export_id"])
        for column, relationship in row["relationships"].items():
            if column not in columns or not isinstance(relationship, dict):
                raise ArtifactError("export_invalid", "Full export relation is invalid")
            relationships.append(relationship)

    def _validate_export_relationship(
        self, relationship: dict[str, Any], export_ids: set[str]
    ) -> None:
        if (
            set(relationship) != {"export_id", "target_column"}
            or relationship.get("export_id") not in export_ids
            or not isinstance(relationship.get("target_column"), str)
        ):
            raise ArtifactError("export_invalid", "Full export relation is invalid")

    def _validate_export_documents(
        self,
        root: Path,
        documents: object,
        declared: set[str],
        manifest: dict[str, Any],
    ) -> None:
        assert isinstance(documents, dict)
        document_ids: set[str] = set()
        content_paths: set[str] = set()
        for document in documents["documents"]:
            self._validate_export_document(root, document, declared, document_ids, content_paths)
        if len(documents["documents"]) != manifest["counts"]["documents"]:
            raise ArtifactError("export_invalid", "Full export document count is invalid")

    def _validate_export_document(
        self,
        root: Path,
        document: object,
        declared: set[str],
        document_ids: set[str],
        content_paths: set[str],
    ) -> None:
        if (
            not isinstance(document, dict)
            or set(document)
            != {
                "export_id",
                "source_document_id",
                "content_path",
                "original_filename",
                "media_type",
                "size_bytes",
                "checksum_sha256",
                "relationships",
            }
            or not isinstance(document["export_id"], str)
            or document["export_id"] in document_ids
            or not isinstance(document["content_path"], str)
            or document["content_path"] in content_paths
            or not isinstance(document["size_bytes"], int)
            or isinstance(document["size_bytes"], bool)
            or document["size_bytes"] < 0
            or not isinstance(document["checksum_sha256"], str)
            or _SHA256.fullmatch(document["checksum_sha256"]) is None
            or not isinstance(document["relationships"], list)
        ):
            raise ArtifactError("export_invalid", "Full export document is invalid")
        package_path = "export/" + document["content_path"]
        content = root.joinpath(*PurePosixPath(package_path).parts)
        if (
            package_path not in declared
            or not content.is_file()
            or content.stat().st_size != document["size_bytes"]
            or _sha256(content) != document["checksum_sha256"]
        ):
            raise ArtifactError("export_invalid", "Full export document is invalid")
        document_ids.add(document["export_id"])
        content_paths.add(document["content_path"])

    def _export_data(self, snapshot: CapturedSnapshot) -> tuple[dict[str, Any], dict[str, Any]]:
        tables: dict[str, Any] = {}
        value_lists: dict[str, list[dict[str, str]]] = {}
        record_count = 0
        with closing(_database_connection(snapshot.database)) as connection:
            included = [
                table for table in _table_names(connection) if table not in _EXCLUDED_EXPORT_TABLES
            ]
            for table in included:
                columns = [
                    str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
                ]
                if set(columns) & _FORBIDDEN_EXPORT_FIELDS:
                    raise ArtifactError(
                        "export_secret_detected", "Full export table contains secret fields"
                    )
                foreign_keys = {
                    str(row[3]): (str(row[2]), str(row[4]))
                    for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
                    if str(row[2]) in included
                }
                order = "id" if "id" in columns else "rowid"
                source_rows = connection.execute(
                    f'SELECT * FROM "{table}" ORDER BY "{order}"'
                ).fetchall()
                exported_rows = []
                for index, row in enumerate(source_rows, start=1):
                    values = dict(row)
                    identifier = values.get("id", index)
                    relationships = {
                        column: {
                            "export_id": f"{target_table}:{values[column]}",
                            "target_column": target_column,
                        }
                        for column, (target_table, target_column) in foreign_keys.items()
                        if values.get(column) is not None
                    }
                    exported_rows.append(
                        {
                            "export_id": f"{table}:{identifier}",
                            "attributes": values,
                            "relationships": relationships,
                        }
                    )
                record_count += len(exported_rows)
                tables[table] = {"columns": columns, "rows": exported_rows}
                for column in columns:
                    if not any(
                        marker in column
                        for marker in ("status", "type", "kind", "role", "season", "action")
                    ):
                        continue
                    values = sorted(
                        {str(row[column]) for row in source_rows if row[column] is not None}
                    )
                    if values:
                        value_lists[f"{table}.{column}"] = [
                            {"code": value, "meaning": f"Code value {value} for {table}.{column}"}
                            for value in values
                        ]
        return (
            {
                "format": "lzug-full-export",
                "format_version": 1,
                "snapshot_at": snapshot.snapshot_at,
                "instance_id": snapshot.instance_id,
                "record_count": record_count,
                "tables": tables,
            },
            {
                "format": "lzug-full-export-value-lists",
                "format_version": 1,
                "lists": value_lists,
            },
        )

    @contextmanager
    def _prepared_restore(
        self, loaded: LoadedArtifact
    ) -> Iterator[tuple[Path, Path, Path, list[str], dict[str, int]]]:
        root = Path(tempfile.mkdtemp(prefix=".lzug-restore-", dir=self.paths.data_dir))
        os.chmod(root, 0o700)
        try:
            database = root / "lzug.sqlite"
            documents = root / "documents"
            key = root / ".lzug-auth.key"
            shutil.copy2(loaded.root / DATABASE_NAME, database)
            shutil.copytree(loaded.root / "payload/documents", documents)
            shutil.copy2(loaded.root / KEY_NAME, key)
            os.chmod(key, 0o600)
            source_schema, migrations = _schema_compatibility(database)
            if source_schema != loaded.manifest["schema_version"]:
                raise ArtifactError("manifest_invalid", "Manifest schema version is invalid")
            if migrations:
                try:
                    apply_migrations(database, root / "migration-backups")
                except Exception as error:
                    raise ArtifactError(
                        "migration_failed", "Prepared restore migration failed", phase="migration"
                    ) from error
            with closing(_database_connection(database, read_only=False)) as connection:
                connection.execute(
                    "UPDATE instance_metadata SET instance_id = ? WHERE id = 1",
                    (loaded.manifest["instance_id"],),
                )
                reset = {
                    "sessions": connection.execute("DELETE FROM auth_session").rowcount,
                    "invitations": connection.execute(
                        "DELETE FROM auth_token WHERE kind = 'invitation' AND consumed_at IS NULL"
                    ).rowcount,
                    "recovery_operations": connection.execute(
                        "DELETE FROM auth_token WHERE kind = 'recovery' AND consumed_at IS NULL"
                    ).rowcount,
                    "recovery_codes": connection.execute("DELETE FROM auth_recovery_code").rowcount,
                    "technical_claims": connection.execute(
                        "UPDATE notification_delivery SET claim_token = NULL, claimed_at = NULL, "
                        "claim_expires_at = NULL WHERE claim_token IS NOT NULL"
                    ).rowcount,
                }
                now = _timestamp()
                for task_table, reopening_table in (
                    ("exam_day_task", "exam_day_reopening"),
                    ("exam_round_task", "exam_round_reopening"),
                ):
                    connection.execute(
                        f"UPDATE \"{task_table}\" SET status = 'completed', completed_at = ? "
                        f"WHERE status = 'open' AND reopening_id IN "
                        f"(SELECT id FROM \"{reopening_table}\" WHERE status != 'open')",
                        (now,),
                    )
                connection.commit()
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            Path(f"{database}-wal").unlink(missing_ok=True)
            Path(f"{database}-shm").unlink(missing_ok=True)
            yield database, documents, key, migrations, reset
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _verify_prepared(
        self,
        database: Path,
        documents: Path,
        key: Path,
        manifest: dict[str, Any],
    ) -> None:
        _database_integrity(database)
        _validate_document_snapshot(database, documents)
        _validate_totp_secrets(database, key.read_bytes())
        if _instance_id(database) != manifest["instance_id"]:
            raise ArtifactError("postcheck_failed", "Restored instance identity is invalid")
        schema, pending = _schema_compatibility(database)
        if pending or schema != _available_migrations()[-1]:
            raise ArtifactError("postcheck_failed", "Restored schema is not current")
        readiness = database_readiness(database)
        if not readiness["ready"]:
            raise ArtifactError("postcheck_failed", "Restored database is not ready")

    def _activate_restore(
        self,
        database: Path,
        documents: Path,
        key: Path,
        manifest: dict[str, Any],
    ) -> None:
        retired = Path(tempfile.mkdtemp(prefix=".lzug-retired-", dir=self.paths.data_dir))
        os.chmod(retired, 0o700)
        target_key = authentication_key_path(self.paths.database)
        moved: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        try:
            self._checkpoint_target_database()
            self._retire_restore_targets(retired, target_key, moved)
            self._install_prepared_restore(database, documents, key, target_key, installed)
            self._validate_activated_restore(target_key, manifest)
            self._fault("activation")
        except Exception as error:
            self._rollback_restore_activation(installed, moved)
            if isinstance(error, ArtifactError):
                raise
            raise ArtifactError(
                "activation_failed", "Restore activation failed", phase="activation"
            ) from error
        finally:
            shutil.rmtree(retired, ignore_errors=True)

    def _checkpoint_target_database(self) -> None:
        if not self.paths.database.exists():
            return
        with closing(_database_connection(self.paths.database, read_only=False)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _retire_restore_targets(
        self, retired: Path, target_key: Path, moved: list[tuple[Path, Path]]
    ) -> None:
        for target in (
            self.paths.database,
            Path(f"{self.paths.database}-wal"),
            Path(f"{self.paths.database}-shm"),
            self.paths.documents,
            target_key,
        ):
            if target.exists():
                destination = retired / target.name
                os.replace(target, destination)
                moved.append((destination, target))

    def _install_prepared_restore(
        self, database: Path, documents: Path, key: Path, target_key: Path, installed: list[Path]
    ) -> None:
        destinations = (
            (database, self.paths.database),
            (documents, self.paths.documents),
            (key, target_key),
        )
        for source, target in destinations:
            os.replace(source, target)
            installed.append(target)

    def _validate_activated_restore(self, target_key: Path, manifest: dict[str, Any]) -> None:
        _database_integrity(self.paths.database)
        _validate_document_snapshot(self.paths.database, self.paths.documents)
        _validate_totp_secrets(self.paths.database, target_key.read_bytes())
        if _instance_id(self.paths.database) != manifest["instance_id"]:
            raise ArtifactError(
                "activation_failed",
                "Activated instance identity is invalid",
                phase="activation",
            )

    def _rollback_restore_activation(
        self, installed: list[Path], moved: list[tuple[Path, Path]]
    ) -> None:
        for target in reversed(installed):
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        for source, target in reversed(moved):
            if source.exists():
                os.replace(source, target)

    def _target_is_empty(self) -> bool:
        if any(self.paths.documents.iterdir()):
            return False
        if not self.paths.database.exists() or self.paths.database.stat().st_size == 0:
            return True
        try:
            with closing(_database_connection(self.paths.database)) as connection:
                excluded = {
                    "artifact_operation",
                    "exam_venue_migration_report",
                    "instance_metadata",
                    "schema_migration",
                    "schema_migration_checksum",
                }
                for table in _table_names(connection):
                    if (
                        table not in excluded
                        and connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()
                    ):
                        return False
                return True
        except sqlite3.Error as error:
            raise ArtifactError(
                "target_invalid", "Existing target cannot be inspected safely"
            ) from error

    def _configuration_manifest(self) -> dict[str, Any]:
        required_names = [
            value.strip()
            for value in self.environment.get(REQUIRED_CONFIG_ENV, "").split(",")
            if value.strip()
        ]
        if any(_ENV_NAME.fullmatch(name) is None for name in required_names):
            raise ArtifactError("configuration_invalid", "Required configuration list is invalid")
        dependencies = [
            {
                "name": name,
                "kind": "external_runtime_configuration",
                "required": True,
                "configured": bool(self.environment.get(name)),
            }
            for name in sorted(set(required_names))
        ]
        for name, variable in (
            ("base_url", "LZUG_EXTERNAL_URL"),
            ("email", "LZUG_SMTP_HOST"),
            ("web_push", "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY"),
        ):
            dependencies.append(
                {
                    "name": name,
                    "kind": "optional_channel",
                    "required": False,
                    "configured": bool(self.environment.get(variable)),
                }
            )
        effective = {}
        for name in ("LZUG_EXTERNAL_URL", "LZUG_TIMEZONE", "LZUG_CALENDAR_TIMEZONE"):
            value = self.environment.get(name)
            effective[name] = (
                "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None
            )
        return {"dependencies": dependencies, "effective_settings": effective}

    def _configuration_report(self, manifest: dict[str, Any]) -> dict[str, Any]:
        source = manifest.get("operator_configuration")
        if not isinstance(source, dict) or not isinstance(source.get("dependencies"), list):
            raise ArtifactError("manifest_invalid", "Operator configuration manifest is invalid")
        missing_required = []
        restricted_channels = []
        required_current = {
            value.strip()
            for value in self.environment.get(REQUIRED_CONFIG_ENV, "").split(",")
            if value.strip()
        }
        optional_variables = {
            "base_url": "LZUG_EXTERNAL_URL",
            "email": "LZUG_SMTP_HOST",
            "web_push": "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY",
        }
        for dependency in source["dependencies"]:
            if not isinstance(dependency, dict):
                raise ArtifactError("manifest_invalid", "Operator dependency is invalid")
            name = dependency.get("name")
            if dependency.get("required"):
                if name not in required_current or not self.environment.get(str(name)):
                    missing_required.append(str(name))
            elif dependency.get("configured") and not self.environment.get(
                optional_variables.get(str(name), "")
            ):
                restricted_channels.append(str(name))
        changed_settings = []
        target = self._configuration_manifest()["effective_settings"]
        for name, fingerprint in source.get("effective_settings", {}).items():
            if fingerprint != target.get(name):
                changed_settings.append(name)
        readiness = (
            "not_ready" if missing_required else "restricted" if restricted_channels else "ready"
        )
        return {
            "missing_required": sorted(missing_required),
            "restricted_channels": sorted(restricted_channels),
            "changed_settings": sorted(changed_settings),
            "readiness": readiness,
        }

    def _record_operation(
        self,
        operation_type: str,
        *,
        result: dict[str, Any] | None = None,
        error: ArtifactError | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        if not self.paths.database.exists():
            return
        artifact_id = result.get("artifact_id") if result else None
        artifact_type = result.get("artifact_type") if result else None
        snapshot_at = result.get("snapshot_at") if result else None
        fingerprint = result.get("recipient_key_fingerprint") if result else None
        if manifest is not None:
            artifact_id = artifact_id or manifest.get("artifact_id")
            artifact_type = artifact_type or manifest.get("artifact_type")
            snapshot_at = snapshot_at or manifest.get("snapshot_at")
        try:
            with mutation_scope(self.paths.database):
                with closing(
                    _database_connection(self.paths.database, read_only=False)
                ) as connection:
                    tables = set(_table_names(connection))
                    if "artifact_operation" not in tables:
                        return
                    connection.execute(
                        "INSERT INTO artifact_operation "
                        "(operation_type, artifact_id, artifact_type, snapshot_at, "
                        "recipient_key_fingerprint, result, error_code) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation_type,
                            artifact_id,
                            artifact_type,
                            snapshot_at,
                            fingerprint,
                            "failed" if error else "succeeded",
                            error.code if error else None,
                        ),
                    )
                    connection.commit()
        except sqlite3.Error:
            return

    def _artifact_path(self, artifact_name: str) -> Path:
        if not isinstance(artifact_name, str) or _ARTIFACT_NAME.fullmatch(artifact_name) is None:
            raise ArtifactError("artifact_name_invalid", "Artifact name is invalid")
        artifact = self.paths.backups / artifact_name
        if artifact.is_symlink() or not artifact.is_file():
            raise ArtifactError("artifact_not_found", "Artifact does not exist")
        return artifact

    def _ensure_runtime_paths(self) -> None:
        for directory in (self.paths.data_dir, self.paths.documents, self.paths.backups):
            if directory.exists() and directory.is_symlink():
                raise ArtifactError("persistence_error", "Persistent directory is invalid")
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise ArtifactError("persistence_error", "Persistent path is invalid")

    @staticmethod
    def _ensure_space(directory: Path, required_bytes: int) -> None:
        try:
            available = shutil.disk_usage(directory).free
        except OSError as error:
            raise ArtifactError("persistence_error", "Free storage could not be checked") from error
        if available < required_bytes:
            raise ArtifactError("insufficient_storage", "Insufficient target storage")

    def _fault(self, phase: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(phase)
