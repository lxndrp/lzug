"""Application-owned transaction boundary for exam lifecycle commands."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from backend.application.consequence_ports import LifecycleConsequenceReadPort
from backend.application.exam_lifecycle_contracts import (
    DayCloseCommand,
    DayClosureFacts,
    DayReopenCommand,
    RoundDecisionCommand,
    RoundLifecycleFacts,
    RoundReopenCommand,
)
from backend.assessment.ports import AssessmentUnitOfWork
from backend.execution.exam_day_closures import (
    ExamDayClosureIntent,
    ExamDayClosureOutcome,
    ExamDayClosureService,
    ExamDayReopeningHandle,
    ExamDayReopeningIntent,
)
from backend.execution.exam_round_lifecycle import (
    ExamRoundDecisionIntent,
    ExamRoundDecisionOutcome,
    ExamRoundLifecycleService,
    ExamRoundReopeningIntent,
)
from backend.execution.lifecycle_ports import (
    AssessmentLifecycleWork,
    CalendarLifecycleWork,
    IdentityLifecycleWork,
    PlanningLifecycleWork,
)
from backend.execution.slot_ports import ExecutionUnitOfWork
from backend.identity.authorization import AuthorizationScope


class ExamLifecycleExecutionUnitOfWork(ExecutionUnitOfWork, Protocol):
    """Execution capabilities required by Application lifecycle commands."""

    def read_day_closure(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        day_id: int,
        facts: DayClosureFacts,
    ) -> dict | None: ...

    def read_round_lifecycle(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        round_id: int,
        pending_consequence_ids: Sequence[int],
    ) -> dict | None: ...

    def set_round_candidate_terminal_status(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        round_id: int,
        candidate_id: int,
        payload: dict,
    ) -> dict: ...

    def document_round_ihk_status(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        round_id: int,
        result_id: int,
        payload: dict,
    ) -> dict: ...

    def delete_empty_draft_round(
        self, service: ExamRoundLifecycleService, scope: AuthorizationScope, round_id: int
    ) -> bool: ...

    def export_round(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        round_id: int,
        *,
        human: bool,
    ) -> dict | str: ...

    def export_day(
        self, service: ExamDayClosureService, scope: AuthorizationScope, day_id: int, *, human: bool
    ) -> dict | str: ...

    def exam_day_round_id(self, day_id: int) -> int | None: ...

    def exam_day_ids_for_round(self, round_id: int) -> tuple[int, ...]: ...

    def evaluate_day_close(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        day_id: int,
        command: DayCloseCommand,
        facts: DayClosureFacts,
    ) -> ExamDayClosureIntent: ...

    def apply_day_close(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        intent: ExamDayClosureIntent,
        facts: DayClosureFacts,
    ) -> ExamDayClosureOutcome: ...

    def day_reopening_impact(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        day_id: int,
        raw_scope: object,
        facts: DayClosureFacts,
    ) -> dict[str, object]: ...

    def evaluate_day_reopen(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        day_id: int,
        command: DayReopenCommand,
        facts: DayClosureFacts,
    ) -> ExamDayReopeningIntent: ...

    def begin_day_reopen(
        self, service: ExamDayClosureService, intent: ExamDayReopeningIntent
    ) -> ExamDayReopeningHandle: ...

    def complete_day_reopen(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        handle: ExamDayReopeningHandle,
        facts: DayClosureFacts,
        assessment_corrections: dict[int, dict],
    ) -> ExamDayClosureOutcome: ...

    def replay_day_reopen(
        self,
        service: ExamDayClosureService,
        scope: AuthorizationScope,
        intent: ExamDayReopeningIntent,
        facts: DayClosureFacts,
    ) -> ExamDayClosureOutcome: ...

    def evaluate_round_decision(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        command: RoundDecisionCommand,
        decision_type: str,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionIntent: ...

    def replay_round_decision(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionOutcome: ...

    def refresh_round_decision_snapshot(
        self,
        service: ExamRoundLifecycleService,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionIntent: ...

    def apply_round_decision(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
        cancelled_recipients: set[int],
    ) -> ExamRoundDecisionOutcome: ...

    def evaluate_round_reopen(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        command: RoundReopenCommand,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundReopeningIntent: ...

    def round_reopening_impact(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        facts: RoundLifecycleFacts,
        raw_scope: object,
    ) -> dict[str, object]: ...

    def replay_round_reopen(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        intent: ExamRoundReopeningIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionOutcome: ...

    def apply_round_reopen(
        self,
        service: ExamRoundLifecycleService,
        scope: AuthorizationScope,
        intent: ExamRoundReopeningIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionOutcome: ...


class ExamLifecycleUnitOfWork(Protocol):
    """Compose Execution and Assessment capabilities in one transaction."""

    @property
    def execution(self) -> ExamLifecycleExecutionUnitOfWork: ...

    @property
    def assessment(self) -> AssessmentUnitOfWork: ...

    @property
    def assessment_lifecycle(self) -> AssessmentLifecycleWork: ...

    @property
    def planning_lifecycle(self) -> PlanningLifecycleWork: ...

    @property
    def identity_lifecycle(self) -> IdentityLifecycleWork: ...

    @property
    def calendar_lifecycle(self) -> CalendarLifecycleWork: ...

    @property
    def consequences(self) -> LifecycleConsequenceReadPort: ...


class ExamLifecycleUnitOfWorkFactory(Protocol):
    """Open the common write boundary owned by Application."""

    def __call__(self) -> AbstractContextManager[ExamLifecycleUnitOfWork]: ...

    def read_scope(self) -> AbstractContextManager[ExamLifecycleUnitOfWork]: ...
