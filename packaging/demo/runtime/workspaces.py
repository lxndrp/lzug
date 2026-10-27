"""Short-lived, visitor-isolated persistence for the public demo."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from uuid import uuid4


class DemoWorkspaceCapacityError(RuntimeError):
    """Signal that no isolated demo workspace can be allocated."""


class DemoWorkspaceGenerationConflictError(RuntimeError):
    """Signal that a request tries to reset a superseded workspace generation."""


@dataclass
class DemoWorkspace:
    """Server-owned metadata for one visitor workspace."""

    path: Path
    created_at: datetime
    expires_at: datetime
    source_signature: tuple[int, int, int, int]
    token_digests: set[str] = field(default_factory=set)
    active_requests: int = 0
    discard_pending: bool = False
    active_paths: dict[Path, int] = field(default_factory=dict)
    retired_paths: set[Path] = field(default_factory=set)
    reset_lock: Lock = field(default_factory=Lock, repr=False)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DemoWorkspaceManager:
    """Create and resolve isolated SQLite copies without exposing workspace ids."""

    def __init__(
        self,
        root: Path,
        *,
        ttl: timedelta = timedelta(minutes=60),
        capacity: int = 32,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        on_discard: Callable[[Path], None] = lambda _path: None,
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Demo workspace lifetime must be positive")
        if capacity < 1 or capacity > 1_000:
            raise ValueError("Demo workspace capacity must be between 1 and 1000")
        self.root = root
        self.ttl = ttl
        self.capacity = capacity
        self.clock = clock
        self.on_discard = on_discard
        self._lock = RLock()
        self._by_token: dict[str, DemoWorkspace] = {}
        self._workspaces: dict[Path, DemoWorkspace] = {}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._remove_orphans()

    def create(
        self,
        base_db_path: Path,
    ) -> DemoWorkspace:
        """Allocate a workspace from the complete immutable profile seed."""
        with self._lock:
            now = _utc(self.clock())
            self._cleanup(now, base_db_path)
            if len(self._workspaces) >= self.capacity:
                raise DemoWorkspaceCapacityError("Demo workspace capacity is exhausted")
            workspace_path = self.root / f"workspace-{uuid4().hex}.sqlite"
            workspace = DemoWorkspace(
                path=workspace_path,
                created_at=now,
                expires_at=now + self.ttl,
                source_signature=self._signature(base_db_path),
            )
            try:
                self._clone(base_db_path, workspace_path)
            except Exception:
                workspace_path.unlink(missing_ok=True)
                raise
            self._workspaces[workspace_path] = workspace
            return workspace

    def resolve(self, base_db_path: Path, token: str | None) -> DemoWorkspace | None:
        """Resolve a live workspace from opaque session bearer material."""
        if not token:
            return None
        with self._lock:
            now = _utc(self.clock())
            self._cleanup(now, base_db_path)
            workspace = self._by_token.get(self._digest(token))
            return None if workspace is None or workspace.discard_pending else workspace

    def resolve_for_request(
        self,
        base_db_path: Path,
        request_db_path: Path,
        token: str | None,
    ) -> DemoWorkspace | None:
        """Resolve a workspace already leased by this request, including pending discard."""
        if not token:
            return None
        with self._lock:
            self._cleanup(_utc(self.clock()), base_db_path)
            workspace = self._by_token.get(self._digest(token))
            if workspace is None or workspace.active_paths.get(request_db_path, 0) == 0:
                return None
            return workspace

    def acquire_request(
        self, base_db_path: Path, token: str | None
    ) -> tuple[Path, Callable[[], None]]:
        """Lease a live workspace until the complete HTTP request has finished."""
        if not token:
            return base_db_path, lambda: None
        with self._lock:
            now = _utc(self.clock())
            self._cleanup(now, base_db_path)
            workspace = self._by_token.get(self._digest(token))
            if workspace is None or workspace.discard_pending or workspace.expires_at <= now:
                return base_db_path, lambda: None
            request_path = workspace.path
            self._retain_path(workspace, request_path)
            return request_path, lambda: self._release_request(workspace, request_path)

    def retain(self, workspace: DemoWorkspace) -> Callable[[], None]:
        """Lease a newly allocated workspace for the request that created it."""
        with self._lock:
            if self._workspaces.get(workspace.path) is not workspace or workspace.discard_pending:
                raise RuntimeError("Demo workspace cannot be retained after discard")
            request_path = workspace.path
            self._retain_path(workspace, request_path)
            return lambda: self._release_request(workspace, request_path)

    @contextmanager
    def retain_current_generation(
        self,
        workspace: DemoWorkspace,
        *,
        request_path: Path,
        token: str,
    ) -> Iterator[tuple[Path, Callable[[], None]]]:
        """Lease and stabilize the current generation while switching a session."""
        with workspace.reset_lock:
            with self._lock:
                if (
                    self._by_token.get(self._digest(token)) is not workspace
                    or workspace.active_paths.get(request_path, 0) == 0
                    or self._workspaces.get(workspace.path) is not workspace
                    or workspace.discard_pending
                ):
                    raise DemoWorkspaceGenerationConflictError(
                        "Demo workspace generation changed before the request switched"
                    )
                current_path = workspace.path
                self._retain_path(workspace, current_path)
            yield current_path, lambda: self._release_request(workspace, current_path)

    def bind(
        self,
        workspace: DemoWorkspace,
        token: str,
        *,
        previous_token: str | None = None,
    ) -> None:
        """Bind a newly issued session token to an existing workspace."""
        with self._lock:
            if previous_token:
                old_digest = self._digest(previous_token)
                self._by_token.pop(old_digest, None)
                workspace.token_digests.discard(old_digest)
            digest = self._digest(token)
            self._by_token[digest] = workspace
            workspace.token_digests.add(digest)

    def remaining(self, workspace: DemoWorkspace) -> timedelta:
        return max(workspace.expires_at - _utc(self.clock()), timedelta(0))

    def reset(
        self,
        base_db_path: Path,
        workspace: DemoWorkspace,
        request_path: Path,
        *,
        token: str,
    ) -> None:
        """Swap in a fresh generation while existing requests finish on the old path."""
        with workspace.reset_lock:
            with self._lock:
                if (
                    request_path != workspace.path
                    or workspace.active_paths.get(request_path, 0) == 0
                    or self._by_token.get(self._digest(token)) is not workspace
                ):
                    raise DemoWorkspaceGenerationConflictError(
                        "Demo workspace generation changed before reset"
                    )
                now = _utc(self.clock())
                if workspace.expires_at <= now:
                    self._discard(workspace)
                    raise RuntimeError("Demo workspace has expired")
                if workspace.source_signature != self._signature(base_db_path):
                    self._discard(workspace)
                    raise RuntimeError("Demo workspace was invalidated by the system reset")
                if (
                    self._workspaces.get(workspace.path) is not workspace
                    or workspace.discard_pending
                ):
                    raise RuntimeError("Demo workspace is unavailable")
                old_path = workspace.path

            new_path = self.root / f"workspace-{uuid4().hex}.sqlite"
            temporary = new_path.with_suffix(f"{new_path.suffix}.{uuid4().hex}.tmp")
            swapped = False
            try:
                # Copy outside the manager lock so unrelated requests can keep
                # acquiring their current generation while reset prepares a new one.
                self._clone(base_db_path, temporary)
                os.replace(temporary, new_path)
                new_path.chmod(0o600)
                with self._lock:
                    now = _utc(self.clock())
                    if workspace.expires_at <= now:
                        self._discard(workspace)
                        raise RuntimeError("Demo workspace has expired")
                    if workspace.source_signature != self._signature(base_db_path):
                        self._discard(workspace)
                        raise RuntimeError("Demo workspace was invalidated by the system reset")
                    if (
                        request_path != workspace.path
                        or workspace.active_paths.get(request_path, 0) == 0
                        or self._by_token.get(self._digest(token)) is not workspace
                    ):
                        raise DemoWorkspaceGenerationConflictError(
                            "Demo workspace generation changed while reset was prepared"
                        )
                    if (
                        self._workspaces.get(old_path) is not workspace
                        or workspace.path != old_path
                        or workspace.discard_pending
                    ):
                        raise RuntimeError("Demo workspace changed while it was reset")
                    self._workspaces.pop(old_path)
                    workspace.path = new_path
                    self._workspaces[new_path] = workspace
                    swapped = True
                    if workspace.active_paths.get(old_path, 0):
                        workspace.retired_paths.add(old_path)
                    else:
                        self._delete_retired_path(workspace, old_path)
            except Exception:
                self._delete_artifacts(temporary)
                if not swapped:
                    self._delete_artifacts(new_path)
                raise
            else:
                self._delete_artifacts(temporary)

    def discard(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            workspace = self._by_token.get(self._digest(token))
            if workspace is not None:
                self._discard(workspace)

    def discard_workspace(self, workspace: DemoWorkspace) -> None:
        """Discard an allocated workspace before a session token exists."""
        with self._lock:
            if self._workspaces.get(workspace.path) is workspace:
                self._discard(workspace)

    def active_count(self, base_db_path: Path) -> int:
        with self._lock:
            self._cleanup(_utc(self.clock()), base_db_path)
            return len(self._workspaces)

    def _cleanup(self, now: datetime, base_db_path: Path) -> None:
        signature = self._signature(base_db_path)
        for workspace in tuple(self._workspaces.values()):
            if workspace.expires_at <= now or workspace.source_signature != signature:
                self._discard(workspace)

    def _discard(self, workspace: DemoWorkspace) -> None:
        workspace.discard_pending = True
        if workspace.active_requests == 0:
            self._finish_discard(workspace)

    @staticmethod
    def _retain_path(workspace: DemoWorkspace, request_path: Path) -> None:
        workspace.active_requests += 1
        workspace.active_paths[request_path] = workspace.active_paths.get(request_path, 0) + 1

    def _release_request(self, workspace: DemoWorkspace, request_path: Path) -> None:
        with self._lock:
            active_for_path = workspace.active_paths.get(request_path, 0)
            if workspace.active_requests <= 0 or active_for_path <= 0:
                raise RuntimeError("Demo workspace request lease was released more than once")
            workspace.active_requests -= 1
            if active_for_path == 1:
                del workspace.active_paths[request_path]
            else:
                workspace.active_paths[request_path] = active_for_path - 1
            if (
                request_path in workspace.retired_paths
                and request_path not in workspace.active_paths
            ):
                self._delete_retired_path(workspace, request_path)
            if workspace.discard_pending and workspace.active_requests == 0:
                self._finish_discard(workspace)

    def _delete_retired_path(self, workspace: DemoWorkspace, path: Path) -> None:
        if workspace.active_paths.get(path, 0):
            return
        workspace.retired_paths.discard(path)
        self._delete_artifacts(path)
        self.on_discard(path)

    def _finish_discard(self, workspace: DemoWorkspace) -> None:
        if self._workspaces.get(workspace.path) is not workspace:
            return
        for digest in tuple(workspace.token_digests):
            self._by_token.pop(digest, None)
        workspace.token_digests.clear()
        self._workspaces.pop(workspace.path, None)
        paths = {*workspace.retired_paths, workspace.path}
        workspace.retired_paths.clear()
        for path in paths:
            self._delete_artifacts(path)
            self.on_discard(path)

    def _remove_orphans(self) -> None:
        """Remove inaccessible copies left behind by a previous runtime process."""
        for path in self.root.glob("workspace-*.sqlite*"):
            if path.is_file() and not path.is_symlink():
                path.unlink(missing_ok=True)

    @staticmethod
    def _delete_sidecars(path: Path) -> None:
        for suffix in ("-wal", "-shm", ".snapshot.lock", ".activation.lock"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)

    @classmethod
    def _delete_artifacts(cls, path: Path) -> None:
        path.unlink(missing_ok=True)
        cls._delete_sidecars(path)

    @staticmethod
    def _clone(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (
            closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_connection,
            source_connection,
        ):
            with closing(sqlite3.connect(target)) as target_connection, target_connection:
                source_connection.backup(target_connection)
        target.chmod(0o600)

    @staticmethod
    def _signature(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
