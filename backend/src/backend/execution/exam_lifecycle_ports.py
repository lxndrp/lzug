"""Execution-owned Assessment capabilities used by exam lifecycle commands."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy.orm import Session


class AssessmentLifecycleWork(Protocol):
    """Narrow Assessment projections and corrections needed by Execution."""

    def day_completion(self, day_id: int) -> dict[str, Any]: ...

    def results_for_day_slots(
        self, day_id: int, slot_ids: Sequence[int]
    ) -> Sequence[dict[str, Any]]: ...

    def result_reopening_impacts(self, result_ids: set[int]) -> Sequence[dict[str, Any]]: ...

    def result_by_id(self, result_id: int) -> dict[str, Any] | None: ...

    def results_for_round(self, round_id: int) -> list[dict[str, Any]]: ...

    def result_for_round_candidate(self, candidate_id: int) -> dict[str, Any] | None: ...

    def open_result_correction(
        self,
        *,
        result_id: int,
        reopening_id: int,
        actor_member_id: int,
        reason: str,
        requested_at: str,
    ) -> dict[str, Any]: ...


class AssessmentLifecyclePort(Protocol):
    """Bind Assessment capabilities to the caller's SQLAlchemy transaction."""

    def bind(self, session: Session) -> AssessmentLifecycleWork: ...
