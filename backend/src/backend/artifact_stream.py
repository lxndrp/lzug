"""Versioned binary stream transport between lzug-admin and the backend."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from .admin import _EXIT_CODES, EXIT_INTERNAL, EXIT_OK, MAX_REQUEST_BYTES, _response
from .artifact_packages import ClearArtifactService
from .backup_restore import ArtifactError
from .database import persistence_paths

STREAM_PROTOCOL_VERSION = 2
STREAM_CHUNK_BYTES = 1024 * 1024


def _read_request(source: BinaryIO) -> tuple[str, Mapping[str, object]]:
    line = source.readline(MAX_REQUEST_BYTES + 1)
    if len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
        raise ArtifactError("invalid_request", "Stream request is invalid")
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("invalid_request", "Stream request is invalid") from error
    if not isinstance(value, dict) or value.get("version") != STREAM_PROTOCOL_VERSION:
        raise ArtifactError("invalid_request", "Stream protocol is incompatible")
    command = value.get("command")
    arguments = value.get("arguments", {})
    if not isinstance(command, str) or not isinstance(arguments, dict):
        raise ArtifactError("invalid_request", "Stream request is invalid")
    return command, arguments


def _required_string(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ArtifactError("invalid_request", f"Argument {name} is required")
    return value


def _write_control(
    stream: BinaryIO, *, result: object = None, error: ArtifactError | None = None
) -> None:
    if error is None:
        stream.write(_response(ok=True, result=result))
    else:
        stream.write(
            _response(
                ok=False,
                error={"class": error.code, "message": str(error), "phase": error.phase},
            )
        )
    stream.flush()


def _produce(command: str, arguments: Mapping[str, object], output: BinaryIO) -> dict[str, object]:
    service = ClearArtifactService(persistence_paths())
    fingerprint = _required_string(arguments, "recipient_key_fingerprint")
    factory = (
        service.write_backup_package
        if command == "backup-package-create"
        else service.write_export_package
    )
    result = factory(output, fingerprint)
    output.flush()
    return result


def _consume(
    command: str,
    arguments: Mapping[str, object],
    source: BinaryIO,
) -> dict[str, object]:
    paths = persistence_paths()
    paths.backups.mkdir(parents=True, exist_ok=True)
    descriptor, value = tempfile.mkstemp(
        prefix=".lzug-incoming-package-", suffix=".zip", dir=paths.backups
    )
    os.close(descriptor)
    package = Path(value)
    os.chmod(package, 0o600)
    try:
        with package.open("wb") as target:
            shutil.copyfileobj(source, target, STREAM_CHUNK_BYTES)
            target.flush()
            os.fsync(target.fileno())
        service = ClearArtifactService(paths)
        if command == "artifact-package-verify":
            expected = arguments.get("artifact_type")
            if expected is not None and expected not in {"backup", "full_export"}:
                raise ArtifactError("invalid_request", "Artifact type is invalid")
            return service.verify_package(package, expected_type=expected)
        if command == "backup-package-restore":
            replace = arguments.get("replace", False)
            if not isinstance(replace, bool):
                raise ArtifactError("invalid_request", "Argument replace must be boolean")
            safety = arguments.get("safety_artifact")
            if safety is not None and not isinstance(safety, str):
                raise ArtifactError("invalid_request", "Safety artifact is invalid")
            return service.restore_package(
                package,
                replace=replace,
                safety_artifact=safety,
                recipient_fingerprint=_required_string(arguments, "recipient_key_fingerprint"),
            )
        raise ArtifactError("invalid_request", "Unsupported stream command")
    finally:
        package.unlink(missing_ok=True)


def run(mode: str, source: BinaryIO, output: BinaryIO, control: BinaryIO) -> int:
    try:
        command, arguments = _read_request(source)
        if mode == "produce":
            if command not in {"backup-package-create", "export-package-create"}:
                raise ArtifactError("invalid_request", "Unsupported stream command")
            result = _produce(command, arguments, output)
            _write_control(control, result=result)
        else:
            result = _consume(command, arguments, source)
            _write_control(control, result=result)
        return EXIT_OK
    except ArtifactError as error:
        _write_control(control, error=error)
        return _EXIT_CODES.get(error.code, EXIT_INTERNAL)
    except Exception:
        error = ArtifactError("internal_error", "Artifact stream operation failed")
        _write_control(control, error=error)
        return EXIT_INTERNAL


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--protocol", type=int, required=True)
    parser.add_argument("mode", choices=("produce", "consume"))
    options = parser.parse_args()
    if options.protocol != STREAM_PROTOCOL_VERSION:
        error = ArtifactError("invalid_request", "Stream protocol is incompatible")
        control = sys.stderr.buffer if options.mode == "produce" else sys.stdout.buffer
        _write_control(control, error=error)
        return _EXIT_CODES["invalid_request"]
    control = sys.stderr.buffer if options.mode == "produce" else sys.stdout.buffer
    return run(options.mode, sys.stdin.buffer, sys.stdout.buffer, control)


if __name__ == "__main__":
    raise SystemExit(main())
