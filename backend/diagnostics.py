"""Secret-free local diagnostics for the versioned operator contract."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .database import (
    DEFAULT_MIN_FREE_BYTES,
    PersistencePaths,
    database_readiness,
    persistence_paths,
)
from .documents import document_upload_policy
from .healthcheck import public_health_ready
from .map_provider import MapProviderConfig
from .notifications import NotificationError, NotificationService
from .security import RuntimeSecurityConfig
from .version import build_metadata

EXIT_DIAGNOSTIC_WARNING = 30
EXIT_DIAGNOSTIC_ERROR = 31

_STATUS_RANK = {"ok": 0, "warning": 1, "error": 2}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _check(
    check_id: str,
    status: str,
    code: str,
    message: str,
    *,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": check_id,
        "status": status,
        "code": code,
        "message": message,
    }
    if details is not None:
        result["details"] = dict(details)
    return result


def _summary(command: str, checks: list[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    status = max((str(item["status"]) for item in checks), key=_STATUS_RANK.__getitem__)
    exit_code = {
        "ok": 0,
        "warning": EXIT_DIAGNOSTIC_WARNING,
        "error": EXIT_DIAGNOSTIC_ERROR,
    }[status]
    return {"command": command, "status": status, "checks": checks}, exit_code


def _runtime_check(client: Mapping[str, str]) -> dict[str, Any]:
    try:
        runtime = build_metadata()
    except OSError, RuntimeError, subprocess.SubprocessError, ValueError:
        return _check(
            "runtime",
            "error",
            "runtime_unavailable",
            "Runtime metadata is unavailable or invalid",
        )

    details = {
        "runtime_identity": runtime.identity,
        "runtime_revision": runtime.revision,
        "client_identity": client["identity"],
        "client_revision": client["revision"],
    }
    if client["revision"] == "unknown" or client["identity"] == "development":
        return _check(
            "runtime",
            "warning",
            "runtime_unverified",
            "CLI and runtime compatibility cannot be verified for a development build",
            details=details,
        )
    if client["identity"] != runtime.identity or client["revision"] != runtime.revision:
        return _check(
            "runtime",
            "warning",
            "runtime_mismatch",
            "CLI and container runtime were built from different identities",
            details=details,
        )
    return _check(
        "runtime",
        "ok",
        "runtime_compatible",
        "CLI and container runtime identities match",
        details=details,
    )


def _persistence_configuration() -> tuple[dict[str, Any], PersistencePaths | None]:
    try:
        paths = persistence_paths()
    except ValueError as error:
        return (
            _check(
                "persistence_configuration",
                "error",
                "configuration_invalid",
                str(error),
            ),
            None,
        )
    return (
        _check(
            "persistence_configuration",
            "ok",
            "configuration_valid",
            "Persistent storage configuration is valid",
        ),
        paths,
    )


def _bounded_port(environment: Mapping[str, str], name: str, default: int) -> int:
    raw_value = environment.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def _boolean(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    if raw_value.strip().lower() in {"1", "true"}:
        return True
    if raw_value.strip().lower() in {"0", "false"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _exact_http_origin(value: str, name: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{name} must be an exact HTTP origin") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is None
        and ":" in parsed.netloc.rsplit("]", 1)[-1]
    ):
        raise ValueError(f"{name} must be an exact HTTP origin")


def _loopback_health_url(environment: Mapping[str, str]) -> str:
    health_url = environment.get("LZUG_HEALTHCHECK_URL", "http://127.0.0.1:8000/api/health")
    try:
        parsed_health = urlsplit(health_url)
        _health_port = parsed_health.port
    except ValueError as error:
        raise ValueError("LZUG_HEALTHCHECK_URL must use loopback HTTP and /api/health") from error
    if (
        parsed_health.scheme != "http"
        or parsed_health.hostname not in _LOOPBACK_HOSTS
        or parsed_health.username is not None
        or parsed_health.password is not None
        or parsed_health.path != "/api/health"
        or parsed_health.query
        or parsed_health.fragment
    ):
        raise ValueError("LZUG_HEALTHCHECK_URL must use loopback HTTP and /api/health")
    return health_url


def _http_configuration(environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        RuntimeSecurityConfig.from_environment(environment)
        _bounded_port(environment, "LZUG_PORT", 8000)
        if not environment.get("LZUG_HOST", "127.0.0.1").strip():
            raise ValueError("LZUG_HOST must not be empty")
        static_dir = environment.get("LZUG_STATIC_DIR")
        if static_dir and not (Path(static_dir).expanduser() / "index.html").is_file():
            raise ValueError("LZUG_STATIC_DIR must contain index.html")
        _loopback_health_url(environment)
    except ValueError as error:
        return _check(
            "http_configuration",
            "error",
            "configuration_invalid",
            str(error),
        )
    return _check(
        "http_configuration",
        "ok",
        "configuration_valid",
        "HTTP and security configuration is valid",
    )


def _document_configuration(environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        document_upload_policy(environment)
    except ValueError as error:
        return _check(
            "document_configuration",
            "error",
            "configuration_invalid",
            str(error),
        )
    return _check(
        "document_configuration",
        "ok",
        "configuration_valid",
        "Document upload configuration is valid",
    )


def _notification_configuration(environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        _bounded_port(environment, "LZUG_SMTP_PORT", 25)
        _boolean(environment, "LZUG_SMTP_STARTTLS", False)
        sink = environment.get("LZUG_NOTIFICATION_SINK", "").strip().lower()
        if sink not in {"", "0", "1", "false", "true", "operator"}:
            raise ValueError("LZUG_NOTIFICATION_SINK must be true, false, or operator")
        external_url = environment.get("LZUG_EXTERNAL_URL", "").strip()
        if external_url:
            _exact_http_origin(external_url, "LZUG_EXTERNAL_URL")
        private_key_configured = bool(
            environment.get("LZUG_WEB_PUSH_VAPID_PRIVATE_KEY", "").strip()
        )
        subject_configured = bool(environment.get("LZUG_WEB_PUSH_SUBJECT", "").strip())
        if private_key_configured != subject_configured:
            raise ValueError(
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY and LZUG_WEB_PUSH_SUBJECT must be set together"
            )
        NotificationService().channels()
    except (NotificationError, ValueError) as error:
        return _check(
            "notification_configuration",
            "error",
            "configuration_invalid",
            str(error),
        )
    return _check(
        "notification_configuration",
        "ok",
        "configuration_valid",
        "Notification configuration is valid",
    )


def _map_provider_configuration(environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        provider = MapProviderConfig.from_environment(dict(environment))
    except ValueError as error:
        return _check(
            "map_provider_configuration",
            "error",
            "configuration_invalid",
            str(error),
        )
    return _check(
        "map_provider_configuration",
        "ok",
        "configuration_valid",
        "Map provider configuration is valid",
        details={"mode": provider.mode},
    )


def _configuration_checks() -> tuple[list[dict[str, Any]], PersistencePaths | None]:
    persistence, paths = _persistence_configuration()
    environment = os.environ
    return (
        [
            persistence,
            _http_configuration(environment),
            _document_configuration(environment),
            _notification_configuration(environment),
            _map_provider_configuration(environment),
        ],
        paths,
    )


def _schema_check(paths: PersistencePaths | None) -> dict[str, Any]:
    if paths is None:
        return _check(
            "schema",
            "error",
            "configuration_invalid",
            "Schema compatibility cannot be checked with invalid storage configuration",
        )
    readiness = database_readiness(paths.database)
    migration = readiness.get("migration")
    details: dict[str, Any] = {"state": str(readiness.get("reason", "unknown"))}
    if isinstance(migration, Mapping):
        details["current"] = migration.get("current")
        details["target"] = migration.get("target")
    if readiness.get("ready") is True:
        return _check(
            "schema",
            "ok",
            "schema_compatible",
            "Database schema is compatible with this runtime",
            details=details,
        )
    if readiness.get("reason") == "migration_required":
        return _check(
            "schema",
            "warning",
            "schema_migration_required",
            "Database schema requires supported migrations",
            details=details,
        )
    return _check(
        "schema",
        "error",
        "schema_incompatible",
        "Database schema is unavailable or incompatible",
        details=details,
    )


def _probe_directory(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".lzug-doctor-") as probe:
            probe.write(b"lzug")
            probe.flush()
            os.fsync(probe.fileno())
    except OSError:
        return False
    return True


def _permissions_check(paths: PersistencePaths | None) -> dict[str, Any]:
    if paths is None:
        return _check(
            "data_permissions",
            "error",
            "configuration_invalid",
            "Persistent storage rights cannot be checked with invalid configuration",
        )
    scopes = {
        "data": paths.data_dir,
        "documents": paths.documents,
        "backups": paths.backups,
        "database_parent": paths.database.parent,
    }
    for scope, path in scopes.items():
        if not _probe_directory(path):
            return _check(
                "data_permissions",
                "error",
                "data_not_writable",
                "A required persistent directory is not writable",
                details={"scope": scope},
            )
    database_writable = paths.database.is_file() and not paths.database.is_symlink()
    if database_writable:
        try:
            descriptor = os.open(paths.database, os.O_WRONLY | os.O_APPEND)
        except OSError:
            database_writable = False
        else:
            os.close(descriptor)
    if not database_writable:
        return _check(
            "data_permissions",
            "error",
            "database_not_writable",
            "The persistent database file is not readable and writable",
            details={"scope": "database"},
        )
    return _check(
        "data_permissions",
        "ok",
        "data_writable",
        "Persistent storage is readable and writable",
    )


def _free_space_check(paths: PersistencePaths | None) -> dict[str, Any]:
    if paths is None:
        return _check(
            "free_space",
            "error",
            "configuration_invalid",
            "Free space cannot be checked with invalid storage configuration",
        )
    available: list[int] = []
    checked: set[Path] = set()
    try:
        for directory in (*paths.directories, paths.database.parent):
            resolved = directory.resolve()
            if resolved in checked:
                continue
            checked.add(resolved)
            available.append(shutil.disk_usage(directory).free)
    except OSError:
        return _check(
            "free_space",
            "error",
            "free_space_unavailable",
            "Free space cannot be determined for persistent storage",
        )
    minimum_available = min(available)
    details = {
        "available_bytes": minimum_available,
        "minimum_bytes": DEFAULT_MIN_FREE_BYTES,
    }
    if minimum_available < DEFAULT_MIN_FREE_BYTES:
        return _check(
            "free_space",
            "warning",
            "free_space_low",
            "Persistent storage has less free space than recommended",
            details=details,
        )
    return _check(
        "free_space",
        "ok",
        "free_space_sufficient",
        "Persistent storage has sufficient free space",
        details=details,
    )


def _health_check() -> dict[str, Any]:
    try:
        health_url = _loopback_health_url(os.environ)
    except ValueError as error:
        return _check(
            "health",
            "error",
            "configuration_invalid",
            str(error),
        )
    if public_health_ready(health_url):
        return _check(
            "health",
            "ok",
            "health_available",
            "The public health endpoint reports a live runtime",
        )
    return _check(
        "health",
        "error",
        "health_unavailable",
        "The public health endpoint is unavailable or invalid",
    )


def run_diagnostics(
    command: str,
    client: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    """Run one allowlisted diagnostic command and return payload plus exit code."""
    if command == "config":
        checks, _paths = _configuration_checks()
        return _summary(command, checks)
    if command not in {"status", "doctor"} or client is None:
        raise ValueError("Unsupported diagnostic command")

    if command == "status":
        _persistence, paths = _persistence_configuration()
        checks = [_runtime_check(client), _schema_check(paths), _health_check()]
    else:
        configuration, paths = _configuration_checks()
        checks = [
            _runtime_check(client),
            *configuration,
            _schema_check(paths),
            _permissions_check(paths),
            _free_space_check(paths),
            _health_check(),
        ]
    return _summary(command, checks)
