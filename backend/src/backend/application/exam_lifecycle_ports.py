"""Application-owned transaction boundary for exam lifecycle commands."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from backend.application.consequence_ports import LifecycleConsequenceReadPort
from backend.application.exam_lifecycle_contracts import (
    DayClosureFacts,
    DayReopeningHandle,
    RoundLifecycleFacts,
)
from backend.assessment.ports import AssessmentUnitOfWork
from backend.execution.day_closure_snapshot import ExamDayClosureReadSnapshot
from backend.execution.day_lifecycle_contracts import (
    ExamDayClosureIntent,
    ExamDayLifecycleSnapshot,
    ExamDayReopeningIntent,
)
from backend.execution.exam_round_lifecycle import (
    ExamRoundDecisionIntent,
    ExamRoundReopeningIntent,
)
from backend.execution.lifecycle_ports import (
    AssessmentLifecycleWork,
    CalendarLifecycleWork,
    IdentityLifecycleWork,
    MutationLockCommand,
    PlanningLifecycleWork,
)
from backend.execution.protocol_ports import ProtocolDaySnapshot
from backend.execution.round_lifecycle_snapshot import (
    ExamRoundLifecycleExportSnapshot,
    ExamRoundLifecycleReadSnapshot,
)
from backend.execution.slot_ports import ExecutionUnitOfWork
from backend.identity.authorization import AuthorizationScope


class ExamLifecycleExecutionUnitOfWork(ExecutionUnitOfWork, Protocol):
    """Execution capabilities required by Application lifecycle commands."""

    def assert_mutation_allowed(self, command: MutationLockCommand) -> None: ...

    def day_closure_read_snapshot(self, day_id: int) -> ExamDayClosureReadSnapshot | None: ...

    def day_lifecycle_snapshot(self, day_id: int) -> ExamDayLifecycleSnapshot | None: ...

    def round_lifecycle_read_snapshot(
        self, round_id: int
    ) -> ExamRoundLifecycleReadSnapshot | None: ...

    def round_lifecycle_export_snapshot(
        self, round_id: int
    ) -> ExamRoundLifecycleExportSnapshot: ...

    def lifecycle_dependency_counts(self, round_id: int) -> dict[str, int]: ...

    def record_round_export(
        self,
        round_id: int,
        actor_member_id: int,
        *,
        human: bool,
        facts: RoundLifecycleFacts,
    ) -> tuple[ExamRoundLifecycleReadSnapshot, ExamRoundLifecycleExportSnapshot, dict]: ...

    def record_day_export(
        self,
        scope: AuthorizationScope,
        day_id: int,
        *,
        human: bool,
        facts: DayClosureFacts,
    ) -> ExamDayClosureReadSnapshot: ...

    def exam_day_round_id(self, day_id: int) -> int | None: ...

    def exam_day_ids_for_round(self, round_id: int) -> tuple[int, ...]: ...

    def protocol_day_snapshot(self, day_id: int) -> ProtocolDaySnapshot | None: ...

    def apply_day_close(
        self,
        intent: ExamDayClosureIntent,
    ) -> dict[str, object]: ...

    def begin_day_reopen(self, intent: ExamDayReopeningIntent) -> dict[str, object]: ...

    def complete_day_reopen(
        self,
        handle: DayReopeningHandle,
        facts: DayClosureFacts,
        assessment_corrections: dict[int, dict],
    ) -> dict[str, object]: ...

    def apply_round_decision(
        self,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
        cancelled_recipients: set[int],
    ) -> dict[str, object]: ...

    def apply_round_reopen(
        self,
        intent: ExamRoundReopeningIntent,
        facts: RoundLifecycleFacts,
    ) -> dict[str, object]: ...


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
