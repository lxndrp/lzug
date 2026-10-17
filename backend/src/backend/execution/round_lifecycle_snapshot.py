"""Persistence-neutral projection for reading round lifecycle state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ExamRoundLifecycleReadSnapshot(Protocol):
    """Detached lifecycle records and evaluation inputs for one round."""

    @property
    def records(self) -> Mapping[str, Any]: ...


class ExamRoundLifecycleReadSnapshotReader(Protocol):
    """Load detached lifecycle data using a caller-owned transaction."""

    def load_round_lifecycle_read_snapshot(
        self, round_id: int
    ) -> ExamRoundLifecycleReadSnapshot | None: ...
