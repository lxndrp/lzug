"""Shared transition values crossing Application, Execution, and Persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class ExamDayLifecycleSnapshot(Protocol):
    """Detached day state and transition records used during validation."""

    @property
    def day(self) -> Mapping[str, object]: ...

    @property
    def closure_fingerprints(self) -> tuple[str, ...]: ...

    @property
    def reopenings(self) -> tuple[Mapping[str, object], ...]: ...


class ExamDayConflictError(ValueError):
    """Signal a stale, repeated-with-different-content, or parallel day command."""


class ExamDayValidationError(ValueError):
    """Expose the complete failed prerequisite matrix for one close attempt."""

    def __init__(self, message: str, findings: list[dict[str, Any]]):
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class NotificationJob:
    recipient_member_ids: set[int]
    event_type: str
    title: str
    message: str
    origin_key: str


@dataclass(frozen=True)
class ExamDayClosureOutcome:
    """Committed lifecycle identity and deferred notification input."""

    committee_id: int | None = None
    round_id: int | None = None
    day_id: int | None = None
    notification_jobs: tuple[NotificationJob, ...] = ()


@dataclass(frozen=True)
class ExamDayClosureIntent:
    """Validated Execution decision ready for the Application-owned apply phase."""

    day_id: int
    expected_revision: int
    closure_type: str
    reason: str | None
    clarification_attempts: str | None
    command_fingerprint: str
    actor_member_id: int
    committee_id: int
    round_id: int
    reopening_id: int | None
    evaluation: dict[str, Any]
    replayed: bool = False


@dataclass(frozen=True)
class ExamDayReopeningIntent:
    """Validated Execution reopening request and detached impact calculation."""

    day_id: int
    expected_revision: int
    occasion: str
    source: str
    reason: str
    command_fingerprint: str
    actor_member_id: int
    committee_id: int
    round_id: int
    impact: dict[str, Any]
    replayed: bool = False
