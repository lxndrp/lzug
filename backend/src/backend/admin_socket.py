"""One Linux Unix-socket listener in the authoritative HTTP backend process."""

from __future__ import annotations

import os
import socket
import struct
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import BoundedSemaphore, Event, RLock, Thread
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from backend.admin_socket_artifacts import STREAM_COMMANDS, SocketArtifacts, validate_request
from backend.admin_socket_path import SocketPath, SocketSecurityError
from backend.admin_socket_protocol import (
    MAX_DATA_BYTES,
    MAX_FRAME_BYTES,
    SOCKET_PROTOCOL,
    SOCKET_SCHEMA,
    SocketProtocolError,
    read_frame,
    write_frame,
)
from backend.application.admin import (
    _ADMIN_COMMANDS,
    _ARTIFACT_COMMANDS,
    _DIAGNOSTIC_COMMANDS,
    MAX_REQUEST_BYTES,
    AdminActorContext,
    AdminApplication,
)
from backend.observability import emit_event

CONTROL_COMMANDS = _ADMIN_COMMANDS | _ARTIFACT_COMMANDS | _DIAGNOSTIC_COMMANDS


@dataclass(frozen=True)
class SocketConfig:
    """Explicit opt-in; provisioning the ephemeral directory belongs to the operator."""

    directory: Path
    gid: int
    max_connections: int = 8
    handshake_timeout: float = 5
    request_timeout: float = 30
    shutdown_timeout: float = 30
    history_size: int = 128
    max_stream_bytes: int = 1024 * 1024 * 1024
    stream_timeout: float = 300

    def __post_init__(self) -> None:
        if (
            self.gid < 0
            or not 1 <= self.max_connections <= 64
            or not self.max_connections <= self.history_size <= 4096
            or not 0 < self.handshake_timeout <= 60
            or not 0 < self.request_timeout <= 3600
            or not 0 < self.shutdown_timeout <= 3600
            or type(self.max_stream_bytes) is not int
            or not 1 <= self.max_stream_bytes <= 1024 * 1024 * 1024
            or not 0 < self.stream_timeout <= 3600
        ):
            raise ValueError("Invalid admin socket limits")


def peer_actor(connection: socket.socket, gid: int) -> AdminActorContext:
    """Trust kernel credentials, never client actor claims or /proc PID lookups.

    The service UID or the dedicated primary operator GID is required in
    addition to filesystem DAC. Supplementary-group-only peers fail closed.
    """
    pid, uid, peer_gid = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    return AdminActorContext(
        f"pid:{pid}:uid:{uid}:gid:{peer_gid}",
        pid > 0 and uid >= 0 and (uid == os.geteuid() or peer_gid == gid),
    )


