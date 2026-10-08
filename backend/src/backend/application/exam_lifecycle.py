"""Application orchestration for cross-domain exam lifecycle commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.application.exam_lifecycle_ports import ExamLifecycleUnitOfWorkFactory
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.identity.authorization import AuthorizationScope
from backend.lifecycle_ports import (
    DayCloseCommand,
    DayClosureFacts,
    DayReopenCommand,
    RoundDecisionCommand,
    RoundLifecycleFacts,
    RoundReopenCommand,
)


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
        self, scope: AuthorizationScope, day_id: int, command: DayCloseCommand
    ) -> dict[str, Any]:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            round_id = unit_of_work.execution.exam_day_round_id(day_id)
            if round_id is None:
                raise ValueError("Prüfungstag nicht gefunden")
            committee_id = unit_of_work.planning_lifecycle.round_committee_id(round_id)
            if committee_id is None:
                raise PermissionError("Forbidden.")
            slots, assignments = unit_of_work.planning_lifecycle.exam_day_plan(day_id)
            member_ids = sorted(
                {
                    item.committee_member_id
                    for item in assignments
                    if item.assignment_role == "examiner"
                }
            )
            facts = DayClosureFacts(
                committee_id=committee_id,
                slots=tuple(slots),
                assignments=tuple(assignments),
                members=tuple(unit_of_work.identity_lifecycle.committee_members_by_ids(member_ids)),
                assessment_completion=unit_of_work.assessment_lifecycle.day_completion(day_id),
            )
            intent = unit_of_work.execution.evaluate_day_close(
                service, scope, day_id, command, facts
            )
            outcome = unit_of_work.execution.apply_day_close(service, scope, intent, facts)
        service.publish_close_notifications(outcome)
        return outcome.response

    def day_reopening_impact(
        self, scope: AuthorizationScope, day_id: int, raw_scope: Any
    ) -> dict[str, Any]:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            round_id = unit_of_work.execution.exam_day_round_id(day_id)
            if round_id is None:
                raise ValueError("Prüfungstag nicht gefunden")
            committee_id = unit_of_work.planning_lifecycle.round_committee_id(round_id)
            if committee_id is None:
                raise PermissionError("Forbidden.")
            slots, assignments = unit_of_work.planning_lifecycle.exam_day_plan(day_id)
            slot_ids = tuple(item.id for item in slots)
            results = tuple(
                unit_of_work.assessment_lifecycle.results_for_day_slots(day_id, slot_ids)
            )
            result_ids = {item["id"] for item in results}
            members = tuple(
                unit_of_work.identity_lifecycle.committee_members_by_ids(
                    sorted(
                        {
                            item.committee_member_id
                            for item in assignments
                            if item.assignment_role == "examiner"
                        }
                    )
                )
            )
            facts = DayClosureFacts(
                committee_id=committee_id,
                slots=tuple(slots),
                assignments=tuple(assignments),
                members=members,
                assessment_completion=unit_of_work.assessment_lifecycle.day_completion(day_id),
                assessment_results=results,
                assessment_impacts=tuple(
                    unit_of_work.assessment_lifecycle.result_reopening_impacts(result_ids)
                ),
            )
            return unit_of_work.execution.day_reopening_impact(
                service, scope, day_id, raw_scope, facts
            )

    def reopen_exam_day(
        self, scope: AuthorizationScope, day_id: int, command: DayReopenCommand
    ) -> dict[str, Any]:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            round_id = unit_of_work.execution.exam_day_round_id(day_id)
            if round_id is None:
                raise ValueError("Prüfungstag nicht gefunden")
            committee_id = unit_of_work.planning_lifecycle.round_committee_id(round_id)
            if committee_id is None:
                raise PermissionError("Forbidden.")
            slots, assignments = unit_of_work.planning_lifecycle.exam_day_plan(day_id)
            slot_ids = tuple(item.id for item in slots)
            assessment_results = tuple(
                unit_of_work.assessment_lifecycle.results_for_day_slots(day_id, slot_ids)
            )
            result_ids = {item["id"] for item in assessment_results}
            facts = DayClosureFacts(
                committee_id=committee_id,
                slots=tuple(slots),
                assignments=tuple(assignments),
                members=tuple(
                    unit_of_work.identity_lifecycle.committee_members_by_ids(
                        sorted(
                            {
                                item.committee_member_id
                                for item in assignments
                                if item.assignment_role == "examiner"
                            }
                        )
                    )
                ),
                assessment_completion=unit_of_work.assessment_lifecycle.day_completion(day_id),
                assessment_results=assessment_results,
                assessment_impacts=tuple(
                    unit_of_work.assessment_lifecycle.result_reopening_impacts(result_ids)
                ),
            )
            intent = unit_of_work.execution.evaluate_day_reopen(
                service, scope, day_id, command, facts
            )
            if intent.replayed:
                outcome = unit_of_work.execution.replay_day_reopen(service, scope, intent, facts)
            else:
                handle = unit_of_work.execution.begin_day_reopen(service, intent)
                corrections = {
                    result_id: unit_of_work.assessment_lifecycle.open_result_correction(
                        result_id=result_id,
                        reopening_id=handle.reopening_id,
                        actor_member_id=intent.actor_member_id,
                        reason=intent.reason,
                        requested_at=handle.now,
                    )
                    for result_id in intent.impact["impacts"]["exam_result_ids"]
                }
                outcome = unit_of_work.execution.complete_day_reopen(
                    service, scope, handle, facts, corrections
                )
        service.publish_reopening_notifications(outcome)
        return outcome.response

    def close_exam_round(
        self,
        scope: AuthorizationScope,
        round_id: int,
        command: RoundDecisionCommand,
    ) -> dict[str, Any]:
        return self._decide_exam_round(scope, round_id, command, "close")

    def cancel_exam_round(
        self, scope: AuthorizationScope, round_id: int, command: RoundDecisionCommand
    ) -> dict[str, Any]:
        return self._decide_exam_round(scope, round_id, command, "cancel")

    def _decide_exam_round(
        self,
        scope: AuthorizationScope,
        round_id: int,
        command: RoundDecisionCommand,
        decision_type: str,
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._round_facts(unit_of_work, round_id)
            intent = unit_of_work.execution.evaluate_round_decision(
                service, scope, command, decision_type, facts
            )
            if intent.replayed:
                outcome = unit_of_work.execution.replay_round_decision(
                    service, scope, intent, facts
                )
            else:
                lifecycle_status = "closed" if decision_type == "close" else "cancelled"
                if not unit_of_work.planning_lifecycle.advance_round_lifecycle(
                    round_id, command.revision, intent.now, lifecycle_status=lifecycle_status
                ):
                    from backend.execution.exam_round_lifecycle import ExamRoundConflictError

                    raise ExamRoundConflictError(
                        "Die Prüfungsrunde wurde zwischenzeitlich geändert"
                    )
                recipients: set[int] = set()
                if decision_type == "cancel":
                    unit_of_work.planning_lifecycle.cancel_exam_day_slots(facts.day_ids, intent.now)
                    recipients.update(facts.management_member_ids)
                    recipients.update(item.committee_member_id for item in facts.assignments)
                    recipients.update(
                        unit_of_work.calendar_lifecycle.cancel_future_round_events(
                            round_id, intent.now[:10], intent.now
                        )
                    )
                outcome = unit_of_work.execution.apply_round_decision(
                    service, scope, intent, facts, recipients
                )
        service.publish_decision_notifications(outcome)
        return outcome.response

    @staticmethod
    def _round_facts(unit_of_work, round_id: int) -> RoundLifecycleFacts:
        planning = unit_of_work.planning_lifecycle
        exam_round = planning.round_lifecycle_snapshot(round_id)
        if exam_round is None:
            raise ValueError("Prüfungsrunde nicht gefunden")
        day_ids = tuple(unit_of_work.execution.exam_day_ids_for_round(round_id))
        candidates = tuple(planning.round_candidates(round_id))
        candidate_ids = tuple(item["candidate_id"] for item in candidates)
        planning_context = planning.lifecycle_context(
            round_id, exam_round.exam_half_year_id, candidate_ids
        )
        slots = tuple(planning.exam_day_slots(day_ids))
        assignments = tuple(planning.exam_day_assignments(day_ids))
        committee = unit_of_work.identity_lifecycle.committee(exam_round.committee_id)
        if committee is None:
            raise PermissionError("Forbidden.")
        return RoundLifecycleFacts(
            round=exam_round,
            day_ids=day_ids,
            candidates=candidates,
            candidate_details=tuple(planning.candidate_details(candidate_ids)),
            planning_context=planning_context,
            slots=slots,
            assignments=assignments,
            assessment_results=tuple(unit_of_work.assessment_lifecycle.results_for_round(round_id)),
            committee=committee,
            members=tuple(
                unit_of_work.identity_lifecycle.committee_members(exam_round.committee_id)
            ),
            management_member_ids=frozenset(
                unit_of_work.identity_lifecycle.management_member_ids(exam_round.committee_id)
            ),
        )

    def reopen_exam_round(
        self, scope: AuthorizationScope, round_id: int, command: RoundReopenCommand
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._round_facts(unit_of_work, round_id)
            intent = unit_of_work.execution.evaluate_round_reopen(service, scope, command, facts)
            if intent.replayed:
                outcome = unit_of_work.execution.replay_round_reopen(service, scope, intent, facts)
            else:
                from backend.execution.exam_round_lifecycle import ExamRoundConflictError

                if not unit_of_work.planning_lifecycle.advance_round_lifecycle(
                    round_id, command.revision, intent.now, lifecycle_status="reopening"
                ):
                    raise ExamRoundConflictError(
                        "Die Prüfungsrunde wurde zwischenzeitlich geändert"
                    )
                outcome = unit_of_work.execution.apply_round_reopen(service, scope, intent, facts)
        service.publish_decision_notifications(outcome)
        return outcome.response

    def round_reopening_impact(
        self, scope: AuthorizationScope, round_id: int, raw_scope: Any
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._round_facts(unit_of_work, round_id)
            return unit_of_work.execution.round_reopening_impact(service, scope, facts, raw_scope)
