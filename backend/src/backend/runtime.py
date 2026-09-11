"""Transport-neutral runtime ownership, admission, and persistence lock order.

One coordinator owns a database for its process lifetime. Adapters hold an
admission across an entire request; persistence scopes also hold admissions so
an abandoned worker cannot release ownership before its transaction exits.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from fcntl import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, flock
from pathlib import Path
from threading import Condition, RLock
from time import monotonic
from typing import IO
from uuid import UUID, uuid4


class RuntimeState(StrEnum):
    """Internal process states; public representations belong to the adapters."""

    STOPPED = "stopped"
    INITIALIZING = "initializing"
    READY = "ready"
    MAINTENANCE = "maintenance"
    MIGRATION_REQUIRED = "migration_required"
    MIGRATING = "migrating"
    ERROR = "error"
    STOPPING = "stopping"


class Operation(StrEnum):
    """Exclusive work classes, never client-supplied command arguments."""

    RESTORE = "restore"
    MIGRATION = "migration"


class JobStatus(StrEnum):
    """No automatic retry is implied by any terminal status."""

    WAITING = "waiting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class RuntimeConflictError(RuntimeError):
    """Safe rejection before admitting conflicting work."""

    def __init__(
        self, code: str = "runtime_not_ready", *, state: RuntimeState | None = None
    ) -> None:
        super().__init__("Runtime cannot accept this operation")
        self.code = code
        self.state = state


@dataclass(frozen=True)
class RuntimeJob:
    """Bounded technical evidence without arguments, payloads or error strings."""

    id: str
    operation: Operation
    status: JobStatus
    requires_recovery: bool = False


@dataclass
class _Admission:
    runtime: RuntimeCoordinator
    exclusive: bool = False
    active: bool = True


@dataclass
class _FileLease:
    path: Path
    operation: int
    active: bool = True


_admission: ContextVar[_Admission | None] = ContextVar("lzug_runtime_admission", default=None)
_registry_lock = RLock()
_runtimes: dict[Path, RuntimeCoordinator] = {}
_file_leases: ContextVar[tuple[_FileLease, ...]] = ContextVar("lzug_file_leases", default=())


def runtime_for(db_path: Path) -> RuntimeCoordinator | None:
    """Keep inherited work bound to its owner, including after that owner stops."""
    path = Path(db_path).resolve()
    parent = _admission.get()
    if parent is not None and parent.runtime.db_path == path:
        return parent.runtime
    with _registry_lock:
        return _runtimes.get(path)


@contextmanager
def file_lock(path: Path, operation: int) -> Iterator[None]:
    """Hold a stable sidecar inode; lock files are never deleted on cleanup."""
    path = path.resolve()
    held = _file_leases.get()
    for lease in held:
        if lease.active and lease.path == path:
            if lease.operation == LOCK_SH and operation == LOCK_EX:
                raise RuntimeConflictError("lock_upgrade_forbidden")
            yield
            return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock_file:
        flock(lock_file.fileno(), operation)
        lease = _FileLease(path, operation)
        token = _file_leases.set((*held, lease))
        try:
            yield
        finally:
            lease.active = False
            _file_leases.reset(token)
            flock(lock_file.fileno(), LOCK_UN)


@contextmanager
def persistence_access(db_path: Path) -> Iterator[None]:
    """Admit a service transaction when the path belongs to a live runtime."""
    _reject_stale_admission(db_path)
    runtime = runtime_for(db_path)
    if runtime is None:
        yield
    else:
        with runtime.admit():
            yield


@contextmanager
def exclusive_operation(db_path: Path, operation: Operation) -> Iterator[None]:
    """Coordinate maintenance, including callers of the existing services."""
    _reject_stale_admission(db_path)
    runtime = runtime_for(db_path)
    if runtime is None:
        yield
    else:
        with runtime.operation(operation):
            yield


def _reject_stale_admission(db_path: Path) -> None:
    parent = _admission.get()
    if (
        parent is not None
        and parent.runtime.db_path == Path(db_path).resolve()
        and not parent.active
    ):
        raise RuntimeConflictError("request_finished")


class RuntimeCoordinator:
    """Own lifecycle and drain admitted work before exclusive operations.

    Lock order is admission, activation, snapshot, migration. The process owner
    lock precedes them and is retained until all workers and jobs have exited.
    Only the latest exclusive job is retained, atomically, across restarts.
    """

    def __init__(self, db_path: Path, probe: Callable[[], Mapping[str, object]]) -> None:
        self.db_path = Path(db_path).resolve()
        self._probe = probe
        self._condition = Condition(RLock())
        self._state = RuntimeState.STOPPED
        self._reason = "stopped"
        self._active = 0
        self._job: RuntimeJob | None = None
        self._busy = False
        self._initializing = False
        self._owner: IO[str] | None = None
        self._journal = Path(f"{self.db_path}.runtime-job.json")
        self._migration: dict[str, object] | None = None

    def snapshot(self) -> dict[str, object]:
        """Read immutable diagnostics without opening SQLite or documents."""
        with self._condition:
            return {
                "state": self._state.value,
                "ready": self._state == RuntimeState.READY and not self._busy,
                "reason": self._reason,
                "active": self._active,
                "job": asdict(self._job) if self._job else None,
            }

    def diagnosis(self) -> dict[str, object]:
        """Give operators the same state plus an allowed, non-mutating next step."""
        with self._condition:
            snapshot = {**self.snapshot(), "migration": deepcopy(self._migration)}
        state = snapshot["state"]
        action = (
            "none"
            if state == RuntimeState.READY
            else (
                "inspect_upgrade"
                if state == RuntimeState.MIGRATION_REQUIRED
                else "inspect_recovery" if state == RuntimeState.ERROR else "wait"
            )
        )
        return {
            **snapshot,
            "next_action": {
                "code": action,
                "command": (
                    "lzug-admin upgrade status"
                    if action == "inspect_upgrade"
                    else (
                        "lzug-admin system doctor"
                        if action == "inspect_recovery"
                        else "lzug-admin system status"
                    )
                ),
            },
        }

    def start(self, prepare: Callable[[], None] | None = None) -> None:
        """Claim ownership and inspect storage; failures remain diagnosable.

        Ownership conflicts raise before preparation. An interrupted job keeps
        normal work closed even if the schema alone passes its readiness probe.
        """
        self.claim()
        self.initialize(prepare)

    def claim(self) -> None:
        """Acquire ownership before publishing transports, without accessing SQLite."""
        with self._condition, _registry_lock:
            if self._owner is not None or self.db_path in _runtimes:
                raise RuntimeConflictError("runtime_owned")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            owner = Path(f"{self.db_path}.runtime.lock").open("a+")
            try:
                flock(owner.fileno(), LOCK_EX | LOCK_NB)
            except BaseException:
                owner.close()
                raise RuntimeConflictError("runtime_owned") from None
            self._owner = owner
            _runtimes[self.db_path] = self
            self._state = RuntimeState.INITIALIZING
            self._reason = "initializing"
            self._migration = None
            self._busy = False

    def initialize(self, prepare: Callable[[], None] | None = None) -> None:
        """Prepare the owned instance while HTTP and admin transports remain live."""
        with self._condition:
            if self._owner is None or self._busy or self._state != RuntimeState.INITIALIZING:
                raise RuntimeConflictError("runtime_not_owned")
            self._busy = True
            self._initializing = True
        inspected = None
        try:
            with self._exclusive_admission(), activation_lock(self.db_path, exclusive=True):
                self._load_job()
                if self._job and self._job.requires_recovery:
                    self._set_state(RuntimeState.ERROR, "operation_interrupted")
                    return
                if prepare is not None:
                    prepare()
                inspected = self._inspect()
        except Exception:
            self._set_state(RuntimeState.ERROR, "initialization_failed")
        except BaseException:
            self._set_state(RuntimeState.ERROR, "initialization_interrupted")
            raise
        finally:
            with self._condition:
                if inspected is not None:
                    self._set_state(*inspected)
                self._busy = False
                self._initializing = False
                self._condition.notify_all()

    @contextmanager
    def admit(self) -> Iterator[None]:
        """Lease one ordinary request/transaction; nested work may finish draining."""
        _reject_stale_admission(self.db_path)
        parent = _admission.get()
        with self._condition:
            _reject_stale_admission(self.db_path)
            inherited = parent is not None and parent.runtime is self and parent.active
            if not inherited and (self._state != RuntimeState.READY or self._busy):
                raise RuntimeConflictError(state=self._state)
            admission = _Admission(
                self, exclusive=bool(inherited and parent is not None and parent.exclusive)
            )
            self._active += 1
        token = _admission.set(admission)
        try:
            yield
        finally:
            with self._condition:
                admission.active = False
                self._active -= 1
                self._condition.notify_all()
            _admission.reset(token)

    @contextmanager
    def inspect_storage(self) -> Iterator[None]:
        """Lease backup/diagnostic access to a compatible, quiescent schema.

        This is an internal operator capability, never ordinary request admission.
        Exclusive lifecycle work drains these leases before touching storage.
        """
        with self._condition:
            if self._busy or self._state not in {
                RuntimeState.READY,
                RuntimeState.MIGRATION_REQUIRED,
            }:
                raise RuntimeConflictError("lifecycle_conflict")
            admission = _Admission(self)
            self._active += 1
        token = _admission.set(admission)
        try:
            with activation_lock(self.db_path):
                yield
        finally:
            with self._condition:
                admission.active = False
                self._active -= 1
                self._condition.notify_all()
            _admission.reset(token)

    @contextmanager
    def _exclusive_admission(self) -> Iterator[None]:
        admission = _Admission(self, exclusive=True)
        token = _admission.set(admission)
        try:
            yield
        finally:
            with self._condition:
                admission.active = False
            _admission.reset(token)

    @contextmanager
    def operation(
        self, operation: Operation, *, timeout: float = 30, job_id: str | None = None
    ) -> Iterator[RuntimeJob | None]:
        """Drain before restore/migration; reject competing jobs without queuing.

        Cancellation is accepted only while waiting. Once running, the owner
        completes or fails the operation under its lease, even after disconnect.
        """
        _reject_stale_admission(self.db_path)
        parent = _admission.get()
        if parent is not None and parent.runtime is self and parent.active:
            if not parent.exclusive:
                raise RuntimeConflictError("lock_upgrade_forbidden")
            if self._initializing and (self._job is None or self._job.status != JobStatus.RUNNING):
                with self._initialization_operation(operation):
                    yield self._job
            else:
                yield self._job
            return
        with self._condition:
            _reject_stale_admission(self.db_path)
            if self._busy or self._state in {
                RuntimeState.STOPPED,
                RuntimeState.STOPPING,
                RuntimeState.INITIALIZING,
            }:
                raise RuntimeConflictError("lifecycle_conflict")
            before = self._state, self._reason
            self._busy = True
            self._state = (
                RuntimeState.MIGRATING
                if operation == Operation.MIGRATION
                else RuntimeState.MAINTENANCE
            )
            self._reason = operation.value
            self._job = RuntimeJob(
                str(UUID(job_id)) if job_id else str(uuid4()),
                operation,
                JobStatus.WAITING,
                requires_recovery=before[0] == RuntimeState.ERROR
                or bool(self._job and self._job.requires_recovery),
            )
        running = False
        inspected = None
        try:
            self._save_job()
            self._drain(timeout)
            self._save_job()
            running = True
            with self._exclusive_admission(), activation_lock(self.db_path, exclusive=True):
                yield self._job
                candidate = self._inspect()
                if candidate[0] != RuntimeState.READY:
                    raise RuntimeConflictError("postcheck_failed")
            self._finish_job(JobStatus.SUCCEEDED)
            inspected = candidate
        except BaseException:
            if running:
                self._set_state(RuntimeState.ERROR, "operation_failed")
                self._finish_job(JobStatus.FAILED)
            else:
                self._set_state(*before)
                self._finish_job(JobStatus.CANCELLED)
            raise
        finally:
            with self._condition:
                if inspected is not None:
                    self._set_state(*inspected)
                self._busy = False
                self._condition.notify_all()

    def _drain(self, timeout: float) -> None:
        deadline = monotonic() + timeout
        with self._condition:
            assert self._job is not None
            while self._active:
                if self._job.status == JobStatus.CANCELLED or self._state == RuntimeState.STOPPING:
                    raise RuntimeConflictError("operation_cancelled")
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise RuntimeConflictError("drain_timeout")
                self._condition.wait(remaining)
            if self._job.status == JobStatus.CANCELLED or self._state == RuntimeState.STOPPING:
                raise RuntimeConflictError("operation_cancelled")
            self._job = replace(self._job, status=JobStatus.RUNNING, requires_recovery=True)

    def cancel(self, job_id: str) -> bool:
        """Cancel a waiting job only; never release a running worker's locks."""
        with self._condition:
            if not self._busy or self._job is None or self._job.id != job_id:
                return False
            if self._job.status != JobStatus.WAITING:
                return False
            self._job = replace(self._job, status=JobStatus.CANCELLED)
            self._condition.notify_all()
            return True

    @contextmanager
    def _initialization_operation(self, operation: Operation) -> Iterator[None]:
        self._set_state(
            (
                RuntimeState.MIGRATING
                if operation == Operation.MIGRATION
                else RuntimeState.MAINTENANCE
            ),
            operation.value,
        )
        self._job = RuntimeJob(str(uuid4()), operation, JobStatus.RUNNING, requires_recovery=True)
        self._save_job()
        try:
            yield
        except BaseException:
            self._finish_job(JobStatus.FAILED)
            raise
        else:
            self._finish_job(JobStatus.SUCCEEDED)

    def stop(self, *, timeout: float = 30) -> None:
        """Close admission and release ownership only after all work exits.

        A timeout leaves the process in stopping with its ownership lock held.
        The caller can wait again; it must never start a replacement worker.
        """
        deadline = monotonic() + timeout
        with self._condition:
            if self._owner is None:
                return
            self._state, self._reason = RuntimeState.STOPPING, "stopping"
            self._condition.notify_all()
            while self._active or self._busy:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise RuntimeConflictError("drain_timeout")
                self._condition.wait(remaining)
            with _registry_lock:
                del _runtimes[self.db_path]
                self._owner.close()
                self._owner = None
            self._state, self._reason = RuntimeState.STOPPED, "stopped"

    def _set_state(self, state: RuntimeState, reason: str) -> None:
        with self._condition:
            if self._state != RuntimeState.STOPPING:
                self._state, self._reason = state, reason

    def _inspect(self) -> tuple[RuntimeState, str]:
        result = self._probe()
        migration = result.get("migration")
        with self._condition:
            # Capture the existing migration probe for privileged diagnosis only.
            # Diagnostic reads never reopen storage during a schema transition.
            self._migration = (
                deepcopy(
                    {key: migration.get(key) for key in ("state", "current", "target", "pending")}
                )
                if isinstance(migration, Mapping)
                else None
            )
        if result.get("ready") is True:
            return RuntimeState.READY, "ready"
        if result.get("reason") == "migration_required":
            return RuntimeState.MIGRATION_REQUIRED, "migration_required"
        if result.get("reason") in {
            "database_missing",
            "migration_error",
            "schema_incomplete",
            "sqlite_settings_invalid",
            "database_unavailable",
        }:
            return RuntimeState.ERROR, str(result["reason"])
        return RuntimeState.ERROR, "persistence_not_ready"

    def _finish_job(self, status: JobStatus) -> None:
        with self._condition:
            if self._job is not None:
                self._job = replace(
                    self._job,
                    status=status,
                    requires_recovery=status != JobStatus.SUCCEEDED
                    and (
                        status in {JobStatus.FAILED, JobStatus.INTERRUPTED}
                        or self._job.requires_recovery
                    ),
                )
        try:
            self._save_job()
        except OSError:
            self._set_state(RuntimeState.ERROR, "job_status_unavailable")
            raise

    def _save_job(self) -> None:
        with self._condition:
            job = asdict(self._job) if self._job else None
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.db_path.parent, prefix=".lzug-runtime-", delete=False
        ) as temporary:
            path = Path(temporary.name)
            try:
                json.dump(job, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
                os.replace(path, self._journal)
                descriptor = os.open(self.db_path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                path.unlink(missing_ok=True)

    def _load_job(self) -> None:
        if not self._journal.exists():
            self._job = None
            return
        if self._journal.stat().st_size > 1024:
            raise ValueError("Invalid runtime journal")
        payload = json.loads(self._journal.read_text())
        self._job = RuntimeJob(
            str(UUID(payload["id"])),
            Operation(payload["operation"]),
            JobStatus(payload["status"]),
            requires_recovery=payload.get("requires_recovery") is not False,
        )
        if self._job.status in {JobStatus.WAITING, JobStatus.RUNNING, JobStatus.FAILED}:
            self._finish_job(JobStatus.INTERRUPTED)


@contextmanager
def activation_lock(db_path: Path, *, exclusive: bool = False) -> Iterator[None]:
    """First persistence lock: shared transactions, exclusive replacement/schema."""
    with file_lock(Path(f"{db_path}.activation.lock"), LOCK_EX if exclusive else LOCK_SH):
        yield
