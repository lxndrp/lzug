"""Application orchestration for cross-domain exam lifecycle commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.application.exam_lifecycle_ports import ExamLifecycleUnitOfWorkFactory
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.identity.authorization import AuthorizationScope


class ExamLifecycleApplication:
    """Own the shared commit boundary and post-commit effects for lifecycle commands."""

    def __init__(
        self,
        unit_of_work_factory: ExamLifecycleUnitOfWorkFactory,
        day_closure_service_factory: Callable[[], ExamDayClosureService],
        round_lifecycle_service_factory: Callable[[], ExamRoundLifecycleService] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._day_closure_service_factory = day_closure_service_factory
        self._round_lifecycle_service_factory = round_lifecycle_service_factory

    def close_exam_day(
        self, scope: AuthorizationScope, day_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            outcome = unit_of_work.execution.close_exam_day(
                service,
                unit_of_work.assessment_lifecycle,
                unit_of_work.planning_lifecycle,
                scope,
                day_id,
                payload,
            )
        service.publish_close_notifications(outcome)
        return outcome.response

    def reopen_exam_day(
        self, scope: AuthorizationScope, day_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            outcome = unit_of_work.execution.reopen_exam_day(
                service,
                unit_of_work.assessment_lifecycle,
                unit_of_work.planning_lifecycle,
                scope,
                day_id,
                payload,
            )
        service.publish_reopening_notifications(outcome)
        return outcome.response

    def close_exam_round(
        self,
        scope: AuthorizationScope,
        round_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._decide_exam_round(scope, round_id, payload, "close")

    def cancel_exam_round(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._decide_exam_round(scope, round_id, payload, "cancel")

    def _decide_exam_round(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any], decision_type: str
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            decision = (
                unit_of_work.execution.close_exam_round
                if decision_type == "close"
                else unit_of_work.execution.cancel_exam_round
            )
            outcome = decision(
                service,
                unit_of_work.assessment_lifecycle,
                unit_of_work.planning_lifecycle,
                scope,
                round_id,
                payload,
            )
        service.publish_decision_notifications(outcome)
        return outcome.response

    def reopen_exam_round(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            outcome = unit_of_work.execution.reopen_exam_round(
                service,
                unit_of_work.assessment_lifecycle,
                unit_of_work.planning_lifecycle,
                scope,
                round_id,
                payload,
            )
        service.publish_decision_notifications(outcome)
        return outcome.response
