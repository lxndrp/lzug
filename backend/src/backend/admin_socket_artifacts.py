"""One bounded artifact exchange on the already authenticated admin connection."""

from __future__ import annotations

import hashlib
import os
import re
import socket
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.admin_socket_protocol import (
    MAX_DATA_BYTES,
    SocketProtocolError,
    read_stream_frame,
    remaining,
    write_data,
    write_frame,
)
from backend.application.admin import _EXIT_CODES, EXIT_INTERNAL, AdminApplication
from backend.operations.artifact_packages import ClearArtifactService
from backend.operations.backup_restore import ArtifactError
from backend.operations.lifecycle import LifecycleError
from backend.runtime import RuntimeConflictError

PRODUCE_COMMANDS = {"backup-package-create", "export-package-create"}
CONSUME_COMMANDS = {"artifact-package-verify", "backup-package-restore", "upgrade-package-apply"}
STREAM_COMMANDS = PRODUCE_COMMANDS | CONSUME_COMMANDS


def validate_request(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Allow only public metadata; identity values and arbitrary claims are rejected."""
    if (
        set(request) != {"version", "command", "arguments"}
        or type(request["version"]) is not int
        or request["version"] != 1
        or request["command"] not in STREAM_COMMANDS
        or not isinstance(request["arguments"], dict)
    ):
        raise SocketProtocolError("validation", "request_invalid")
    command, arguments = request["command"], request["arguments"]
    fields = {"recipient_key_fingerprint"}
    if command == "artifact-package-verify":
        fields = {"artifact_type"}
        if not isinstance(arguments.get("artifact_type"), str) or arguments[
            "artifact_type"
        ] not in {"backup", "full_export"}:
            raise SocketProtocolError("validation", "request_invalid")
    else:
        fingerprint = arguments.get("recipient_key_fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", fingerprint
        ):
            raise SocketProtocolError("validation", "request_invalid")
    if command == "backup-package-restore":
        fields |= {"replace", "safety_artifact"}
        safety = arguments.get("safety_artifact")
        if type(arguments.get("replace")) is not bool or (
            safety is not None and (not isinstance(safety, str) or not 0 < len(safety) <= 4096)
        ):
            raise SocketProtocolError("validation", "request_invalid")
    if command == "upgrade-package-apply":
        fields |= {"plan_id", "confirm_irreversible"}
        if (
            not isinstance(arguments.get("plan_id"), str)
            or re.fullmatch(r"[0-9a-f]{64}", arguments["plan_id"]) is None
            or type(arguments.get("confirm_irreversible")) is not bool
        ):
            raise SocketProtocolError("validation", "request_invalid")
    if set(arguments) != fields:
        raise SocketProtocolError("validation", "request_invalid")
    return command, arguments


class StreamWriter:
    """A non-seekable ZIP target with one frame in memory and no pending queue."""

    def __init__(self, connection: socket.socket, deadline: float, limit: int) -> None:
        self.connection, self.deadline, self.limit = connection, deadline, limit
        self.count = 0
        self.digest = hashlib.sha256()

    def write(self, payload: bytes) -> int:
        if len(payload) > self.limit - self.count:
            raise SocketProtocolError("transfer", "stream_limit_exceeded")
        for offset in range(0, len(payload), MAX_DATA_BYTES):
            chunk = payload[offset : offset + MAX_DATA_BYTES]
            write_data(self.connection, chunk, self.deadline)
            self.digest.update(chunk)
            self.count += len(chunk)
        return len(payload)

    def flush(self) -> None:
        remaining(self.connection, self.deadline)

    def end(self) -> None:
        write_frame(self.connection, self.summary(), self.deadline)

    def summary(self) -> dict[str, Any]:
        return {"type": "stream-end", "bytes": self.count, "sha256": self.digest.hexdigest()}


def receive_package(connection: socket.socket, target, deadline: float, limit: int) -> None:
    """Require a matching terminator and write-half closure before any execution.

    EOF alone is never success. The CLI sends the terminator only after its age
    reader has authenticated EOF; a failed integrity read closes without it.
    """
    count, digest = 0, hashlib.sha256()
    while True:
        frame = read_stream_frame(connection, deadline)
        if isinstance(frame, bytes):
            if len(frame) > limit - count:
                raise SocketProtocolError("transfer", "stream_limit_exceeded")
            target.write(frame)
            digest.update(frame)
            count += len(frame)
            continue
        if (
            set(frame) != {"type", "bytes", "sha256"}
            or frame["type"] != "stream-end"
            or type(frame["bytes"]) is not int
            or frame["bytes"] != count
            or frame["sha256"] != digest.hexdigest()
            or count == 0
        ):
            raise SocketProtocolError("transfer", "stream_incomplete")
        remaining(connection, deadline)
        if connection.recv(1):
            raise SocketProtocolError("transfer", "stream_frame_invalid")
        target.flush()
        os.fsync(target.fileno())
        remaining(connection, deadline)
        return


class SocketArtifacts:
    """Reuse package services in the authoritative process, with bounded staging."""

    def __init__(self, application: AdminApplication, limit: int) -> None:
        self.application, self.limit = application, limit
        self.lifecycle = application.services.lifecycle_factory(application.paths)

    @contextmanager
    def _incoming(self, service: ClearArtifactService):
        root = Path(tempfile.mkdtemp(prefix=".lzug-socket-", dir=self.application.paths.backups))
        try:
            yield root
        finally:
            if root.exists():
                service._cleanup_workspace(root)

    def execute(
        self,
        connection: socket.socket,
        request: dict[str, Any],
        deadline: float,
        job: dict[str, Any],
        record: Callable[..., None],
    ) -> tuple[dict[str, Any], int]:
        command, arguments = validate_request(request)
        runtime = self.application.runtime
        assert runtime is not None
        configured = self.application.services.artifact_factory(self.application.paths)
        service = ClearArtifactService(
            self.application.paths,
            environment=configured.environment,
            settings=configured.settings,
            package_limit=self.limit,
        )
        try:
            if command in PRODUCE_COMMANDS:
                admission = (
                    runtime.inspect_storage()
                    if command == "backup-package-create"
                    else runtime.admit()
                )
                with admission:
                    migration_backup = runtime.snapshot()["state"] == "migration_required"
                    if migration_backup:
                        self.lifecycle._plan()
                        if (
                            self.lifecycle.recipient()["fingerprint"]
                            != arguments["recipient_key_fingerprint"]
                        ):
                            raise LifecycleError(
                                "recipient_key_mismatch", "Backup recipient does not match"
                            )
                    self._ready(connection, deadline, job, "download")
                    record(job, phase="download")
                    output = StreamWriter(connection, deadline, self.limit)
                    produce = (
                        service.write_backup_package
                        if command == "backup-package-create"
                        else service.write_export_package
                    )
                    result = produce(output, arguments["recipient_key_fingerprint"])
                    output.end()
                    if migration_backup:
                        self.lifecycle.backup_created(
                            output.digest.hexdigest(), arguments["recipient_key_fingerprint"]
                        )
            else:
                # Uploads do not hold a maintenance lease while waiting on a peer.
                # Restore obtains exclusive runtime admission after verified EOF.
                if runtime.snapshot()["state"] not in {
                    "ready",
                    "migration_required",
                } and command not in {"backup-package-restore", "upgrade-package-apply"}:
                    raise RuntimeConflictError()
                self.application.paths.backups.mkdir(parents=True, exist_ok=True)
                with self._incoming(service) as directory:
                    package = directory / "incoming.zip"
                    with package.open("xb") as target:
                        package.chmod(0o600)
                        self._ready(connection, deadline, job, "upload")
                        record(job, phase="upload")
                        receive_package(connection, target, deadline, self.limit)
                    record(job, phase="execution")
                    if command == "artifact-package-verify":
                        with runtime.inspect_storage():
                            result = service.verify_package(
                                package, expected_type=arguments["artifact_type"]
                            )
                    elif command == "upgrade-package-apply":
                        result = self.lifecycle.apply_package(
                            package,
                            service,
                            plan_id=arguments["plan_id"],
                            fingerprint=arguments["recipient_key_fingerprint"],
                            confirm_irreversible=arguments["confirm_irreversible"],
                            job_id=job["job_id"],
                            release_package=lambda: service._cleanup_workspace(directory),
                        )
                    else:
                        result = service.restore_package(
                            package,
                            replace=arguments["replace"],
                            safety_artifact=arguments["safety_artifact"],
                            recipient_fingerprint=arguments["recipient_key_fingerprint"],
                        )
            return {"version": 1, "ok": True, "result": result}, 0
        except RuntimeConflictError:
            raise SocketProtocolError("lifecycle", "lifecycle_conflict") from None
        except (ArtifactError, LifecycleError) as error:
            return {
                "version": 1,
                "ok": False,
                "error": {
                    "class": error.code,
                    "message": "Artifact operation failed",
                    "phase": error.phase,
                    **(
                        {"details": error.details}
                        if isinstance(error, LifecycleError) and error.details
                        else {}
                    ),
                },
            }, _EXIT_CODES.get(error.code, EXIT_INTERNAL)

    def _ready(self, connection: socket.socket, deadline: float, job, direction: str) -> None:
        remaining(connection, deadline)
        write_frame(
            connection,
            {
                "type": "stream-ready",
                "job_id": job["job_id"],
                "correlation_id": job["correlation_id"],
                "direction": direction,
                "max_data_bytes": MAX_DATA_BYTES,
                "max_stream_bytes": self.limit,
            },
            deadline,
        )
