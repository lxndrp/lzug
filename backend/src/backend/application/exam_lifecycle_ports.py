"""Application-owned transaction boundary for exam lifecycle commands."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from backend.assessment.ports import AssessmentUnitOfWork
from backend.execution.exam_day_closures import ExamDayClosureOutcome, ExamDayClosureService
from backend.execution.exam_round_lifecycle import (
    ExamRoundDecisionOutcome,
    ExamRoundLifecycleService,
)
from backend.execution.slot_ports import ExecutionUnitOfWork
from backend.identity.authorization import AuthorizationScope
from backend.lifecycle_ports import AssessmentLifecycleWork, PlanningLifecycleWork


class ExamLifecycleExecutionUnitOfWork(ExecutionUnitOfWork, Protocol):
    """Execution capabilities required by Application lifecycle commands."""

    def close_exam_day(
        self,
        service: ExamDayClosureService,
        assessment_lifecycle: AssessmentLifecycleWork,
        planning_lifecycle: PlanningLifecycleWork,
        scope: AuthorizationScope,
        day_id: int,
        payload: dict,
    ) -> ExamDayClosureOutcome: ...

    def reopen_exam_day(
        self,
        service: ExamDayClosureService,
        assessment_lifecycle: AssessmentLifecycleWork,
        planning_lifecycle: PlanningLifecycleWork,
        scope: AuthorizationScope,
        day_id: int,
        payload: dict,
    ) -> ExamDayClosureOutcome: ...

    def close_exam_round(
        self,
        service: ExamRoundLifecycleService,
        assessment_lifecycle: AssessmentLifecycleWork,
        planning_lifecycle: PlanningLifecycleWork,
        scope: AuthorizationScope,
        round_id: int,
        payload: dict,
    ) -> ExamRoundDecisionOutcome: ...

    def cancel_exam_round(
        self,
        service: ExamRoundLifecycleService,
        assessment_lifecycle: AssessmentLifecycleWork,
        planning_lifecycle: PlanningLifecycleWork,
        scope: AuthorizationScope,
        round_id: int,
        payload: dict,
    ) -> ExamRoundDecisionOutcome: ...

    def reopen_exam_round(
        self,
        service: ExamRoundLifecycleService,
        assessment_lifecycle: AssessmentLifecycleWork,
        planning_lifecycle: PlanningLifecycleWork,
        scope: AuthorizationScope,
        round_id: int,
        payload: dict,
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


class ExamLifecycleUnitOfWorkFactory(Protocol):
    """Open the common write boundary owned by Application."""

    def __call__(self) -> AbstractContextManager[ExamLifecycleUnitOfWork]: ...
