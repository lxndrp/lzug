"""Serialize Identity membership writes with authorized-scope revalidation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock


class IdentityScopeCoordinator:
    """Coordinate short membership writes and final scope checks within one process."""

    def __init__(self) -> None:
        self._lock = RLock()

    @contextmanager
    def guard(self) -> Iterator[None]:
        with self._lock:
            yield
