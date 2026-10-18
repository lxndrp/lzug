"""Revision-bound lifecycle, history, locking, and exports for exam rounds."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from backend.execution.lifecycle_errors import ExamRoundConflictError
from backend.execution.lifecycle_ports import (
    PlanningRoundLifecycleSnapshot,
    RoundDecisionCommand,
    RoundLifecycleFacts,
    RoundReopenCommand,
)
from backend.execution.round_lifecycle_snapshot import (
    ExamRoundLifecycleExportSnapshot,
    ExamRoundLifecycleReadSnapshot,
)
from backend.execution.round_lifecycle_view import round_lifecycle_view
from backend.identity.authorization import AuthorizationScope
from backend.notifications.service import NotificationService
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


class ExamRoundValidationError(ValueError):
    """Expose the complete failed prerequisite matrix for one decision."""

    def __init__(self, message: str, findings: list[dict[str, Any]]):
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class ExamRoundDecisionOutcome:
    """Deferred notification input for one committed round decision."""

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
        *,
        notification_service: NotificationService,
    ) -> None:
        self.notification_service = notification_service

    def export_from_read_snapshots(
        self,
        scope: AuthorizationScope,
        facts: RoundLifecycleFacts,
        lifecycle_snapshot: ExamRoundLifecycleReadSnapshot,
        export_snapshot: ExamRoundLifecycleExportSnapshot,
        export_record: dict[str, Any],
        pending_consequence_ids: Sequence[int],
        *,
        human: bool,
    ) -> dict[str, Any] | str:
        """Project and render an export using only detached facts and records."""
        lifecycle = round_lifecycle_view(
            scope,
            facts,
            pending_consequence_ids,
            lifecycle_snapshot,
        )
        if lifecycle is None:
            raise ValueError("Prüfungsrunde nicht gefunden")
        snapshot = self._snapshot_from_export_snapshot(facts, export_snapshot)
        if human:
            return render_round_lifecycle_export(facts.round.id, lifecycle, snapshot)
        return {
            "export_version": 1,
            "export": export_record,
            "lifecycle": lifecycle,
            "snapshot": snapshot,
        }

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
        repeated = any(
            item["command_fingerprint"] == fingerprint
            for item in facts.lifecycle_records.get("read", {}).get("decisions", ())
        )
        if repeated:
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
            exam_round, command.revision, decision_type, facts=facts
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
            reopening["id"] if reopening else None,
            evaluation,
            self._snapshot(exam_round, facts=facts),
            _now(),
            False,
        )

    def refresh_decision_snapshot(
        self,
        intent: ExamRoundDecisionIntent,
        facts: RoundLifecycleFacts,
    ) -> ExamRoundDecisionIntent:
        """Rebuild the persisted decision snapshot from post-Planning mutation facts."""
        day_status_overrides = (
            {day_id: "cancelled" for day_id in facts.day_ids}
            if intent.decision_type == "cancel"
            else {}
        )
        return replace(
            intent,
            snapshot=self._snapshot(
                facts.round, facts=facts, day_status_overrides=day_status_overrides
            ),
        )

    def evaluate_reopen_intent(
        self,
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
        repeated = any(
            item["command_fingerprint"] == fingerprint
            for item in facts.lifecycle_records.get("read", {}).get("reopenings", ())
        )
        if repeated:
            previous = self._current_or_latest_decision_record(facts)
            return ExamRoundReopeningIntent(
                exam_round.id,
                command.revision,
                fingerprint,
                actor_id,
                reason,
                occasion,
                source,
                {},
                previous["id"] if previous else None,
                _now(),
                True,
            )
        impact = self._reopening_prerequisites(
            exam_round,
            command.revision,
            [item.payload() for item in command.scope],
            facts=facts,
        )
        previous = self._current_or_latest_decision_record(facts)
        return ExamRoundReopeningIntent(
            exam_round.id,
            command.revision,
            fingerprint,
            actor_id,
            reason,
            occasion,
            source,
            impact,
            previous["id"] if previous else None,
            _now(),
            False,
        )

    def _decision_prerequisites(
        self,
        exam_round: PlanningRoundLifecycleSnapshot,
        expected_revision: int,
        decision_type: str,
        facts: RoundLifecycleFacts,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Evaluate the current state after replay detection and before any mutation."""
        if exam_round.revision != expected_revision:
            raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
        if exam_round.lifecycle_status not in {"open", "reopening"}:
            raise ExamRoundConflictError("Die Prüfungsrunde ist bereits fachlich beendet")
        reopening = self._active_reopening_record(facts)
        if exam_round.lifecycle_status == "reopening" and reopening is None:
            raise ExamRoundConflictError("Der Wiederöffnungsstand ist inkonsistent")

        evaluation = self._evaluate(exam_round, decision_type, facts)
        if not evaluation["ready"]:
            raise ExamRoundValidationError(
                "Die Voraussetzungen für diesen Rundenstand sind nicht erfüllt",
                [item for item in evaluation["items"] if not item["ok"]],
            )

        return reopening, evaluation

    def reopening_impact_from_facts(
        self,
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
        if self._active_reopening_record(facts) is not None:
            raise ExamRoundConflictError("Für die Prüfungsrunde läuft bereits eine Wiederöffnung")
        return self._impact(exam_round, raw_scope, facts=facts)

    def _reopening_prerequisites(
        self,
        exam_round: PlanningRoundLifecycleSnapshot,
        expected_revision: int,
        raw_scope: Any,
        facts: RoundLifecycleFacts,
    ) -> dict[str, Any]:
        """Read and validate correction impact without superseding any current evidence."""
        if exam_round.revision != expected_revision:
            raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
        if exam_round.lifecycle_status not in TERMINAL_LIFECYCLE_STATUSES:
            raise ExamRoundConflictError(
                "Nur eine beendete Prüfungsrunde kann wieder geöffnet werden"
            )
        if self._active_reopening_record(facts) is not None:
            raise ExamRoundConflictError("Für die Prüfungsrunde läuft bereits eine Wiederöffnung")
        return self._impact(exam_round, raw_scope, facts=facts)

    def _evaluate(
        self,
        exam_round: PlanningRoundLifecycleSnapshot,
        decision_type: str,
        facts: RoundLifecycleFacts,
        pending_consequence_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        records = facts.lifecycle_records
        read_records = records.get("read", {})
        export_records = records.get("export", {})
        days = list(export_records.get("days", ()))
        day_ids = list(facts.day_ids)
        slots = facts.exam_day_slots(day_ids)
        candidates = facts.round_candidates(exam_round.id)
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
        formal_day_ids = set(read_records.get("current_closure_day_ids", ()))
        incomplete_days = [
            item["id"]
            for item in days
            if item["closure_status"] not in {"closed", "closed_exception", "historical"}
            or (item["closure_status"] != "historical" and item["id"] not in formal_day_ids)
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
            all(item["closure_status"] != "reopening" for item in days),
            [item["id"] for item in days if item["closure_status"] == "reopening"],
        )
        follow_ups = list(read_records.get("follow_up_task_ids", ()))
        self._finding(
            items,
            "no_protocol_follow_up",
            "Keine Protokoll-Nachfassaufgabe ist offen",
            not follow_ups,
            follow_ups,
        )
        non_terminal = [item["id"] for item in candidates if item["terminal_status"] == "open"]
        invalid_terminal = [
            item["id"] for item in candidates if not self._candidate_terminal_valid(item, facts)
        ]
        self._finding(
            items,
            "candidates_terminal",
            "Jeder Prüfling besitzt einen wirksamen terminalen Status",
            not non_terminal and not invalid_terminal,
            sorted(set(non_terminal + invalid_terminal)),
        )
        results = facts.results_for_round(exam_round.id)
        corrections = [
            (result["id"], correction["id"])
            for result in results
            for correction in result["corrections"]
            if correction["status"] == "open"
        ]
        protocol_corrections = list(read_records.get("protocol_correction_ids", ()))
        self._finding(
            items,
            "no_corrections",
            "Keine Protokoll-, Bewertungs- oder Ergebniskorrektur ist offen",
            not corrections and not protocol_corrections,
            [item[1] for item in corrections] + protocol_corrections,
        )
        absences = list(export_records.get("absences", ()))
        open_absences = [
            item["id"] for item in absences if item["status"] not in TERMINAL_ABSENCE_STATUSES
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
            tuple(pending_consequence_ids)
            if pending_consequence_ids is not None
            else records.get("pending_consequence_ids", ())
        )
        self._finding(
            items,
            "plan_consequences_complete",
            "Alle Planänderungsfolgen sind verarbeitet",
            not pending_consequences,
            pending_consequences,
        )
        return {"ready": all(item["ok"] for item in items), "items": items}

    @staticmethod
    def _snapshot_from_export_snapshot(
        facts: RoundLifecycleFacts,
        export_snapshot: ExamRoundLifecycleExportSnapshot,
    ) -> dict[str, Any]:
        """Build the export view without sessions or persistence model objects."""
        exam_round = facts.round
        planning_context = facts.lifecycle_context(
            exam_round.id,
            exam_round.exam_half_year_id,
            tuple(item["candidate_id"] for item in facts.candidates),
        )
        half_year = planning_context["half_year"]
        committee = facts.committee
        candidates_by_id = {item.id: item for item in facts.candidate_details}
        candidates = [
            {
                "round_candidate_id": item["id"],
                "candidate_id": candidates_by_id[item["candidate_id"]].id,
                "first_name": candidates_by_id[item["candidate_id"]].first_name,
                "last_name": candidates_by_id[item["candidate_id"]].last_name,
                "ihk_exam_number": candidates_by_id[item["candidate_id"]].ihk_exam_number,
                "terminal_status": item["terminal_status"],
                "terminal_reason": item["terminal_reason"],
                "effective_new_round_id": item["effective_new_round_id"],
                "postponed_until": item["postponed_until"],
                "ihk_decision_reference": item["ihk_decision_reference"],
                "terminal_at": item["terminal_at"],
            }
            for item in facts.round_candidates(exam_round.id)
        ]
        records = export_snapshot.records
        days = records["days"]
        slots = facts.exam_day_slots(facts.day_ids)
        results = facts.results_for_round(exam_round.id)
        assignments = facts.exam_day_assignments(facts.day_ids)
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
                for member in facts.members
            ],
            "candidates": candidates,
            "candidate_assignment_history": planning_context["candidate_assignment_history"],
            "plan_revisions": planning_context["plan_revisions"],
            "days": [dict(item) for item in days],
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
                for item in assignments
            ],
            "absences": [
                {
                    "id": item["id"],
                    "exam_day_id": item["exam_day_id"],
                    "exam_day_assignment_id": item["exam_day_assignment_id"],
                    "status": item["status"],
                    "selected_replacement_member_id": item["selected_replacement_member_id"],
                    "version": item["version"],
                }
                for item in records["absences"]
            ],
            "protocols": [dict(item) for item in records["protocols"]],
            "results": [
                {
                    "id": item["id"],
                    "round_candidate_id": item["round_candidate_id"],
                    "state": item["state"],
                    "correction_open": bool(item["correction_open"]),
                    "version": item["version"],
                    "communications": [
                        {
                            "id": row["id"],
                            "determination_id": row["determination_id"],
                            "communicated_at": row["communicated_at"],
                            "method": row["method"],
                            "external_document_status": row["external_document_status"],
                            "external_document_reference": row["external_document_reference"],
                            "status": row["status"],
                        }
                        for row in item["communications"]
                    ],
                }
                for item in results
            ],
            "assessments": {
                "individual": [
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
                    for result in results
                    for item in result["individual_assessments"]
                ],
                "committee": [
                    {
                        "id": item["id"],
                        "exam_result_id": result["id"],
                        "component_key": item["component_key"],
                        "revision": item["revision"],
                        "points": item["points"],
                        "participant_member_ids": item["participant_member_ids"],
                        "status": item["status"],
                    }
                    for result in results
                    for item in result["component_assessments"]
                ],
            },
        }

    def _snapshot(
        self,
        exam_round: PlanningRoundLifecycleSnapshot,
        facts: RoundLifecycleFacts,
        day_status_overrides: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        planning_context = facts.lifecycle_context(
            exam_round.id,
            exam_round.exam_half_year_id,
            tuple(item["candidate_id"] for item in facts.candidates),
        )
        half_year = planning_context["half_year"]
        committee = facts.committee
        members = list(facts.members)
        candidates = []
        round_candidates = facts.round_candidates(exam_round.id)
        candidate_details = {item.id: item for item in facts.candidate_details}
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
        records = facts.lifecycle_records.get("export", {})
        days = list(records.get("days", ()))
        day_ids = list(facts.day_ids)
        slots = facts.exam_day_slots(day_ids)
        result_rows = facts.results_for_round(exam_round.id)
        protocol_rows = list(records.get("protocols", ()))
        result_ids = [item["id"] for item in result_rows]
        assignment_rows = facts.exam_day_assignments(day_ids)
        absence_rows = list(records.get("absences", ()))
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
                    "id": item["id"],
                    "date": item["date"],
                    "status": (day_status_overrides or {}).get(item["id"], item["status"]),
                    "revision": item["revision"],
                    "closure_status": item["closure_status"],
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
                    "id": item["id"],
                    "exam_day_id": item["exam_day_id"],
                    "exam_day_assignment_id": item["exam_day_assignment_id"],
                    "status": item["status"],
                    "selected_replacement_member_id": item["selected_replacement_member_id"],
                    "version": item["version"],
                }
                for item in absence_rows
            ],
            "protocols": [
                {
                    "id": item["id"],
                    "exam_slot_id": item["exam_slot_id"],
                    "current_version": item["current_version"],
                    "workflow_state": item["workflow_state"],
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

    def _impact(
        self,
        exam_round: PlanningRoundLifecycleSnapshot,
        raw_scope: Any,
        facts: RoundLifecycleFacts,
    ) -> dict[str, Any]:
        requested = self._normalize_scope(raw_scope)
        day_ids = set(facts.day_ids)
        candidate_ids = facts.lifecycle_candidate_ids(exam_round.id)
        records = facts.lifecycle_records.get("export", {})
        protocols = records.get("protocols", ())
        protocol_ids = {item["id"] for item in protocols}
        protocol_ids_by_slot: dict[int, set[int]] = {}
        for item in protocols:
            protocol_ids_by_slot.setdefault(item["exam_slot_id"], set()).add(item["id"])
        round_results = facts.results_for_round(exam_round.id)
        result_ids = {item["id"] for item in round_results}
        absence_ids = {item["id"] for item in records.get("absences", ())}
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
                day_slots = facts.exam_day_slots([entity_id])
                day_slot_ids = {item.id for item in day_slots}
                expanded.update(
                    _token("exam_protocol", item)
                    for slot_id in day_slot_ids
                    for item in protocol_ids_by_slot.get(slot_id, ())
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
        recipients = set(facts.management_member_ids)
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
        candidate: dict[str, Any],
        facts: RoundLifecycleFacts,
    ) -> bool:
        if candidate["terminal_status"] == "result_communicated":
            try:
                self._assert_result_communicated(candidate, facts)
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
                )
            ):
                return False
            return facts.effective_transfer_exists(
                facts.round.exam_half_year_id,
                candidate["effective_new_round_id"],
                candidate["candidate_id"],
            )
        if candidate["terminal_status"] == "postponed":
            return bool(
                candidate["terminal_reason"]
                and candidate["postponed_until"]
                and not candidate["is_active"]
                and (facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"]))
            )
        if candidate["terminal_status"] == "ihk_terminated":
            return bool(
                candidate["terminal_reason"]
                and candidate["ihk_decision_reference"]
                and not candidate["is_active"]
                and (facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"]))
            )
        return False

    def _assert_result_communicated(
        self, candidate: dict[str, Any], facts: RoundLifecycleFacts
    ) -> None:
        result = facts.result_for_round_candidate(candidate["id"])
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
    def _active_reopening_record(facts: RoundLifecycleFacts) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in facts.lifecycle_records.get("read", {}).get("reopenings", ())
                if item["status"] == "open"
            ),
            None,
        )

    @staticmethod
    def _current_or_latest_decision_record(
        facts: RoundLifecycleFacts,
    ) -> dict[str, Any] | None:
        decisions = list(facts.lifecycle_records.get("read", {}).get("decisions", ()))
        return max(
            decisions,
            key=lambda item: (item["status"] == "current", item["id"]),
            default=None,
        )
