"""Thread-context limits for SQLite files inside one disposable artifact workspace."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_limits: ContextVar[tuple[Path, int] | None] = ContextVar("artifact_sqlite_limits", default=None)


@contextmanager
def artifact_database_limit(root: Path, size: int) -> Iterator[None]:
    """Limit only staged copies; never change the live database's configuration."""
    token = _limits.set((root.resolve(), size))
    try:
        yield
    finally:
        _limits.reset(token)


def configure_artifact_database(connection, path: Path) -> None:
    """Apply the page ceiling to every connection that can grow a staged copy."""
    limits = _limits.get()
    if limits is None or not path.resolve().is_relative_to(limits[0]):
        return
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    pages = max(1, limits[1] // page_size)
    actual = connection.execute(f"PRAGMA max_page_count = {pages}").fetchone()[0]
    if actual > pages:
        raise ValueError("Artifact database limit exceeded")
    connection.execute("PRAGMA cache_size = -2048")
    connection.execute("PRAGMA wal_autocheckpoint = 128")