class AdminSocket:
    """Bound workers and drain mutations before relinquishing socket ownership.

    Execution is never forcibly cancelled or retried. A connection deadline
    bounds I/O; an already admitted worker keeps its slot until the application
    returns, even if the result can no longer be delivered.
    """

    def __init__(
        self,
        config: SocketConfig,
        application: AdminApplication,
        *,
        on_failure: Callable[[], None],
    ) -> None:
        if application.runtime is None:
            raise ValueError("Admin socket requires the authoritative runtime")
        # Runtime files must never live in persistent data/document/backup trees.
        for persistent in (
            application.paths.data_dir,
            application.paths.documents,
            application.paths.backups,
            application.paths.database.parent,
        ):
            if config.directory.resolve().is_relative_to(persistent.resolve()):
                raise SocketSecurityError()
        self.config = config
        self.application = application
        self.on_failure = on_failure
        self.path = SocketPath(config.directory, config.gid)
        self._listener: socket.socket | None = None
        self._thread: Thread | None = None
        self._stopping = Event()
        self._lock = RLock()
        self._slots = BoundedSemaphore(config.max_connections)
        self._artifact_slot = BoundedSemaphore(1)
        self._artifact_cleanup_failed = Event()
        self.artifacts = SocketArtifacts(application, config.max_stream_bytes)
        self._workers: dict[Thread, socket.socket] = {}
        self._jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._state = "stopped"

    def snapshot(self) -> dict[str, Any]:
        """Expose limits and technical state without paths, parameters or results."""
        with self._lock:
            limits = asdict(self.config)
            del limits["directory"]
            return {
                "state": self._state,
                "active_connections": len(self._workers),
                "protocol": SOCKET_PROTOCOL,
                "schema": SOCKET_SCHEMA,
                "max_request_bytes": MAX_REQUEST_BYTES,
                "max_response_bytes": MAX_FRAME_BYTES,
                "max_data_bytes": MAX_DATA_BYTES,
                "max_artifact_connections": 1,
                "artifact_cleanup_required": self._artifact_cleanup_failed.is_set(),
                **limits,
            }

    def start(self) -> None:
        """Publish only after security checks; startup failure creates no replacement."""
        if self._state != "stopped" or self._stopping.is_set():
            raise RuntimeError("Admin socket cannot be restarted")
        try:
            self.path.open()
            self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.path.bind(self._listener)
            self._listener.listen(self.config.max_connections)
            self._listener.settimeout(0.1)
            self._state = "listening"
            self._thread = Thread(target=self._accept, name="lzug-admin-listener")
            self._thread.start()
        except OSError, SocketSecurityError:
            if self._listener is not None:
                self._listener.close()
            self.path.close()
            self._state = "failed"
            raise SocketSecurityError() from None

    def _accept(self) -> None:
        assert self._listener is not None
        try:
            while not self._stopping.is_set():
                try:
                    connection, _address = self._listener.accept()
                except TimeoutError:
                    continue
                if not self._slots.acquire(blocking=False):
                    # No unbounded rejection workers or writes in the accept loop.
                    connection.close()
                    continue
                with self._lock:
                    if self._stopping.is_set():
                        connection.close()
                        self._slots.release()
                        break
                    worker = Thread(target=self._serve, args=(connection,), name="lzug-admin-job")
                    self._workers[worker] = connection
                    worker.start()
        except OSError:
            if not self._stopping.is_set():
                self._state = "failed"
                emit_event("admin_socket", phase="listener", status="failed")
                self.on_failure()

    def _audit(self, job: dict[str, Any], actor: str, signal: str) -> None:
        emit_event(
            "admin_socket",
            actor=actor,
            job_id=job["job_id"],
            correlation_id=job["correlation_id"],
            command=job["command"],
            phase=job["phase"],
            status=job["status"],
            signal=signal,
        )

    def _record(self, job: dict[str, Any], **fields: Any) -> None:
        with self._lock:
            job.update(fields)
            self._jobs[job["job_id"]] = dict(job)
            while len(self._jobs) > self.config.history_size:
                terminal = next(
                    key for key, value in self._jobs.items() if value["status"] != "running"
                )
                del self._jobs[terminal]

    def _handshake(self, connection: socket.socket, job: dict[str, Any]) -> None:
        deadline = monotonic() + self.config.handshake_timeout
        hello = read_frame(connection, deadline, 1024)
        if (
            set(hello) != {"type", "protocol", "schema"}
            or hello["type"] != "hello"
            or type(hello["protocol"]) is not int
            or type(hello["schema"]) is not int
            or hello["protocol"] != SOCKET_PROTOCOL
            or hello["schema"] != SOCKET_SCHEMA
        ):
            raise SocketProtocolError("handshake", "version_incompatible")
        write_frame(
            connection,
            {
                "type": "hello",
                "protocol": SOCKET_PROTOCOL,
                "schema": SOCKET_SCHEMA,
                "job_id": job["job_id"],
                "correlation_id": job["correlation_id"],
                "limits": self.snapshot(),
            },
            deadline,
        )

    def _execute(self, request: dict[str, Any], actor: AdminActorContext) -> tuple[dict, int]:
        if (
            set(request) != {"version", "command", "arguments"}
            or type(request["version"]) is not int
        ):
            raise SocketProtocolError("validation", "request_invalid")
        command = request["command"]
        if not isinstance(command, str) or request["version"] != SOCKET_SCHEMA:
            raise SocketProtocolError("validation", "request_invalid")
        if command == "socket-job-status":
            arguments = request["arguments"]
            if not isinstance(arguments, dict) or set(arguments) != {"job_id"}:
                raise SocketProtocolError("validation", "request_invalid")
            try:
                key = str(UUID(arguments["job_id"]))
            except ValueError, TypeError, AttributeError:
                raise SocketProtocolError("validation", "request_invalid") from None
            with self._lock:
                result = self._jobs.get(key)
                result = dict(result) if result else {"job_id": key, "status": "unknown"}
            return {"version": SOCKET_SCHEMA, "ok": True, "result": result}, 0
        if command not in CONTROL_COMMANDS:
            raise SocketProtocolError("validation", "command_unsupported")
        result = self.application.execute(request, actor)
        response = result.response
        if command in _DIAGNOSTIC_COMMANDS and response["ok"]:
            response["result"]["socket"] = self.snapshot()
        return response, result.exit_code

    def _exchange(
        self, connection: socket.socket, actor: AdminActorContext, job: dict[str, Any]
    ) -> None:
        self._record(job, phase="handshake")
        self._handshake(connection, job)
        self._record(job, phase="validation")
        deadline = monotonic() + self.config.request_timeout
        request = read_frame(connection, deadline, MAX_REQUEST_BYTES)
        command = request.get("command")
        if isinstance(command, str) and command in CONTROL_COMMANDS | STREAM_COMMANDS | {
            "socket-job-status"
        }:
            self._record(job, command=command)
        if self._stopping.is_set():
            raise SocketProtocolError("lifecycle", "socket_stopping")
        self._record(job, phase="execution")
        self._audit(job, actor.technical_identity, "execute")
        if isinstance(command, str) and command in STREAM_COMMANDS:
            validate_request(request)
            if self._artifact_cleanup_failed.is_set():
                raise SocketProtocolError("lifecycle", "artifact_cleanup_required")
            if not self._artifact_slot.acquire(blocking=False):
                raise SocketProtocolError("lifecycle", "artifact_busy")
            try:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, MAX_DATA_BYTES)
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, MAX_DATA_BYTES)
                deadline = monotonic() + self.config.stream_timeout
                response, code = self.artifacts.execute(
                    connection, request, deadline, job, self._record
                )
                if not response["ok"] and response["error"]["class"] == "artifact_cleanup_failed":
                    self._artifact_cleanup_failed.set()
            finally:
                self._artifact_slot.release()
        else:
            response, code = self._execute(request, actor)
        phase = "execution"
        if not response["ok"]:
            phase = {"database_not_ready": "lifecycle", "invalid_request": "validation"}.get(
                response["error"]["class"], "execution"
            )
        self._record(job, status="succeeded" if response["ok"] else "failed", phase=phase)
        write_frame(
            connection,
            {"type": "result", **job, "exit_code": code, "response": response},
            deadline,
        )
        self._record(job, delivery="sent")

    def _serve(self, connection: socket.socket) -> None:
        job = {
            "job_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "command": "unknown",
            "phase": "authorization",
            "status": "running",
            "delivery": "pending",
        }
        actor = AdminActorContext("unavailable", False)
        self._record(job)
        try:
            actor = peer_actor(connection, self.config.gid)
            if not actor.is_authorized:
                raise SocketProtocolError("authorization", "authorization_failed")
            self._audit(job, actor.technical_identity, "begin")
            self._exchange(connection, actor, job)
        except SocketProtocolError as error:
            fields = {"phase": error.phase, "delivery": "lost", "code": error.code}
            if job["status"] == "running":
                fields["status"] = "rejected"
            self._record(job, **fields)
            try:
                write_frame(
                    connection,
                    {"type": "error", **job, "code": error.code},
                    monotonic() + min(1, self.config.handshake_timeout),
                )
            except OSError, SocketProtocolError:
                pass
        except OSError as error:
            if job["status"] == "running":
                self._record(
                    job,
                    status="unknown" if job["phase"] == "execution" else "rejected",
                    delivery="lost",
                    code="timeout" if isinstance(error, TimeoutError) else "connection_lost",
                )
            else:
                self._record(job, phase="transfer", delivery="lost")
        except Exception:
            # An unexpected application/encoding failure never proves no mutation.
            # Keep uncertainty visible without logging exception text or payloads.
            self._record(job, status="unknown", phase="execution", delivery="lost")
        finally:
            try:
                self._audit(job, actor.technical_identity, "end")
            finally:
                connection.close()
                with self._lock:
                    worker = next(
                        key for key, value in self._workers.items() if value is connection
                    )
                    del self._workers[worker]
                self._slots.release()

    def stop(self) -> None:
        """Close new admission and I/O; retain directory ownership until workers exit."""
        self._stopping.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            workers = list(self._workers.items())
        for _worker, connection in workers:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = monotonic() + self.config.shutdown_timeout
        for worker, _connection in workers:
            worker.join(max(0, deadline - monotonic()))
            if worker.is_alive():
                raise TimeoutError("Admin socket is draining an admitted operation")
        self.path.close()
        self._state = "stopped"
