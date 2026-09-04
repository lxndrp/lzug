"""Short-lived, visitor-isolated persistence for the public demo."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4


class DemoWorkspaceCapacityError(RuntimeError):
    """Signal that no isolated demo workspace can be allocated."""


@dataclass
class DemoWorkspace:
    """Server-owned metadata for one visitor workspace."""

    path: Path
    created_at: datetime
    expires_at: datetime
    source_signature: tuple[int, int, int, int]
    token_digests: set[str] = field(default_factory=set)


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
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Demo workspace lifetime must be positive")
        if capacity < 1 or capacity > 1_000:
            raise ValueError("Demo workspace capacity must be between 1 and 1000")
        self.root = root
        self.ttl = ttl
        self.capacity = capacity
        self.clock = clock
        self._lock = RLock()
        self._by_token: dict[str, DemoWorkspace] = {}
        self._workspaces: dict[Path, DemoWorkspace] = {}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self._remove_orphans()

    def create(
        self,
        base_db_path: Path,
        seed: Callable[[Path, datetime], None],
    ) -> DemoWorkspace:
        """Allocate, clone, and seed a workspace or fail without sharing state."""
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
                seed(workspace_path, now)
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
            if workspace is None or workspace.expires_at <= now:
                return None
            return workspace

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
        seed: Callable[[Path, datetime], None],
    ) -> None:
        """Atomically replace domain state while preserving the absolute expiry."""
        with self._lock:
            now = _utc(self.clock())
            if workspace.expires_at <= now:
                self._discard(workspace)
                raise RuntimeError("Demo workspace has expired")
            if workspace.source_signature != self._signature(base_db_path):
                self._discard(workspace)
                raise RuntimeError("Demo workspace was invalidated by the system reset")
            temporary = workspace.path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                self._clone(base_db_path, temporary)
                seed(temporary, now)
                self._delete_sidecars(workspace.path)
                os.replace(temporary, workspace.path)
                workspace.path.chmod(0o600)
            finally:
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
        for digest in tuple(workspace.token_digests):
            self._by_token.pop(digest, None)
        workspace.token_digests.clear()
        self._workspaces.pop(workspace.path, None)
        self._delete_artifacts(workspace.path)

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
