"""Revision-bound lifecycle, history, locking, and exports for exam rounds."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.execution.lifecycle_ports import (
    AssessmentLifecycleWork,
    AssessmentLifecycleWorkFactory,
    CalendarLifecycleWorkFactory,
    IdentityLifecycleWork,
    IdentityLifecycleWorkFactory,
    PlanningLifecycleWork,
    PlanningLifecycleWorkFactory,
    PlanningRoundLifecycleSnapshot,
    RoundDecisionCommand,
    RoundLifecycleFacts,
    RoundReopenCommand,
)
from backend.identity.authorization import AuthorizationScope
from backend.notifications.service import NotificationService
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.models import (
    AbsenceReport,
    ExamDay,
    ExamDayClosure,
    ExamDayTask,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolRetention,
    ExamProtocolRevision,
    ExamRoundAuditEvent,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundIhkStatus,
    ExamRoundReopening,
    ExamRoundTask,
)
from backend.presentation.exam_exports import render_round_lifecycle_export

TERMINAL_LIFECYCLE_STATUSES = {"closed", "cancelled", "historical"}
TERMINAL_CANDIDATE_STATUSES = {
    "result_communicated",
    "transferred",
    "postponed",
    "ihk_terminated",
}
REOPENING_SCOPE_KINDS = {
    "candidate_assignment",
    "availability",
    "planning",
    "exam_day",
    "absence",
    "exam_protocol",
    "exam_result",
}
TERMINAL_ABSENCE_STATUSES = {
    "replacement_selected",
    "resolved",
    "withdrawn",
    "exam_day_cancelled",
}


class ExamRoundConflictError(ValueError):
    """Signal a stale, duplicate-different, or parallel lifecycle command."""


class ExamRoundValidationError(ValueError):
    """Expose the complete failed prerequisite matrix for one decision."""

    def __init__(self, message: str, findings: list[dict[str, Any]]):
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class ExamRoundDecisionOutcome:
    """Decision response and deferred cancellation notification input."""

    response: dict[str, Any]
    committee_id: int | None = None
    round_id: int | None = None
    recipient_member_ids: frozenset[int] = frozenset()
    title: str = ""
    message: str = ""
    origin_key: str = ""


@dataclass(frozen=True)
class ExamRoundDecisionIntent:
    round_id: int
    expected_revision: int
    decision_type: str
    reason: str | None
    command_fingerprint: str
    actor_member_id: int
    committee_id: int
    lifecycle_status: str
    reopening_id: int | None
    evaluation: dict[str, Any]
    snapshot: dict[str, Any]
    now: str
    replayed: bool = False


@dataclass(frozen=True)
class ExamRoundReopeningIntent:
    round_id: int
    expected_revision: int
    command_fingerprint: str
    actor_member_id: int
    reason: str
    occasion: str
    source: str
    impact: dict[str, Any]
    previous_decision_id: int | None
    now: str
    replayed: bool = False


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _token(kind: str, entity_id: int) -> str:
    return f"{kind}:{entity_id}"


class ExamRoundLifecycleService:
    """Open, close, cancel, reopen, trace, lock, and export one exam round."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        notification_service: NotificationService,
        assessment_lifecycle_factory: AssessmentLifecycleWorkFactory,
        planning_lifecycle_work_factory: PlanningLifecycleWorkFactory,
        identity_lifecycle_work_factory: IdentityLifecycleWorkFactory,
        calendar_lifecycle_work_factory: CalendarLifecycleWorkFactory,
    ) -> None:
        self.db_path = db_path
        self.notification_service = notification_service
        self.assessment_lifecycle_factory = assessment_lifecycle_factory
        self.planning_lifecycle_work_factory = planning_lifecycle_work_factory
        self.identity_lifecycle_work_factory = identity_lifecycle_work_factory
        self.calendar_lifecycle_work_factory = calendar_lifecycle_work_factory

    def get(self, scope: AuthorizationScope, round_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = planning.round_lifecycle_snapshot(round_id)
            if exam_round is None:
                return None
            self._require_access(exam_round, scope)
            return self._view(session, exam_round, scope, planning_work=planning)

    def publish_decision_notifications(self, outcome: ExamRoundDecisionOutcome) -> None:
        """Publish cancellation notices only after the caller has committed."""
        if (
            outcome.committee_id is not None
            and outcome.round_id is not None
            and outcome.recipient_member_ids
        ):
            self._notify(
                outcome.committee_id,
                outcome.round_id,
                set(outcome.recipient_member_ids),
                outcome.title,
                outcome.message,
                outcome.origin_key,
            )

    def evaluate_decision_intent(
        self,
        session: Session,
        scope: AuthorizationScope,
        command: RoundDecisionCommand,
        decision_type: str,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionIntent:
        """Validate a round decision from detached owner facts without mutating state."""
        if not command.confirmed:
            raise ValueError("Die angezeigten Voraussetzungen müssen bestätigt werden")
        reason = (
            self._required_text(command.reason, "reason", 3000)
            if decision_type == "cancel"
            else None
        )
        fingerprint = _fingerprint(
            {
                "decision_type": decision_type,
                "revision": command.revision,
                "confirmed": True,
                "reason": reason,
            }
        )
        exam_round = facts.round
        actor_id = self._require_management(exam_round, scope)
        repeated = session.scalar(
            select(ExamRoundDecision).where(
                ExamRoundDecision.exam_round_id == exam_round.id,
                ExamRoundDecision.command_fingerprint == fingerprint,
            )
        )
        if repeated is not None:
            return ExamRoundDecisionIntent(
                exam_round.id,
                command.revision,
                decision_type,
                reason,
                fingerprint,
                actor_id,
                exam_round.committee_id,
                exam_round.lifecycle_status,
                None,
                {},
                {},
                _now(),
                True,
            )
        reopening, evaluation = self._decision_prerequisites(
            session, exam_round, command.revision, decision_type, facts=facts
        )
        return ExamRoundDecisionIntent(
            exam_round.id,
            command.revision,
            decision_type,
            reason,
            fingerprint,
            actor_id,
            exam_round.committee_id,
            exam_round.lifecycle_status,
            reopening.id if reopening else None,
            evaluation,
            self._snapshot(session, exam_round, facts=facts),
            _now(),
            False,
        )

    def replay_decision_intent(
        self,
        session: Session,
        scope: AuthorizationScope,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionOutcome:
        return ExamRoundDecisionOutcome(self._view(session, facts.round, scope, facts=facts))

    def refresh_decision_snapshot(
        self,
        session: Session,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionIntent:
        """Rebuild the persisted decision snapshot from post-Planning mutation facts."""
        return replace(intent, snapshot=self._snapshot(session, facts.round, facts=facts))

    def evaluate_reopen_intent(
        self,
        session: Session,
        scope: AuthorizationScope,
        command: RoundReopenCommand,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundReopeningIntent:
        occasion = self._required_text(command.occasion, "occasion", 1000)
        source = self._required_text(command.source, "source", 1000)
        reason = self._required_text(command.reason, "reason", 3000)
        requested_scope = self._normalize_scope([item.payload() for item in command.scope])
        fingerprint = _fingerprint(
            {
                "revision": command.revision,
                "occasion": occasion,
                "source": source,
                "reason": reason,
                "scope": requested_scope,
            }
        )
        exam_round = facts.round
        actor_id = self._require_management(exam_round, scope)
        repeated = session.scalar(
            select(ExamRoundReopening).where(
                ExamRoundReopening.exam_round_id == exam_round.id,
                ExamRoundReopening.command_fingerprint == fingerprint,
            )
        )
        if repeated is not None:
            previous = self._current_or_latest_decision(session, exam_round.id)
            return ExamRoundReopeningIntent(
                exam_round.id,
                command.revision,
                fingerprint,
                actor_id,
                reason,
                occasion,
                source,
                {},
                previous.id if previous else None,
                _now(),
                True,
            )
        impact = self._reopening_prerequisites(
            session,
            exam_round,
            command.revision,
            [item.payload() for item in command.scope],
            facts=facts,
        )
        previous = self._current_or_latest_decision(session, exam_round.id)
        return ExamRoundReopeningIntent(
            exam_round.id,
            command.revision,
            fingerprint,
            actor_id,
            reason,
            occasion,
            source,
            impact,
            previous.id if previous else None,
            _now(),
            False,
        )

    def replay_reopen_intent(self, session, scope, intent, facts):
        return ExamRoundDecisionOutcome(self._view(session, facts.round, scope, facts=facts))

    def apply_reopen_intent(self, session, scope, intent, facts):
        previous = self._current_or_latest_decision(session, intent.round_id)
        if previous is not None:
            previous.status = "superseded"
        reopening = ExamRoundReopening(
            exam_round_id=intent.round_id,
            previous_decision_id=previous.id if previous else None,
            requested_revision=intent.expected_revision,
            resulting_revision=intent.expected_revision + 1,
            occasion=intent.occasion,
            source=intent.source,
            reason=intent.reason,
            requested_scope_json=_json(intent.impact["requested_scope"]),
            scope_json=_json(intent.impact["expanded_scope"]),
            impacts_json=_json(intent.impact["impacts"]),
            actor_member_id=intent.actor_member_id,
            status="open",
            command_fingerprint=intent.command_fingerprint,
            opened_at=intent.now,
        )
        session.add(reopening)
        session.flush()
        updated = replace(
            facts.round, revision=intent.expected_revision + 1, lifecycle_status="reopening"
        )
        self._supersede_exports(session, updated, intent.now)
        recipients = self._create_reopening_tasks(
            session, updated, reopening, intent.impact, intent.now, None, facts
        )
        session.add(
            ExamRoundAuditEvent(
                exam_round_id=intent.round_id,
                round_revision=updated.revision,
                event_type="reopened",
                actor_member_id=intent.actor_member_id,
                reopening_id=reopening.id,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json,
                created_at=intent.now,
            )
        )
        return ExamRoundDecisionOutcome(
            response=self._view(session, updated, scope, facts=replace(facts, round=updated)),
            committee_id=intent.impact and updated.committee_id if recipients else None,
            round_id=intent.round_id if recipients else None,
            recipient_member_ids=frozenset(recipients),
            title="Prüfungsrunde zur Korrektur wieder geöffnet" if recipients else "",
            message=(
                "Von Ihnen erfasste oder bestätigte Daten sind von einer begründeten "
                "Korrektur betroffen."
                if recipients
                else ""
            ),
            origin_key=f"exam-round-reopening:{reopening.id}:affected" if recipients else "",
        )

    def apply_decision_intent(
        self,
        session: Session,
        scope: AuthorizationScope,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
        cancelled_recipients: set[int] | None = None,
    ) -> ExamRoundDecisionOutcome:
        """Persist Execution-owned decision, audit, and response after owner mutations."""
        previous = self._current_or_latest_decision(session, intent.round_id)
        if previous is not None:
            previous.status = "superseded"
        reopening = (
            session.get(ExamRoundReopening, intent.reopening_id) if intent.reopening_id else None
        )
        decision = ExamRoundDecision(
            exam_round_id=intent.round_id,
            decision_type=intent.decision_type,
            requested_revision=intent.expected_revision,
            resulting_revision=intent.expected_revision + 1,
            actor_member_id=intent.actor_member_id,
            reason=intent.reason,
            checklist_json=_json(intent.evaluation["items"]),
            snapshot_json=_json(intent.snapshot),
            previous_decision_id=previous.id if previous else None,
            status="current",
            command_fingerprint=intent.command_fingerprint,
            decided_at=intent.now,
        )
        session.add(decision)
        session.flush()
        lifecycle_status = "closed" if intent.decision_type == "close" else "cancelled"
        updated = replace(
            facts.round, revision=intent.expected_revision + 1, lifecycle_status=lifecycle_status
        )
        if intent.decision_type == "cancel":
            for day in session.scalars(
                select(ExamDay).where(ExamDay.exam_round_id == intent.round_id)
            ):
                day.status = "cancelled"
                day.updated_at = intent.now
        self._complete_reopening(session, reopening, intent.now)
        session.add(
            ExamRoundAuditEvent(
                exam_round_id=intent.round_id,
                round_revision=updated.revision,
                event_type=(
                    ("reclosed" if intent.decision_type == "close" else "recancelled")
                    if reopening
                    else lifecycle_status
                ),
                actor_member_id=intent.actor_member_id,
                decision_id=decision.id,
                reopening_id=reopening.id if reopening else None,
                reason=intent.reason,
                scope_json=reopening.requested_scope_json if reopening else "[]",
                created_at=intent.now,
            )
        )
        recipients = cancelled_recipients or set()
        response = self._view(session, updated, scope, facts=replace(facts, round=updated))
        return ExamRoundDecisionOutcome(
            response=response,
            committee_id=intent.committee_id if recipients else None,
            round_id=intent.round_id if recipients else None,
            recipient_member_ids=frozenset(recipients),
            title="Prüfungsrunde abgesagt" if recipients else "",
            message=(
                "Die Prüfungsrunde wurde vollständig und begründet abgesagt." if recipients else ""
            ),
            origin_key=f"exam-round-decision:{decision.id}:cancelled" if recipients else "",
        )

    def _decision_prerequisites(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        expected_revision: int,
        decision_type: str,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> tuple[ExamRoundReopening | None, dict[str, Any]]:
        """Evaluate the current state after replay detection and before any mutation."""
        if exam_round.revision != expected_revision:
            raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
        if exam_round.lifecycle_status not in {"open", "reopening"}:
            raise ExamRoundConflictError("Die Prüfungsrunde ist bereits fachlich beendet")
        reopening = self._active_reopening(session, exam_round.id)
        if exam_round.lifecycle_status == "reopening" and reopening is None:
            raise ExamRoundConflictError("Der Wiederöffnungsstand ist inkonsistent")

        evaluation = self._evaluate(
            session, exam_round, decision_type, assessment_work, planning_work, facts
        )
        if not evaluation["ready"]:
            raise ExamRoundValidationError(
                "Die Voraussetzungen für diesen Rundenstand sind nicht erfüllt",
                [item for item in evaluation["items"] if not item["ok"]],
            )

        return reopening, evaluation

    @staticmethod
    def _complete_reopening(
        session: Session, reopening: ExamRoundReopening | None, now: str
    ) -> None:
        """Complete the correction and its open tasks in the decision transaction."""
        if reopening is not None:
            reopening.status = "completed"
            reopening.completed_at = now
            for task in session.scalars(
                select(ExamRoundTask).where(
                    ExamRoundTask.reopening_id == reopening.id,
                    ExamRoundTask.status == "open",
                )
            ):
                task.status = "completed"
                task.completed_at = now

    def reopening_impact_from_facts(
        self,
        session: Session,
        scope: AuthorizationScope,
        facts: RoundLifecycleFacts,
        raw_scope: Any,
    ) -> dict[str, Any]:
        exam_round = facts.round
        self._require_management(exam_round, scope)
        if exam_round.lifecycle_status not in TERMINAL_LIFECYCLE_STATUSES:
            raise ExamRoundConflictError(
                "Nur eine beendete Prüfungsrunde kann wieder geöffnet werden"
            )
        if self._active_reopening(session, exam_round.id) is not None:
            raise ExamRoundConflictError("Für die Prüfungsrunde läuft bereits eine Wiederöffnung")
        return self._impact(session, exam_round, raw_scope, facts=facts)

    def _reopening_prerequisites(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        expected_revision: int,
        raw_scope: Any,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        """Read and validate correction impact without superseding any current evidence."""
        if exam_round.revision != expected_revision:
            raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
        if exam_round.lifecycle_status not in TERMINAL_LIFECYCLE_STATUSES:
            raise ExamRoundConflictError(
                "Nur eine beendete Prüfungsrunde kann wieder geöffnet werden"
            )
        if self._active_reopening(session, exam_round.id) is not None:
            raise ExamRoundConflictError("Für die Prüfungsrunde läuft bereits eine Wiederöffnung")
        return self._impact(
            session, exam_round, raw_scope, assessment_work, planning_work, facts=facts
        )

    def _create_reopening_tasks(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        reopening: ExamRoundReopening,
        impact: dict[str, Any],
        now: str,
        identity: IdentityLifecycleWork | None,
        facts: RoundLifecycleFacts | None = None,
    ) -> set[int]:
        """Persist reconfirmation and IHK follow-up work with the reopening audit."""
        round_id = exam_round.id
        reason = reopening.reason
        recipients = set(impact["impacts"]["recipient_member_ids"])
        for recipient_id in sorted(recipients):
            session.add(
                ExamRoundTask(
                    exam_round_id=round_id,
                    reopening_id=reopening.id,
                    recipient_member_id=recipient_id,
                    task_type="reconfirmation",
                    origin_key=f"exam-round-reopening:{reopening.id}:affected",
                    details_json=_json({"reason": reason, "scope": impact["expanded_scope"]}),
                    status="open",
                    created_at=now,
                )
            )
        for result_id in impact["impacts"]["ihk_processed_result_ids"]:
            managers = (
                set(facts.management_member_ids)
                if facts is not None
                else self._management_member_ids(session, exam_round, identity)
            )
            for recipient_id in managers:
                session.add(
                    ExamRoundTask(
                        exam_round_id=round_id,
                        reopening_id=reopening.id,
                        recipient_member_id=recipient_id,
                        task_type="ihk_clarification",
                        origin_key=f"exam-round-reopening:{reopening.id}:ihk:{result_id}",
                        details_json=_json({"exam_result_id": result_id, "reason": reason}),
                        status="open",
                        created_at=now,
                    )
                )
        return recipients

    @staticmethod
    def _supersede_exports(
        session: Session, exam_round: PlanningRoundLifecycleSnapshot, now: str
    ) -> None:
        """Mark earlier exports obsolete with the authoritative new revision."""
        for export in session.scalars(
            select(ExamRoundExport).where(
                ExamRoundExport.exam_round_id == exam_round.id,
                ExamRoundExport.superseded_at.is_(None),
            )
        ):
            export.superseded_at = now
            export.superseded_by_revision = exam_round.revision

    def set_candidate_terminal_status(
        self,
        scope: AuthorizationScope,
        round_id: int,
        round_candidate_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        expected_revision = self._required_revision(payload)
        status = payload.get("terminal_status")
        if status not in TERMINAL_CANDIDATE_STATUSES | {"open"}:
            raise ValueError("Unbekannter abschließender Kandidatenstatus")
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = self._required_round(planning, round_id)
            self._require_management(exam_round, scope)
            candidate = planning.round_candidate(round_id, round_candidate_id)
            if candidate is None:
                raise ValueError("Prüfling gehört nicht zur Prüfungsrunde")
            self._require_mutable_scope(
                session, exam_round, _token("candidate_assignment", candidate["id"])
            )
            if exam_round.revision != expected_revision:
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            reason = self._optional_text(payload.get("reason"), 3000)
            target_round_id = payload.get("effective_new_round_id")
            postponed_until = self._optional_text(payload.get("postponed_until"), 100)
            ihk_reference = self._optional_text(payload.get("ihk_decision_reference"), 1000)
            self._require_terminal_details(
                status, reason, target_round_id, postponed_until, ihk_reference
            )
            if status == "result_communicated":
                self._assert_result_communicated(session, candidate)
            elif status == "transferred":
                if not isinstance(target_round_id, int) or isinstance(target_round_id, bool):
                    raise ValueError("Ein Ausschusswechsel benötigt eine wirksame neue Runde")
                self._require_effective_transfer(planning, exam_round, candidate, target_round_id)
            now = _now()
            values = {
                "terminal_status": status,
                "terminal_reason": reason,
                "effective_new_round_id": target_round_id if status == "transferred" else None,
                "postponed_until": postponed_until if status == "postponed" else None,
                "ihk_decision_reference": ihk_reference if status == "ihk_terminated" else None,
                "terminal_at": now if status != "open" else None,
                "updated_at": now,
            }
            ends_assignment = status in {"transferred", "postponed", "ihk_terminated"}
            if ends_assignment:
                values["is_active"] = 0
            if not planning.update_candidate_terminal(
                round_id,
                candidate["id"],
                values,
                ended_at=now if ends_assignment else None,
                change_reason=reason,
            ):
                raise ValueError("Prüfling gehört nicht zur Prüfungsrunde")
            if not planning.advance_round_lifecycle(round_id, expected_revision, now):
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            exam_round = replace(exam_round, revision=exam_round.revision + 1)
            session.flush()
            return self._view(session, exam_round, scope, planning_work=planning)

    @staticmethod
    def _require_terminal_details(
        status: str,
        reason: str | None,
        target_round_id: Any,
        postponed_until: str | None,
        ihk_reference: str | None,
    ) -> None:
        """Decide required terminal evidence without reading or mutating persistence."""
        if status == "transferred":
            if reason is None or not isinstance(target_round_id, int):
                raise ValueError("Ein Ausschusswechsel benötigt Grund und wirksame neue Runde")
        elif status == "postponed":
            if reason is None or postponed_until is None:
                raise ValueError("Eine Verschiebung benötigt Grund und verbindlichen Termin")
        elif status == "ihk_terminated":
            if reason is None or ihk_reference is None:
                raise ValueError("Die IHK-Entscheidung benötigt Grund und Referenz")

    @staticmethod
    def _require_effective_transfer(
        planning: PlanningLifecycleWork,
        exam_round: PlanningRoundLifecycleSnapshot,
        candidate: dict[str, Any],
        target_round_id: int,
    ) -> None:
        """Check the effective target assignment in the terminal transition's transaction."""
        if target_round_id == exam_round.id or not planning.effective_transfer_exists(
            exam_round.exam_half_year_id, target_round_id, candidate["candidate_id"]
        ):
            raise ValueError("Die neue Zuordnung ist nicht wirksam")

    def delete_empty_draft(self, scope: AuthorizationScope, round_id: int) -> bool:
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = planning.round_lifecycle_snapshot(round_id)
            if exam_round is None:
                return False
            self._require_management(exam_round, scope)
            if exam_round.status != "draft" or exam_round.lifecycle_status != "open":
                raise ValueError("Nur eine offene Entwurfsrunde kann gelöscht werden")
            dependencies = self._dependency_counts(session, exam_round, planning)
            present = [name for name, count in dependencies.items() if count]
            if present:
                raise ValueError(
                    "Die Prüfungsrunde besitzt abhängige Fachdaten: " + ", ".join(present)
                )
            if not planning.delete_empty_draft_round(round_id, exam_round.revision):
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            return True

    def machine_export(self, scope: AuthorizationScope, round_id: int) -> dict[str, Any]:
        return self._export(scope, round_id, "machine")

    def human_export(self, scope: AuthorizationScope, round_id: int) -> str:
        export = self._export(scope, round_id, "human")
        lifecycle = export["lifecycle"]
        snapshot = export["snapshot"]
        return render_round_lifecycle_export(round_id, lifecycle, snapshot)

    def document_ihk_status(
        self,
        scope: AuthorizationScope,
        round_id: int,
        result_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        document_status = self._required_text(
            payload.get("document_status"), "document_status", 300
        )
        reference = self._required_text(
            payload.get("document_reference"), "document_reference", 1000
        )
        fingerprint = _fingerprint(
            {
                "round_id": round_id,
                "result_id": result_id,
                "document_status": document_status,
                "document_reference": reference,
            }
        )
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = self._required_round(planning, round_id)
            actor_id = self._require_management(exam_round, scope)
            result = self.assessment_lifecycle_factory(session).result_by_id(result_id)
            if result is None or result["round_id"] != round_id:
                raise ValueError("Ergebnis gehört nicht zur Prüfungsrunde")
            existing = session.scalar(
                select(ExamRoundIhkStatus).where(
                    ExamRoundIhkStatus.command_fingerprint == fingerprint
                )
            )
            if existing is None:
                session.add(
                    ExamRoundIhkStatus(
                        exam_round_id=round_id,
                        exam_result_id=result_id,
                        document_status=document_status,
                        document_reference=reference,
                        recorded_by_member_id=actor_id,
                        command_fingerprint=fingerprint,
                        recorded_at=_now(),
                    )
                )
                session.flush()
            return self._view(session, exam_round, scope)

    def _export(self, scope: AuthorizationScope, round_id: int, export_kind: str) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = self._required_round(planning, round_id)
            actor_id = self._require_access(exam_round, scope)
            if actor_id is None:
                raise PermissionError("Forbidden.")
            decision = self._current_or_latest_decision(session, round_id)
            row = ExamRoundExport(
                exam_round_id=round_id,
                decision_id=decision.id if decision else None,
                round_revision=exam_round.revision,
                export_kind=export_kind,
                lifecycle_status=exam_round.lifecycle_status,
                generated_by_member_id=actor_id,
                generated_at=_now(),
            )
            session.add(row)
            session.flush()
            view = self._view(session, exam_round, scope)
            return {
                "export_version": 1,
                "export": self._export_view(row),
                "lifecycle": view,
                "snapshot": self._snapshot(session, exam_round),
            }

    def assert_mutable(self, round_id: int, kind: str, entity_id: int) -> None:
        """Enforce the shared lock for direct business API mutations."""
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            exam_round = self._required_round(planning, round_id)
            self._require_mutable_scope(session, exam_round, _token(kind, entity_id))

    def assert_http_mutation(
        self, method: str, path_parts: list[str], payload: dict[str, Any]
    ) -> None:
        """Resolve one business HTTP mutation and enforce the round-wide lock."""
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or not path_parts:
            return
        if (
            path_parts[0] == "exam-rounds"
            and len(path_parts) >= 3
            and path_parts[2]
            in {
                "closure",
                "cancellation",
                "reopening-impact",
                "reopenings",
                "candidate-terminal-status",
            }
        ):
            return
        if (
            path_parts[0] == "exam-rounds"
            and len(path_parts) == 5
            and path_parts[2] == "candidates"
            and path_parts[4] == "terminal-status"
        ):
            return
        if (
            path_parts[0] == "exam-rounds"
            and len(path_parts) == 5
            and path_parts[2] == "results"
            and path_parts[4] == "ihk-status"
        ):
            return
        if (
            path_parts[0] in {"exam-protocols", "exam-results"}
            and len(path_parts) == 3
            and path_parts[2] == "retention"
        ):
            return
        with session_scope(self.db_path) as session:
            planning = self.planning_lifecycle_work_factory(session)
            resolved = self._round_mutation_token(session, path_parts, payload)
            if resolved is None:
                return
            round_id, token = resolved
            exam_round = self._required_round(planning, round_id)
            self._require_mutable_scope(session, exam_round, token)

    def _round_mutation_token(
        self, session: Session, path_parts: list[str], payload: dict[str, Any]
    ) -> tuple[int, str] | None:
        resource = path_parts[0]
        identifier = int(path_parts[1]) if len(path_parts) > 1 and path_parts[1].isdigit() else None
        if resource == "exam-rounds":
            if identifier is None:
                return None
            return identifier, _token("planning", identifier)
        if resource == "planning-proposals":
            round_id = payload.get("round_id")
            return (
                (int(round_id), _token("planning", int(round_id)))
                if isinstance(round_id, int) and not isinstance(round_id, bool)
                else None
            )
        if resource in {
            "planning-settings",
            "candidate-exam-days",
            "member-availabilities",
            "round-candidates",
        }:
            target = self.planning_lifecycle_work_factory(session).mutation_target(
                resource, identifier, payload
            )
            if target is None:
                return None
            round_id, entity_id = target
            kind = (
                "availability"
                if resource == "member-availabilities"
                else ("candidate_assignment" if resource == "round-candidates" else "planning")
            )
            return round_id, _token(kind, entity_id)
        if resource == "confirmed-plan-days" and identifier is not None:
            row = session.get(ExamDay, identifier)
            if row is not None:
                return row.exam_round_id, _token("exam_day", identifier)
        if resource == "exam-protocols" and identifier is not None:
            slot_id = session.scalar(
                select(ExamProtocol.exam_slot_id).where(ExamProtocol.id == identifier)
            )
            round_id = (
                self.planning_lifecycle_work_factory(session).round_id_for_slot(slot_id)
                if slot_id is not None
                else None
            )
            return (round_id, _token("exam_protocol", identifier)) if round_id else None
        if resource == "exam-results" and identifier is not None:
            result = self.assessment_lifecycle_factory(session).result_by_id(identifier)
            round_id = result["round_id"] if result is not None else None
            return (round_id, _token("exam_result", identifier)) if round_id else None
        if resource == "absence-reports" and identifier is not None:
            round_id = session.scalar(
                select(ExamDay.exam_round_id)
                .join(AbsenceReport, AbsenceReport.exam_day_id == ExamDay.id)
                .where(AbsenceReport.id == identifier)
            )
            return (round_id, _token("absence", identifier)) if round_id else None
        return None

    def _view(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        scope: AuthorizationScope,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        planning = planning_work or self.planning_lifecycle_work_factory(session)
        actor_id = self._require_access(exam_round, scope)
        decision_rows = list(
            session.scalars(
                select(ExamRoundDecision)
                .where(ExamRoundDecision.exam_round_id == exam_round.id)
                .order_by(ExamRoundDecision.id)
            )
        )
        reopening_rows = list(
            session.scalars(
                select(ExamRoundReopening)
                .where(ExamRoundReopening.exam_round_id == exam_round.id)
                .order_by(ExamRoundReopening.id)
            )
        )
        history = list(
            session.scalars(
                select(ExamRoundAuditEvent)
                .where(ExamRoundAuditEvent.exam_round_id == exam_round.id)
                .order_by(ExamRoundAuditEvent.id)
            )
        )
        tasks = list(
            session.scalars(
                select(ExamRoundTask)
                .where(ExamRoundTask.exam_round_id == exam_round.id)
                .order_by(ExamRoundTask.id)
            )
        )
        exports = list(
            session.scalars(
                select(ExamRoundExport)
                .where(ExamRoundExport.exam_round_id == exam_round.id)
                .order_by(ExamRoundExport.id)
            )
        )
        ihk_statuses = list(
            session.scalars(
                select(ExamRoundIhkStatus)
                .where(ExamRoundIhkStatus.exam_round_id == exam_round.id)
                .order_by(ExamRoundIhkStatus.id)
            )
        )
        round_candidates = (
            facts.round_candidates(exam_round.id)
            if facts is not None
            else planning.round_candidates(exam_round.id)
        )
        return {
            "round_id": exam_round.id,
            "revision": exam_round.revision,
            "status": exam_round.lifecycle_status,
            "legacy_status": exam_round.legacy_status,
            "historical_without_formal_evidence": (
                exam_round.lifecycle_status == "historical" and not decision_rows
            ),
            "evaluation": self._evaluate(
                session, exam_round, "close", assessment_work, planning, facts
            ),
            "candidates": [
                {
                    "round_candidate_id": item["id"],
                    "candidate_id": item["candidate_id"],
                    "terminal_status": item["terminal_status"],
                    "terminal_reason": item["terminal_reason"],
                    "effective_new_round_id": item["effective_new_round_id"],
                    "postponed_until": item["postponed_until"],
                    "ihk_decision_reference": item["ihk_decision_reference"],
                    "terminal_at": item["terminal_at"],
                }
                for item in round_candidates
            ],
            "current_decision": next(
                (self._decision_view(item) for item in decision_rows if item.status == "current"),
                None,
            ),
            "decisions": [self._decision_view(item) for item in decision_rows],
            "reopenings": [self._reopening_view(item) for item in reopening_rows],
            "history": [self._event_view(item) for item in history],
            "tasks": [self._task_view(item) for item in tasks],
            "exports": [self._export_view(item) for item in exports],
            "ihk_statuses": [
                {
                    "id": item.id,
                    "exam_result_id": item.exam_result_id,
                    "document_status": item.document_status,
                    "document_reference": item.document_reference,
                    "recorded_by_member_id": item.recorded_by_member_id,
                    "recorded_at": item.recorded_at,
                }
                for item in ihk_statuses
            ],
            "retention": self._retention_view(
                session, exam_round.id, assessment_work, planning, facts
            ),
            "permissions": {
                "close": scope.can_manage_committee(exam_round.committee_id)
                and exam_round.lifecycle_status in {"open", "reopening"},
                "cancel": scope.can_manage_committee(exam_round.committee_id)
                and exam_round.lifecycle_status in {"open", "reopening"},
                "reopen": scope.can_manage_committee(exam_round.committee_id)
                and exam_round.lifecycle_status in TERMINAL_LIFECYCLE_STATUSES,
                "delete": scope.can_manage_committee(exam_round.committee_id)
                and exam_round.status == "draft"
                and exam_round.lifecycle_status == "open",
                "export": actor_id is not None,
            },
            "_links": {
                "self": {"href": f"/api/exam-rounds/{exam_round.id}/lifecycle"},
                "machine_export": {
                    "href": f"/api/exam-rounds/{exam_round.id}/lifecycle/export.json"
                },
                "human_export": {"href": f"/api/exam-rounds/{exam_round.id}/lifecycle/export.txt"},
            },
        }

    def _evaluate(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        decision_type: str,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        planning = planning_work or self.planning_lifecycle_work_factory(session)
        items: list[dict[str, Any]] = []
        days = list(session.scalars(select(ExamDay).where(ExamDay.exam_round_id == exam_round.id)))
        day_ids = list(facts.day_ids) if facts is not None else [item.id for item in days]
        slots = (
            facts.exam_day_slots(day_ids) if facts is not None else planning.exam_day_slots(day_ids)
        )
        candidates = (
            facts.round_candidates(exam_round.id)
            if facts is not None
            else planning.round_candidates(exam_round.id)
        )
        started = [item.id for item in slots if item.actual_started_at is not None]
        if decision_type == "cancel":
            self._finding(
                items,
                "round_has_candidates",
                "Die abzusagende Prüfungsrunde besitzt zugeordnete Prüflinge",
                bool(candidates),
                [],
            )
            self._finding(
                items, "no_slot_started", "Kein Prüfungsslot hat begonnen", not started, started
            )
            self._finding(
                items,
                "candidates_terminal",
                "Alle Prüflinge sind wirksam neu zugeordnet oder beendet",
                all(
                    item["terminal_status"] in TERMINAL_CANDIDATE_STATUSES - {"result_communicated"}
                    for item in candidates
                ),
                [
                    item["id"]
                    for item in candidates
                    if item["terminal_status"]
                    not in TERMINAL_CANDIDATE_STATUSES - {"result_communicated"}
                ],
            )
            return {"ready": all(item["ok"] for item in items), "items": items}

        self._finding(
            items,
            "round_has_confirmed_plan",
            "Die Prüfungsrunde besitzt einen bestätigten oder begonnenen Plan",
            exam_round.status in {"plan_confirmed", "in_progress", "completed"} and bool(days),
            {"planning_status": exam_round.status, "exam_day_count": len(days)},
        )
        formal_day_ids = (
            set(
                session.scalars(
                    select(ExamDayClosure.exam_day_id).where(
                        ExamDayClosure.exam_day_id.in_(day_ids),
                        ExamDayClosure.status == "current",
                    )
                )
            )
            if day_ids
            else set()
        )
        incomplete_days = [
            item.id
            for item in days
            if item.closure_status not in {"closed", "closed_exception", "historical"}
            or (item.closure_status != "historical" and item.id not in formal_day_ids)
        ]
        self._finding(
            items,
            "days_closed",
            "Alle Prüfungstage sind mit Nachweis geschlossen",
            not incomplete_days,
            incomplete_days,
        )
        self._finding(
            items,
            "no_day_reopening",
            "Kein Prüfungstag ist wieder geöffnet",
            all(item.closure_status != "reopening" for item in days),
            [item.id for item in days if item.closure_status == "reopening"],
        )
        follow_ups = (
            list(
                session.scalars(
                    select(ExamDayTask).where(
                        ExamDayTask.exam_day_id.in_(day_ids),
                        ExamDayTask.task_type == "protocol_follow_up",
                        ExamDayTask.status == "open",
                    )
                )
            )
            if day_ids
            else []
        )
        self._finding(
            items,
            "no_protocol_follow_up",
            "Keine Protokoll-Nachfassaufgabe ist offen",
            not follow_ups,
            [item.id for item in follow_ups],
        )
        non_terminal = [item["id"] for item in candidates if item["terminal_status"] == "open"]
        invalid_terminal = [
            item["id"]
            for item in candidates
            if not self._candidate_terminal_valid(session, item, planning, facts)
        ]
        self._finding(
            items,
            "candidates_terminal",
            "Jeder Prüfling besitzt einen wirksamen terminalen Status",
            not non_terminal and not invalid_terminal,
            sorted(set(non_terminal + invalid_terminal)),
        )
        results = (
            facts.results_for_round(exam_round.id)
            if facts is not None
            else (assessment_work or self.assessment_lifecycle_factory(session)).results_for_round(
                exam_round.id
            )
        )
        corrections = [
            (result["id"], correction["id"])
            for result in results
            for correction in result["corrections"]
            if correction["status"] == "open"
        ]
        slot_ids = (
            facts.exam_day_slot_ids(day_ids)
            if facts is not None
            else planning.exam_day_slot_ids(day_ids)
        )
        protocol_corrections = (
            list(
                session.scalars(
                    select(ExamProtocolCorrectionRequest)
                    .join(
                        ExamProtocol,
                        ExamProtocol.id == ExamProtocolCorrectionRequest.exam_protocol_id,
                    )
                    .where(
                        ExamProtocol.exam_slot_id.in_(slot_ids),
                        ExamProtocolCorrectionRequest.status.in_({"requested", "opened"}),
                    )
                )
            )
            if day_ids
            else []
        )
        self._finding(
            items,
            "no_corrections",
            "Keine Protokoll-, Bewertungs- oder Ergebniskorrektur ist offen",
            not corrections and not protocol_corrections,
            [item[1] for item in corrections] + [item.id for item in protocol_corrections],
        )
        absences = (
            list(
                session.scalars(select(AbsenceReport).where(AbsenceReport.exam_day_id.in_(day_ids)))
            )
            if day_ids
            else []
        )
        open_absences = [
            item.id for item in absences if item.status not in TERMINAL_ABSENCE_STATUSES
        ]
        self._finding(
            items,
            "absence_processes_complete",
            "Alle Ausfall- und Ersatzvorgänge sind abgeschlossen",
            not open_absences,
            open_absences,
        )
        open_slots = [
            item.id for item in slots if item.execution_status not in {"completed", "cancelled"}
        ]
        self._finding(
            items,
            "slots_terminal",
            "Keine offenen Prüfungsslots verbleiben",
            not open_slots,
            open_slots,
        )
        pending_consequences = (
            facts.lifecycle_context(
                exam_round.id,
                exam_round.exam_half_year_id,
                tuple(item["candidate_id"] for item in candidates),
            )
            if facts is not None
            else planning.lifecycle_context(
                exam_round.id,
                exam_round.exam_half_year_id,
                tuple(item["candidate_id"] for item in candidates),
            )
        )["pending_consequence_ids"]
        self._finding(
            items,
            "plan_consequences_complete",
            "Alle Planänderungsfolgen sind verarbeitet",
            not pending_consequences,
            pending_consequences,
        )
        return {"ready": all(item["ok"] for item in items), "items": items}

    def _snapshot(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        identity_work: IdentityLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        planning = planning_work or self.planning_lifecycle_work_factory(session)
        identity = identity_work or self.identity_lifecycle_work_factory(session)
        planning_context = (
            facts.lifecycle_context(
                exam_round.id,
                exam_round.exam_half_year_id,
                tuple(item["candidate_id"] for item in facts.candidates),
            )
            if facts is not None
            else planning.lifecycle_context(
                exam_round.id,
                exam_round.exam_half_year_id,
                tuple(item["candidate_id"] for item in planning.round_candidates(exam_round.id)),
            )
        )
        half_year = planning_context["half_year"]
        committee = (
            facts.committee if facts is not None else identity.committee(exam_round.committee_id)
        )
        members = (
            list(facts.members)
            if facts is not None
            else list(identity.committee_members(exam_round.committee_id))
        )
        candidates = []
        round_candidates = (
            facts.round_candidates(exam_round.id)
            if facts is not None
            else planning.round_candidates(exam_round.id)
        )
        candidate_details = {
            item.id: item
            for item in (
                facts.candidate_details
                if facts is not None
                else planning.candidate_details([row["candidate_id"] for row in round_candidates])
            )
        }
        for item in round_candidates:
            person = candidate_details[item["candidate_id"]]
            candidates.append(
                {
                    "round_candidate_id": item["id"],
                    "candidate_id": person.id,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "ihk_exam_number": person.ihk_exam_number,
                    "terminal_status": item["terminal_status"],
                    "terminal_reason": item["terminal_reason"],
                    "effective_new_round_id": item["effective_new_round_id"],
                    "postponed_until": item["postponed_until"],
                    "ihk_decision_reference": item["ihk_decision_reference"],
                    "terminal_at": item["terminal_at"],
                }
            )
        days = list(
            session.scalars(
                select(ExamDay).where(ExamDay.exam_round_id == exam_round.id).order_by(ExamDay.id)
            )
        )
        day_ids = list(facts.day_ids) if facts is not None else [item.id for item in days]
        slots = (
            facts.exam_day_slots(day_ids) if facts is not None else planning.exam_day_slots(day_ids)
        )
        result_rows = (
            facts.results_for_round(exam_round.id)
            if facts is not None
            else (assessment_work or self.assessment_lifecycle_factory(session)).results_for_round(
                exam_round.id
            )
        )
        slot_ids = (
            facts.exam_day_slot_ids(day_ids)
            if facts is not None
            else planning.exam_day_slot_ids(day_ids)
        )
        protocol_rows = (
            list(
                session.scalars(
                    select(ExamProtocol)
                    .where(ExamProtocol.exam_slot_id.in_(slot_ids))
                    .order_by(ExamProtocol.id)
                )
            )
            if day_ids
            else []
        )
        result_ids = [item["id"] for item in result_rows]
        assignment_rows = (
            facts.exam_day_assignments(day_ids)
            if facts is not None
            else planning.exam_day_assignments(day_ids)
        )
        absence_rows = (
            list(
                session.scalars(
                    select(AbsenceReport)
                    .where(AbsenceReport.exam_day_id.in_(day_ids))
                    .order_by(AbsenceReport.id)
                )
            )
            if day_ids
            else []
        )
        return {
            "round": {
                "id": exam_round.id,
                "name": exam_round.name,
                "planning_status": exam_round.status,
                "lifecycle_status": exam_round.lifecycle_status,
                "revision": exam_round.revision,
            },
            "half_year": {
                "id": half_year["id"],
                "season": half_year["season"],
                "year": half_year["year"],
                "administrative_status": half_year["status"],
                "legacy_status": half_year["legacy_status"],
            },
            "committee": {
                "id": committee.id,
                "name": committee.name,
                "occupation": committee.occupation,
                "ihk": committee.ihk,
            },
            "roles": [
                {
                    "member_id": member.id,
                    "person_id": member.person_id,
                    "first_name": member.first_name,
                    "last_name": member.last_name,
                    "committee_role": member.committee_role,
                    "representing_side": member.representing_side,
                    "is_active": bool(member.is_active),
                }
                for member in members
            ],
            "candidates": candidates,
            "candidate_assignment_history": planning_context["candidate_assignment_history"],
            "plan_revisions": planning_context["plan_revisions"],
            "days": [
                {
                    "id": item.id,
                    "date": item.date,
                    "status": item.status,
                    "revision": item.revision,
                    "closure_status": item.closure_status,
                }
                for item in days
            ],
            "slots": [
                {
                    "id": item.id,
                    "exam_day_id": item.exam_day_id,
                    "round_candidate_id": item.round_candidate_id,
                    "starts_at": item.starts_at,
                    "ends_at": item.ends_at,
                    "execution_status": item.execution_status,
                    "actual_started_at": item.actual_started_at,
                    "actual_completed_at": item.actual_completed_at,
                }
                for item in slots
            ],
            "assignments": [
                {
                    "id": item.id,
                    "exam_day_id": item.exam_day_id,
                    "committee_member_id": item.committee_member_id,
                    "assignment_role": item.assignment_role,
                    "day_part": item.day_part,
                    "fallback_status": item.fallback_status,
                }
                for item in assignment_rows
            ],
            "absences": [
                {
                    "id": item.id,
                    "exam_day_id": item.exam_day_id,
                    "exam_day_assignment_id": item.exam_day_assignment_id,
                    "status": item.status,
                    "selected_replacement_member_id": item.selected_replacement_member_id,
                    "version": item.version,
                }
                for item in absence_rows
            ],
            "protocols": [
                {
                    "id": item.id,
                    "exam_slot_id": item.exam_slot_id,
                    "current_version": item.current_version,
                    "workflow_state": session.scalar(
                        select(ExamProtocolRevision.workflow_state).where(
                            ExamProtocolRevision.exam_protocol_id == item.id,
                            ExamProtocolRevision.version == item.current_version,
                        )
                    ),
                }
                for item in protocol_rows
            ],
            "results": [
                {
                    "id": item["id"],
                    "round_candidate_id": item["round_candidate_id"],
                    "state": item["state"],
                    "correction_open": bool(item["correction_open"]),
                    "version": item["version"],
                    "communications": [
                        {
                            "id": communication["id"],
                            "determination_id": communication["determination_id"],
                            "communicated_at": communication["communicated_at"],
                            "method": communication["method"],
                            "external_document_status": communication["external_document_status"],
                            "external_document_reference": communication[
                                "external_document_reference"
                            ],
                            "status": communication["status"],
                        }
                        for communication in item["communications"]
                    ],
                }
                for item in result_rows
            ],
            "assessments": {
                "individual": (
                    [
                        {
                            "id": item["id"],
                            "exam_result_id": result["id"],
                            "component_key": item["component_key"],
                            "criterion_key": item["criterion_key"],
                            "assessor_member_id": item["assessor_member_id"],
                            "revision": item["revision"],
                            "normalized_points": item["normalized_points"],
                            "status": item["status"],
                        }
                        for result in result_rows
                        for item in result["individual_assessments"]
                    ]
                    if result_ids
                    else []
                ),
                "committee": (
                    [
                        {
                            "id": item["id"],
                            "exam_result_id": result["id"],
                            "component_key": item["component_key"],
                            "revision": item["revision"],
                            "points": item["points"],
                            "participant_member_ids": item["participant_member_ids"],
                            "status": item["status"],
                        }
                        for result in result_rows
                        for item in result["component_assessments"]
                    ]
                    if result_ids
                    else []
                ),
            },
        }

    def _retention_view(
        self,
        session: Session,
        round_id: int,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        planning = planning_work or self.planning_lifecycle_work_factory(session)
        day_ids = (
            list(facts.day_ids)
            if facts is not None
            else list(session.scalars(select(ExamDay.id).where(ExamDay.exam_round_id == round_id)))
        )
        slot_ids = (
            facts.exam_day_slot_ids(day_ids)
            if facts is not None
            else planning.exam_day_slot_ids(day_ids)
        )
        protocol_rows = list(
            session.execute(
                select(
                    ExamProtocolRetention.exam_protocol_id,
                    ExamProtocolRetention.retain_until,
                    ExamProtocolRetention.legal_hold,
                    ExamProtocolRetention.hold_reason,
                )
                .join(ExamProtocol, ExamProtocol.id == ExamProtocolRetention.exam_protocol_id)
                .where(ExamProtocol.exam_slot_id.in_(slot_ids))
            )
        )
        result_rows = [
            {"result_id": result["id"], **result["retention"]}
            for result in (
                facts.results_for_round(round_id)
                if facts is not None
                else (
                    assessment_work or self.assessment_lifecycle_factory(session)
                ).results_for_round(round_id)
            )
            if result["retention"] is not None
        ]
        sources = [
            {
                "kind": "protocol",
                "id": row.exam_protocol_id,
                "retain_until": row.retain_until,
                "legal_hold": bool(row.legal_hold),
                "hold_reason": row.hold_reason,
            }
            for row in protocol_rows
        ] + [
            {
                "kind": "result",
                "id": row["result_id"],
                "retain_until": row["retain_until"],
                "legal_hold": bool(row["legal_hold"]),
                "hold_reason": row["hold_reason"],
            }
            for row in result_rows
        ]
        retain_until_values = [
            item["retain_until"] for item in sources if item["retain_until"] is not None
        ]
        return {
            "retain_until": max(retain_until_values) if retain_until_values else None,
            "legal_hold": any(item["legal_hold"] for item in sources),
            "sources": sources,
        }

    def _impact(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        raw_scope: Any,
        assessment_work: AssessmentLifecycleWork | None = None,
        planning_work: PlanningLifecycleWork | None = None,
        identity_work: IdentityLifecycleWork | None = None,
        facts: RoundLifecycleFacts | None = None,
    ) -> dict[str, Any]:
        planning = planning_work or self.planning_lifecycle_work_factory(session)
        identity = identity_work or self.identity_lifecycle_work_factory(session)
        requested = self._normalize_scope(raw_scope)
        day_ids = (
            set(facts.day_ids)
            if facts is not None
            else set(
                session.scalars(select(ExamDay.id).where(ExamDay.exam_round_id == exam_round.id))
            )
        )
        slot_ids = (
            facts.exam_day_slot_ids(tuple(day_ids))
            if facts is not None
            else planning.exam_day_slot_ids(tuple(day_ids))
        )
        candidate_ids = (
            facts.lifecycle_candidate_ids(exam_round.id)
            if facts is not None
            else planning.lifecycle_candidate_ids(exam_round.id)
        )
        protocol_ids = (
            set(
                session.scalars(
                    select(ExamProtocol.id).where(ExamProtocol.exam_slot_id.in_(slot_ids))
                )
            )
            if day_ids
            else set()
        )
        round_results = (
            facts.results_for_round(exam_round.id)
            if facts is not None
            else (assessment_work or self.assessment_lifecycle_factory(session)).results_for_round(
                exam_round.id
            )
        )
        result_ids = {item["id"] for item in round_results}
        absence_ids = (
            set(
                session.scalars(
                    select(AbsenceReport.id).where(AbsenceReport.exam_day_id.in_(day_ids))
                )
            )
            if day_ids
            else set()
        )
        valid_ids = {
            "candidate_assignment": candidate_ids,
            "exam_day": day_ids,
            "exam_protocol": protocol_ids,
            "exam_result": result_ids,
            "absence": absence_ids,
            "planning": {exam_round.id},
            "availability": {exam_round.id},
        }
        for token in requested:
            kind, raw_id = token.split(":", 1)
            if int(raw_id) not in valid_ids[kind]:
                raise ValueError("Der Korrekturumfang gehört nicht zur ausgewählten Prüfungsrunde")
        expanded = set(requested)
        for token in requested:
            kind, raw_id = token.split(":", 1)
            entity_id = int(raw_id)
            if kind == "exam_day":
                day_slots = (
                    facts.exam_day_slots([entity_id])
                    if facts is not None
                    else planning.exam_day_slots([entity_id])
                )
                day_slot_ids = {item.id for item in day_slots}
                expanded.update(
                    _token("exam_protocol", item)
                    for item in session.scalars(
                        select(ExamProtocol.id).where(ExamProtocol.exam_slot_id.in_(day_slot_ids))
                    )
                )
                day_candidate_ids = {item.round_candidate_id for item in day_slots}
                expanded.update(
                    _token("exam_result", result["id"])
                    for result in round_results
                    if result["round_candidate_id"] in day_candidate_ids
                )
        impacted_result_ids = sorted(
            int(item.split(":", 1)[1]) for item in expanded if item.startswith("exam_result:")
        )
        recipients = (
            set(facts.management_member_ids)
            if facts is not None
            else self._management_member_ids(session, exam_round, identity)
        )
        results_by_id = {item["id"]: item for item in round_results}
        for result_id in impacted_result_ids:
            result = results_by_id[result_id]
            determination = next(
                (item for item in result["determinations"] if item["status"] == "current"),
                None,
            )
            if determination is not None:
                recipients.update(determination["participant_member_ids"])
        ihk_processed = [
            result_id
            for result_id in impacted_result_ids
            if any(
                item["external_document_status"] is not None
                for item in results_by_id[result_id]["communications"]
            )
        ]
        return {
            "round_id": exam_round.id,
            "revision": exam_round.revision,
            "requested_scope": requested,
            "expanded_scope": sorted(expanded),
            "impacts": {
                "recipient_member_ids": sorted(recipients),
                "exam_result_ids": impacted_result_ids,
                "ihk_processed_result_ids": ihk_processed,
            },
        }

    def _candidate_terminal_valid(
        self,
        session: Session,
        candidate: dict[str, Any],
        planning: PlanningLifecycleWork,
        facts: RoundLifecycleFacts | None = None,
    ) -> bool:
        if candidate["terminal_status"] == "result_communicated":
            try:
                self._assert_result_communicated(session, candidate, facts)
            except ValueError:
                return False
            return True
        if candidate["terminal_status"] == "transferred":
            if (
                candidate["effective_new_round_id"] is None
                or not candidate["terminal_reason"]
                or candidate["is_active"]
                or not (
                    facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"])
                    if facts is not None
                    else planning.original_assignment_ended(
                        candidate["id"], candidate["exam_round_id"]
                    )
                )
            ):
                return False
            if facts is not None:
                return facts.effective_transfer_exists(
                    facts.round.exam_half_year_id,
                    candidate["effective_new_round_id"],
                    candidate["candidate_id"],
                )
            return planning.effective_transfer_exists(
                self._required_round(
                    self.planning_lifecycle_work_factory(session),
                    candidate["exam_round_id"],
                ).exam_half_year_id,
                candidate["effective_new_round_id"],
                candidate["candidate_id"],
            )
        if candidate["terminal_status"] == "postponed":
            return bool(
                candidate["terminal_reason"]
                and candidate["postponed_until"]
                and not candidate["is_active"]
                and (
                    facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"])
                    if facts is not None
                    else planning.original_assignment_ended(
                        candidate["id"], candidate["exam_round_id"]
                    )
                )
            )
        if candidate["terminal_status"] == "ihk_terminated":
            return bool(
                candidate["terminal_reason"]
                and candidate["ihk_decision_reference"]
                and not candidate["is_active"]
                and (
                    facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"])
                    if facts is not None
                    else planning.original_assignment_ended(
                        candidate["id"], candidate["exam_round_id"]
                    )
                )
            )
        return False

    def _assert_result_communicated(
        self, session: Session, candidate: dict[str, Any], facts: RoundLifecycleFacts | None = None
    ) -> None:
        result = (
            facts.result_for_round_candidate(candidate["id"])
            if facts is not None
            else self.assessment_lifecycle_factory(session).result_for_round_candidate(
                candidate["id"]
            )
        )
        if result is None or result["state"] != "determined" or result["correction_open"]:
            raise ValueError("Das Ergebnis ist nicht vollständig festgestellt")
        determination = next(
            (item for item in result["determinations"] if item["status"] == "current"), None
        )
        communication = next(
            (item for item in result["communications"] if item["status"] == "current"), None
        )
        if determination is None or communication is None:
            raise ValueError("Ergebnisfeststellung und Ergebnismitteilung sind erforderlich")
        if any(item["status"] != "confirmed" for item in result["external_results"]):
            raise ValueError("Externe Eingangsergebnisse sind noch nicht bestätigt")

    def _dependency_counts(
        self,
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        planning: PlanningLifecycleWork,
    ) -> dict[str, int]:
        day_ids = select(ExamDay.id).where(ExamDay.exam_round_id == exam_round.id)
        return {
            **planning.dependency_counts(exam_round.id),
            "Prüfungstage": self._count(session, ExamDay, ExamDay.exam_round_id == exam_round.id),
            "Ausfallvorgänge": self._count(
                session, AbsenceReport, AbsenceReport.exam_day_id.in_(day_ids)
            ),
            "Lebenszyklushistorie": self._count(
                session, ExamRoundDecision, ExamRoundDecision.exam_round_id == exam_round.id
            ),
        }

    @staticmethod
    def _count(session: Session, model: type[Any], criterion: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(criterion)) or 0)

    def _require_mutable_scope(
        self, session: Session, exam_round: PlanningRoundLifecycleSnapshot, token: str
    ) -> None:
        if exam_round.lifecycle_status == "open":
            return
        if exam_round.lifecycle_status != "reopening":
            raise ExamRoundConflictError(
                "Die Prüfungsrunde ist fachlich beendet und für Änderungen gesperrt"
            )
        reopening = self._active_reopening(session, exam_round.id)
        if reopening is None or token not in set(json.loads(reopening.scope_json)):
            raise ExamRoundConflictError(
                "Diese Daten gehören nicht zum freigegebenen Korrekturumfang"
            )

    def _notify(
        self,
        committee_id: int,
        round_id: int,
        recipients: set[int],
        title: str,
        message: str,
        origin_key: str,
    ) -> None:
        try:
            self.notification_service.create_direct(
                committee_id=committee_id,
                round_id=round_id,
                recipient_member_ids=recipients,
                event_type="plan_changed",
                title=title,
                message=message,
                action_path="/exam-half-years",
                origin_key=origin_key,
            )
        except Exception:
            pass

    @staticmethod
    def _finding(
        items: list[dict[str, Any]], code: str, label: str, ok: bool, details: Any
    ) -> None:
        items.append({"code": code, "label": label, "ok": ok, "details": details})

    @staticmethod
    def _required_round(
        planning: PlanningLifecycleWork, round_id: int
    ) -> PlanningRoundLifecycleSnapshot:
        exam_round = planning.round_lifecycle_snapshot(round_id)
        if exam_round is None:
            raise ValueError("Prüfungsrunde nicht gefunden")
        return exam_round

    @staticmethod
    def _required_revision(payload: dict[str, Any]) -> int:
        value = payload.get("revision")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Eine aktuelle Rundenrevision ist erforderlich")
        return value

    @staticmethod
    def _required_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} ist erforderlich")
        normalized = value.strip()
        if len(normalized) > maximum:
            raise ValueError(f"{field} ist zu lang")
        return normalized

    @staticmethod
    def _optional_text(value: Any, maximum: int) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Textwert erwartet")
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > maximum:
            raise ValueError("Textwert ist zu lang")
        return normalized

    @staticmethod
    def _normalize_scope(raw_scope: Any) -> list[str]:
        if not isinstance(raw_scope, list) or not raw_scope:
            raise ValueError("Eine Wiederöffnung benötigt einen konkreten Korrekturumfang")
        tokens: set[str] = set()
        for item in raw_scope:
            if not isinstance(item, dict) or set(item) != {"kind", "entity_id"}:
                raise ValueError("Ungültiger Korrekturumfang")
            kind = item.get("kind")
            entity_id = item.get("entity_id")
            if kind not in REOPENING_SCOPE_KINDS:
                raise ValueError("Unbekannter Korrekturumfang")
            if not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id < 1:
                raise ValueError("Ungültige Kennung im Korrekturumfang")
            tokens.add(_token(kind, entity_id))
        return sorted(tokens)

    @staticmethod
    def _require_access(
        exam_round: PlanningRoundLifecycleSnapshot, scope: AuthorizationScope
    ) -> int | None:
        if not scope.can_read_committee(exam_round.committee_id):
            raise PermissionError("Forbidden.")
        return scope.member_for_committee(exam_round.committee_id)

    def _require_management(
        self, exam_round: PlanningRoundLifecycleSnapshot, scope: AuthorizationScope
    ) -> int:
        actor_id = self._require_access(exam_round, scope)
        if actor_id is None or not scope.can_manage_committee(exam_round.committee_id):
            raise PermissionError("Forbidden.")
        return actor_id

    @staticmethod
    def _active_reopening(session: Session, round_id: int) -> ExamRoundReopening | None:
        return session.scalar(
            select(ExamRoundReopening).where(
                ExamRoundReopening.exam_round_id == round_id,
                ExamRoundReopening.status == "open",
            )
        )

    @staticmethod
    def _current_or_latest_decision(session: Session, round_id: int) -> ExamRoundDecision | None:
        return session.scalar(
            select(ExamRoundDecision)
            .where(ExamRoundDecision.exam_round_id == round_id)
            .order_by(
                (ExamRoundDecision.status == "current").desc(),
                ExamRoundDecision.id.desc(),
            )
        )

    @staticmethod
    def _management_member_ids(
        session: Session,
        exam_round: PlanningRoundLifecycleSnapshot,
        identity: IdentityLifecycleWork,
    ) -> set[int]:
        return identity.management_member_ids(exam_round.committee_id)

    @staticmethod
    def _decision_view(item: ExamRoundDecision) -> dict[str, Any]:
        return {
            "id": item.id,
            "decision_type": item.decision_type,
            "requested_revision": item.requested_revision,
            "resulting_revision": item.resulting_revision,
            "actor_member_id": item.actor_member_id,
            "reason": item.reason,
            "checklist": json.loads(item.checklist_json),
            "snapshot": json.loads(item.snapshot_json),
            "previous_decision_id": item.previous_decision_id,
            "status": item.status,
            "decided_at": item.decided_at,
        }

    @staticmethod
    def _reopening_view(item: ExamRoundReopening) -> dict[str, Any]:
        return {
            "id": item.id,
            "requested_revision": item.requested_revision,
            "resulting_revision": item.resulting_revision,
            "occasion": item.occasion,
            "source": item.source,
            "reason": item.reason,
            "requested_scope": json.loads(item.requested_scope_json),
            "scope": json.loads(item.scope_json),
            "impacts": json.loads(item.impacts_json),
            "actor_member_id": item.actor_member_id,
            "status": item.status,
            "opened_at": item.opened_at,
            "completed_at": item.completed_at,
        }

    @staticmethod
    def _event_view(item: ExamRoundAuditEvent) -> dict[str, Any]:
        return {
            "id": item.id,
            "round_revision": item.round_revision,
            "event_type": item.event_type,
            "actor_member_id": item.actor_member_id,
            "decision_id": item.decision_id,
            "reopening_id": item.reopening_id,
            "reason": item.reason,
            "scope": json.loads(item.scope_json),
            "created_at": item.created_at,
        }

    @staticmethod
    def _task_view(item: ExamRoundTask) -> dict[str, Any]:
        return {
            "id": item.id,
            "reopening_id": item.reopening_id,
            "recipient_member_id": item.recipient_member_id,
            "task_type": item.task_type,
            "details": json.loads(item.details_json),
            "status": item.status,
            "created_at": item.created_at,
            "completed_at": item.completed_at,
        }

    @staticmethod
    def _export_view(item: ExamRoundExport) -> dict[str, Any]:
        return {
            "id": item.id,
            "decision_id": item.decision_id,
            "round_revision": item.round_revision,
            "export_kind": item.export_kind,
            "lifecycle_status": item.lifecycle_status,
            "generated_by_member_id": item.generated_by_member_id,
            "generated_at": item.generated_at,
            "superseded_at": item.superseded_at,
            "superseded_by_revision": item.superseded_by_revision,
            "obsolete": item.superseded_at is not None,
        }
