"""Application orchestration for cross-domain exam lifecycle commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from backend.application.exam_lifecycle_contracts import (
    DayCloseCommand,
    DayClosureFacts,
    DayReopenCommand,
    RoundDecisionCommand,
    RoundIhkStatusCommand,
    RoundLifecycleFacts,
    RoundReopenCommand,
)
from backend.application.exam_lifecycle_ports import (
    ExamLifecycleUnitOfWork,
    ExamLifecycleUnitOfWorkFactory,
)
from backend.execution.day_closure_policy import day_closure_view
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.execution.lifecycle_ports import MutationLockCommand, MutationLockKind
from backend.execution.round_lifecycle_view import round_lifecycle_view
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

    def get_exam_day_closure(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any] | None:
        with self._unit_of_work_factory.read_scope() as unit_of_work:
            round_id = unit_of_work.execution.exam_day_round_id(day_id)
            if round_id is None:
                return None
            committee_id = unit_of_work.planning_lifecycle.round_committee_id(round_id)
            if committee_id is None or not scope.can_read_committee(committee_id):
                raise PermissionError("Forbidden.")
            facts = self._day_closure_facts(unit_of_work, day_id, round_id, committee_id)
            return day_closure_view(
                scope, facts, unit_of_work.execution.day_closure_read_snapshot(day_id)
            )

    def get_exam_round_lifecycle(
        self, scope: AuthorizationScope, round_id: int
    ) -> dict[str, Any] | None:
        with self._unit_of_work_factory.read_scope() as unit_of_work:
            exam_round = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(round_id)
            if exam_round is None:
                return None
            if not scope.can_read_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            pending_consequence_ids = unit_of_work.consequences.pending_ids_for_round(round_id)
            facts = self._round_facts(unit_of_work, round_id, exam_round=exam_round)
            snapshot = unit_of_work.execution.round_lifecycle_read_snapshot(round_id)
            return round_lifecycle_view(scope, facts, pending_consequence_ids, snapshot)

    def assert_mutation_allowed(self, command: MutationLockCommand) -> None:
        """Apply the shared lifecycle lock through the configured Execution boundary."""
        service = self._round_lifecycle_service()
        with self._unit_of_work_factory.read_scope() as unit_of_work:
            unit_of_work.execution.assert_mutation_allowed(service, command)

    def assert_mutation_allowed_in_session(self, session, command: MutationLockCommand) -> None:
        """Check a domain mutation lock in the caller's existing write transaction."""
        service = self._round_lifecycle_service()
        service.assert_mutation_allowed_in_session(session, command)

    def set_exam_round_candidate_terminal_status(
        self, scope: AuthorizationScope, round_id: int, candidate_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        service = self._round_lifecycle_service()
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.execution.assert_mutation_allowed(
                service,
                MutationLockCommand(MutationLockKind.ROUND_CANDIDATE, candidate_id, payload),
            )
            unit_of_work.execution.set_round_candidate_terminal_status(
                service, scope, round_id, candidate_id, payload
            )
            response = self._read_round_lifecycle_response(unit_of_work, scope, round_id)
        return response

    def document_exam_round_ihk_status(
        self, scope: AuthorizationScope, round_id: int, result_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self._unit_of_work_factory() as unit_of_work:
            exam_round = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(round_id)
            if exam_round is None:
                raise ValueError("Prüfungsrunde nicht gefunden")
            actor_id = scope.member_for_committee(exam_round.committee_id)
            if actor_id is None or not scope.can_manage_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            result = unit_of_work.assessment.queries.result_by_id(result_id)
            if result is None or result["round_id"] != round_id:
                raise ValueError("Ergebnis gehört nicht zur Prüfungsrunde")
            command = RoundIhkStatusCommand(
                round_id=round_id,
                result_id=result_id,
                document_status=payload.get("document_status"),
                document_reference=payload.get("document_reference"),
                actor_member_id=actor_id,
            )
            unit_of_work.assessment.repository.record_ihk_status(
                round_id=command.round_id,
                result_id=command.result_id,
                document_status=command.document_status,
                document_reference=command.document_reference,
                actor_member_id=command.actor_member_id,
            )
            response = self._read_round_lifecycle_response(unit_of_work, scope, round_id)
        return response

    def delete_empty_exam_round_draft(self, scope: AuthorizationScope, round_id: int) -> bool:
        service = self._round_lifecycle_service()
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.execution.assert_mutation_allowed(
                service,
                MutationLockCommand(MutationLockKind.EXAM_ROUND, round_id, {}),
            )
            return unit_of_work.execution.delete_empty_draft_round(service, scope, round_id)

    def export_exam_round(
        self, scope: AuthorizationScope, round_id: int, *, human: bool
    ) -> dict[str, Any] | str:
        service = self._round_lifecycle_service()
        with self._unit_of_work_factory() as unit_of_work:
            exam_round = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(round_id)
            if exam_round is None:
                raise ValueError("Prüfungsrunde nicht gefunden")
            if not scope.can_read_committee(exam_round.committee_id):
                raise PermissionError("Forbidden.")
            facts = self._round_facts(unit_of_work, round_id, exam_round=exam_round)
            pending_consequence_ids = unit_of_work.consequences.pending_ids_for_round(round_id)
            return unit_of_work.execution.export_round(
                service,
                scope,
                round_id,
                human=human,
                facts=facts,
                pending_consequence_ids=pending_consequence_ids,
            )

    def export_exam_day(
        self, scope: AuthorizationScope, day_id: int, *, human: bool
    ) -> dict[str, Any] | str:
        service = self._day_closure_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            round_id = unit_of_work.execution.exam_day_round_id(day_id)
            if round_id is None:
                raise ValueError("Prüfungstag nicht gefunden")
            facts = self._day_closure_facts(unit_of_work, day_id, round_id)
            snapshot = unit_of_work.execution.record_day_export(
                scope, day_id, human=human, facts=facts
            )
            return service.export_from_read_snapshot(scope, facts, snapshot, human=human)

    def _round_lifecycle_service(self) -> ExamRoundLifecycleService:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        return self._round_lifecycle_service_factory()

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
            facts = self._day_closure_facts(unit_of_work, day_id, round_id, committee_id)
            intent = unit_of_work.execution.evaluate_day_close(
                service, scope, day_id, command, facts
            )
            outcome = unit_of_work.execution.apply_day_close(service, scope, intent, facts)
            response = day_closure_view(
                scope, facts, unit_of_work.execution.day_closure_read_snapshot(day_id)
            )
            if response is None:
                raise RuntimeError("Closed exam day disappeared before its response was read")
        service.publish_close_notifications(outcome)
        return response

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
            facts = self._day_closure_facts(unit_of_work, day_id, round_id, committee_id)
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
            facts = self._day_closure_facts(unit_of_work, day_id, round_id, committee_id)
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
                facts = replace(
                    facts,
                    assessment_completion=unit_of_work.assessment_lifecycle.day_completion(day_id),
                )
                outcome = unit_of_work.execution.complete_day_reopen(
                    service, scope, handle, facts, corrections
                )
            response = day_closure_view(
                scope, facts, unit_of_work.execution.day_closure_read_snapshot(day_id)
            )
            if response is None:
                raise RuntimeError("Reopened exam day disappeared before its response was read")
        service.publish_reopening_notifications(outcome)
        return response

    @staticmethod
    def _day_closure_facts(
        unit_of_work: ExamLifecycleUnitOfWork,
        day_id: int,
        round_id: int,
        committee_id: int | None = None,
    ) -> DayClosureFacts:
        if committee_id is None:
            committee_id = unit_of_work.planning_lifecycle.round_committee_id(round_id)
        if committee_id is None:
            raise PermissionError("Forbidden.")
        slots, assignments = unit_of_work.planning_lifecycle.exam_day_plan(day_id)
        completed_slot_ids = tuple(
            item.id for item in slots if item.execution_status == "completed"
        )
        examiner_ids = tuple(
            sorted(
                {
                    item.committee_member_id
                    for item in assignments
                    if item.assignment_role == "examiner"
                }
            )
        )
        results = tuple(
            unit_of_work.assessment_lifecycle.results_for_day_slots(
                day_id, tuple(item.id for item in slots)
            )
        )
        result_ids = {item["id"] for item in results}
        protocol_day_snapshot = unit_of_work.execution.protocol_day_snapshot(day_id)
        if protocol_day_snapshot is None:
            raise ValueError("Prüfungstag nicht gefunden")
        return DayClosureFacts(
            committee_id=committee_id,
            slots=tuple(slots),
            assignments=tuple(assignments),
            members=tuple(unit_of_work.identity_lifecycle.committee_members_by_ids(examiner_ids)),
            assessment_completion=unit_of_work.assessment_lifecycle.day_completion(day_id),
            management_member_ids=frozenset(
                unit_of_work.identity_lifecycle.management_member_ids(committee_id)
            ),
            assessment_results=results,
            assessment_impacts=tuple(
                unit_of_work.assessment_lifecycle.result_reopening_impacts(result_ids)
            ),
            candidate_attendance=unit_of_work.execution.candidate_attendance_for_slots(
                completed_slot_ids
            ),
            member_attendance=unit_of_work.execution.member_attendance_for_day(
                day_id, examiner_ids
            ),
            absences=tuple(unit_of_work.execution.absence_reports_for_day(day_id)),
            protocol_day_snapshot=protocol_day_snapshot,
        )

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
                    facts = self._round_facts(unit_of_work, round_id)
                    intent = unit_of_work.execution.refresh_round_decision_snapshot(
                        service, intent, facts
                    )
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
            response = self._read_round_lifecycle_response(unit_of_work, scope, round_id)
        service.publish_decision_notifications(outcome)
        return response

    @staticmethod
    def _round_facts(unit_of_work, round_id: int, *, exam_round=None) -> RoundLifecycleFacts:
        planning = unit_of_work.planning_lifecycle
        exam_round = exam_round or planning.round_lifecycle_snapshot(round_id)
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
            response = self._read_round_lifecycle_response(unit_of_work, scope, round_id)
        service.publish_decision_notifications(outcome)
        return response

    def _read_round_lifecycle_response(
        self,
        unit_of_work,
        scope: AuthorizationScope,
        round_id: int,
    ) -> dict[str, Any]:
        exam_round = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(round_id)
        if exam_round is None:
            raise RuntimeError("Exam round disappeared before its lifecycle response was read")
        facts = self._round_facts(unit_of_work, round_id, exam_round=exam_round)
        pending_consequence_ids = unit_of_work.consequences.pending_ids_for_round(round_id)
        snapshot = unit_of_work.execution.round_lifecycle_read_snapshot(round_id)
        response = round_lifecycle_view(scope, facts, pending_consequence_ids, snapshot)
        if response is None:
            raise RuntimeError("Exam round disappeared before its lifecycle response was read")
        return response

    def round_reopening_impact(
        self, scope: AuthorizationScope, round_id: int, raw_scope: Any
    ) -> dict[str, Any]:
        if self._round_lifecycle_service_factory is None:
            raise RuntimeError("Round lifecycle service factory is not configured")
        service = self._round_lifecycle_service_factory()
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._round_facts(unit_of_work, round_id)
            return unit_of_work.execution.round_reopening_impact(service, scope, facts, raw_scope)
