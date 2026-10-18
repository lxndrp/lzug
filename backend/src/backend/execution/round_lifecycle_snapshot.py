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


class ExamRoundLifecycleExportSnapshot(Protocol):
    """Detached persistence inputs needed to assemble the round export snapshot."""

    @property
    def records(self) -> Mapping[str, Any]: ...


class ExamRoundLifecycleExportSnapshotReader(Protocol):
    """Load export-specific records through the caller-owned transaction."""

    def load_round_lifecycle_export_snapshot(
        self, round_id: int
    ) -> ExamRoundLifecycleExportSnapshot: ...
