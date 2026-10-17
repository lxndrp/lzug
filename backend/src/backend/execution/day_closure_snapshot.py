"""Persistence-neutral read contracts for the exam-day closure view."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class ExamDayClosureReadSnapshot(Protocol):
    """Detached day header and ordered history used to render closure reads."""

    @property
    def day(self) -> Mapping[str, object]: ...

    @property
    def history(self) -> tuple[Mapping[str, object], ...]: ...

    @property
    def tasks(self) -> tuple[Mapping[str, object], ...]: ...


class ExamDayClosureReadSnapshotReader(Protocol):
    """Read the closure view projection over a caller-owned transaction."""

    def load_day_closure_read_snapshot(self, day_id: int) -> ExamDayClosureReadSnapshot | None: ...
