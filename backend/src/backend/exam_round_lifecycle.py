"""Revision-bound lifecycle, history, locking, and exports for exam rounds."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    AbsenceReport,
    CalendarEvent,
    Candidate,
    CandidateCommitteeAssignment,
    CandidateExamDay,
    Committee,
    CommitteeAssessment,
    CommitteeMember,
    ConfirmedPlanRevision,
    ExamDay,
    ExamDayAssignment,
    ExamDayClosure,
    ExamDayTask,
    ExamHalfYear,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolRetention,
    ExamProtocolRevision,
    ExamResult,
    ExamRound,
    ExamRoundAuditEvent,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundIhkStatus,
    ExamRoundReopening,
    ExamRoundTask,
    ExamSlot,
    ExternalExamResult,
    IndividualAssessment,
    MemberAvailability,
    Person,
    PlanConsequence,
    PlanConsequenceBatch,
    PlanningSettings,
    ResultCommunication,
    ResultCorrection,
    ResultDetermination,
    ResultRetention,
    RoundCandidate,
)
from .notifications import NotificationService

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
        notification_service: NotificationService | None = None,
    ) -> None:
        self.db_path = db_path
        self.notification_service = notification_service or NotificationService(db_path)

    def get(self, scope: AuthorizationScope, round_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                return None
            self._require_access(exam_round, scope)
            return self._view(session, exam_round, scope)

    def close(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._decide(scope, round_id, payload, "close")

    def cancel(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._decide(scope, round_id, payload, "cancel")

    def _decide(
        self,
        scope: AuthorizationScope,
        round_id: int,
        payload: dict[str, Any],
        decision_type: str,
    ) -> dict[str, Any]:
        expected_revision = self._required_revision(payload)
        if payload.get("confirmed") is not True:
            raise ValueError("Die angezeigten Voraussetzungen müssen bestätigt werden")
        reason = (
            self._required_text(payload.get("reason"), "reason", 3000)
            if decision_type == "cancel"
            else None
        )
        command = {
            "decision_type": decision_type,
            "revision": expected_revision,
            "confirmed": True,
            "reason": reason,
        }
        fingerprint = _fingerprint(command)
        notify_cancelled: set[int] = set()
        committee_id = 0
        decision_id = 0
        with session_scope(self.db_path) as session:
            exam_round = self._required_round(session, round_id)
            committee_id = exam_round.committee_id
            actor_id = self._require_management(exam_round, scope)
            repeated = session.scalar(
                select(ExamRoundDecision).where(
                    ExamRoundDecision.exam_round_id == exam_round.id,
                    ExamRoundDecision.command_fingerprint == fingerprint,
                )
            )
            if repeated is not None:
                return self._view(session, exam_round, scope)
            if exam_round.revision != expected_revision:
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            if exam_round.lifecycle_status not in {"open", "reopening"}:
                raise ExamRoundConflictError("Die Prüfungsrunde ist bereits fachlich beendet")
            reopening = self._active_reopening(session, exam_round.id)
            if exam_round.lifecycle_status == "reopening" and reopening is None:
                raise ExamRoundConflictError("Der Wiederöffnungsstand ist inkonsistent")

            evaluation = self._evaluate(session, exam_round, decision_type)
            if not evaluation["ready"]:
                raise ExamRoundValidationError(
                    "Die Voraussetzungen für diesen Rundenstand sind nicht erfüllt",
                    [item for item in evaluation["items"] if not item["ok"]],
                )

            now = _now()
            if decision_type == "cancel":
                notify_cancelled = self._apply_cancellation(session, exam_round, now)
            previous = self._current_or_latest_decision(session, exam_round.id)
            if previous is not None:
                previous.status = "superseded"
            snapshot = self._snapshot(session, exam_round)
            decision = ExamRoundDecision(
                exam_round_id=exam_round.id,
                decision_type=decision_type,
                requested_revision=exam_round.revision,
                resulting_revision=exam_round.revision + 1,
                actor_member_id=actor_id,
                reason=reason,
                checklist_json=_json(evaluation["items"]),
                snapshot_json=_json(snapshot),
                previous_decision_id=previous.id if previous else None,
                status="current",
                command_fingerprint=fingerprint,
                decided_at=now,
            )
            session.add(decision)
            session.flush()
            decision_id = decision.id
            exam_round.revision += 1
            exam_round.lifecycle_status = "closed" if decision_type == "close" else "cancelled"
            exam_round.updated_at = now
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
            session.add(
                ExamRoundAuditEvent(
                    exam_round_id=exam_round.id,
                    round_revision=exam_round.revision,
                    event_type=(
                        ("reclosed" if decision_type == "close" else "recancelled")
                        if reopening
                        else ("closed" if decision_type == "close" else "cancelled")
                    ),
                    actor_member_id=actor_id,
                    decision_id=decision.id,
                    reopening_id=reopening.id if reopening else None,
                    reason=reason,
                    scope_json=reopening.requested_scope_json if reopening else "[]",
                    created_at=now,
                )
            )
            result = self._view(session, exam_round, scope)
        if notify_cancelled:
            self._notify(
                committee_id,
                round_id,
                notify_cancelled,
                "Prüfungsrunde abgesagt",
                "Die Prüfungsrunde wurde vollständig und begründet abgesagt.",
                f"exam-round-decision:{decision_id}:cancelled",
            )
        return result

    def reopening_impact(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            exam_round = self._required_round(session, round_id)
            self._require_management(exam_round, scope)
            if exam_round.lifecycle_status not in TERMINAL_LIFECYCLE_STATUSES:
                raise ExamRoundConflictError(
                    "Nur eine beendete Prüfungsrunde kann wieder geöffnet werden"
                )
            if self._active_reopening(session, round_id) is not None:
                raise ExamRoundConflictError(
                    "Für die Prüfungsrunde läuft bereits eine Wiederöffnung"
                )
            return self._impact(session, exam_round, payload.get("scope"))

    def reopen(
        self, scope: AuthorizationScope, round_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_revision = self._required_revision(payload)
        occasion = self._required_text(payload.get("occasion"), "occasion", 1000)
        source = self._required_text(payload.get("source"), "source", 1000)
        reason = self._required_text(payload.get("reason"), "reason", 3000)
        requested_scope = self._normalize_scope(payload.get("scope"))
        command = {
            "revision": expected_revision,
            "occasion": occasion,
            "source": source,
            "reason": reason,
            "scope": requested_scope,
        }
        fingerprint = _fingerprint(command)
        recipients: set[int] = set()
        committee_id = 0
        reopening_id = 0
        with session_scope(self.db_path) as session:
            exam_round = self._required_round(session, round_id)
            committee_id = exam_round.committee_id
            actor_id = self._require_management(exam_round, scope)
            repeated = session.scalar(
                select(ExamRoundReopening).where(
                    ExamRoundReopening.exam_round_id == round_id,
                    ExamRoundReopening.command_fingerprint == fingerprint,
                )
            )
            if repeated is not None:
                return self._view(session, exam_round, scope)
            if exam_round.revision != expected_revision:
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            if exam_round.lifecycle_status not in TERMINAL_LIFECYCLE_STATUSES:
                raise ExamRoundConflictError(
                    "Nur eine beendete Prüfungsrunde kann wieder geöffnet werden"
                )
            if self._active_reopening(session, round_id) is not None:
                raise ExamRoundConflictError(
                    "Für die Prüfungsrunde läuft bereits eine Wiederöffnung"
                )
            impact = self._impact(session, exam_round, payload.get("scope"))
            now = _now()
            previous = self._current_or_latest_decision(session, round_id)
            if previous is not None:
                previous.status = "superseded"
            reopening = ExamRoundReopening(
                exam_round_id=round_id,
                previous_decision_id=previous.id if previous else None,
                requested_revision=exam_round.revision,
                resulting_revision=exam_round.revision + 1,
                occasion=occasion,
                source=source,
                reason=reason,
                requested_scope_json=_json(impact["requested_scope"]),
                scope_json=_json(impact["expanded_scope"]),
                impacts_json=_json(impact["impacts"]),
                actor_member_id=actor_id,
                status="open",
                command_fingerprint=fingerprint,
                opened_at=now,
            )
            session.add(reopening)
            session.flush()
            reopening_id = reopening.id
            exam_round.revision += 1
            exam_round.lifecycle_status = "reopening"
            exam_round.updated_at = now
            for export in session.scalars(
                select(ExamRoundExport).where(
                    ExamRoundExport.exam_round_id == round_id,
                    ExamRoundExport.superseded_at.is_(None),
                )
            ):
                export.superseded_at = now
                export.superseded_by_revision = exam_round.revision
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
                for recipient_id in self._management_member_ids(session, exam_round):
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
            session.add(
                ExamRoundAuditEvent(
                    exam_round_id=round_id,
                    round_revision=exam_round.revision,
                    event_type="reopened",
                    actor_member_id=actor_id,
                    reopening_id=reopening.id,
                    reason=reason,
                    scope_json=reopening.requested_scope_json,
                    created_at=now,
                )
            )
            result = self._view(session, exam_round, scope)
        if recipients:
            self._notify(
                committee_id,
                round_id,
                recipients,
                "Prüfungsrunde zur Korrektur wieder geöffnet",
                "Von Ihnen erfasste oder bestätigte Daten sind von einer begründeten "
                "Korrektur betroffen.",
                f"exam-round-reopening:{reopening_id}:affected",
            )
        return result

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
            exam_round = self._required_round(session, round_id)
            self._require_management(exam_round, scope)
            candidate = session.get(RoundCandidate, round_candidate_id)
            if candidate is None or candidate.exam_round_id != round_id:
                raise ValueError("Prüfling gehört nicht zur Prüfungsrunde")
            self._require_mutable_scope(
                session, exam_round, _token("candidate_assignment", candidate.id)
            )
            if exam_round.revision != expected_revision:
                raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")
            reason = self._optional_text(payload.get("reason"), 3000)
            target_round_id = payload.get("effective_new_round_id")
            postponed_until = self._optional_text(payload.get("postponed_until"), 100)
            ihk_reference = self._optional_text(payload.get("ihk_decision_reference"), 1000)
            if status == "result_communicated":
                self._assert_result_communicated(session, candidate)
            elif status == "transferred":
                if reason is None or not isinstance(target_round_id, int):
                    raise ValueError("Ein Ausschusswechsel benötigt Grund und wirksame neue Runde")
                target = session.get(ExamRound, target_round_id)
                if (
                    target is None
                    or target.id == exam_round.id
                    or target.exam_half_year_id != exam_round.exam_half_year_id
                ):
                    raise ValueError("Die neue Zuordnung ist nicht wirksam")
                assignment = session.scalar(
                    select(CandidateCommitteeAssignment).where(
                        CandidateCommitteeAssignment.candidate_id == candidate.candidate_id,
                        CandidateCommitteeAssignment.exam_round_id == target.id,
                        CandidateCommitteeAssignment.ended_at.is_(None),
                    )
                )
                if assignment is None:
                    raise ValueError("Die neue Zuordnung ist nicht wirksam")
            elif status == "postponed":
                if reason is None or postponed_until is None:
                    raise ValueError("Eine Verschiebung benötigt Grund und verbindlichen Termin")
            elif status == "ihk_terminated":
                if reason is None or ihk_reference is None:
                    raise ValueError("Die IHK-Entscheidung benötigt Grund und Referenz")
            now = _now()
            original_assignment = session.scalar(
                select(CandidateCommitteeAssignment).where(
                    CandidateCommitteeAssignment.round_candidate_id == candidate.id,
                    CandidateCommitteeAssignment.exam_round_id == round_id,
                )
            )
            candidate.terminal_status = status
            candidate.terminal_reason = reason
            candidate.effective_new_round_id = target_round_id if status == "transferred" else None
            candidate.postponed_until = postponed_until if status == "postponed" else None
            candidate.ihk_decision_reference = ihk_reference if status == "ihk_terminated" else None
            candidate.terminal_at = now if status != "open" else None
            if status in {"transferred", "postponed", "ihk_terminated"}:
                candidate.is_active = 0
                if original_assignment is not None and original_assignment.ended_at is None:
                    original_assignment.ended_at = now
                    original_assignment.change_reason = reason
                    original_assignment.updated_at = now
            candidate.updated_at = now
            exam_round.revision += 1
            exam_round.updated_at = now
            session.flush()
            return self._view(session, exam_round, scope)

    def delete_empty_draft(self, scope: AuthorizationScope, round_id: int) -> bool:
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                return False
            self._require_management(exam_round, scope)
            if exam_round.status != "draft" or exam_round.lifecycle_status != "open":
                raise ValueError("Nur eine offene Entwurfsrunde kann gelöscht werden")
            dependencies = self._dependency_counts(session, exam_round)
            present = [name for name, count in dependencies.items() if count]
            if present:
                raise ValueError(
                    "Die Prüfungsrunde besitzt abhängige Fachdaten: " + ", ".join(present)
                )
            session.delete(exam_round)
            return True

    def machine_export(self, scope: AuthorizationScope, round_id: int) -> dict[str, Any]:
        return self._export(scope, round_id, "machine")

    def human_export(self, scope: AuthorizationScope, round_id: int) -> str:
        export = self._export(scope, round_id, "human")
        lifecycle = export["lifecycle"]
        snapshot = export["snapshot"]
        lines = [
            f"Prüfungsrundennachweis {round_id}",
            f"Runde: {snapshot['round']['name']}",
            f"Zeitraum: {snapshot['half_year']['season']} {snapshot['half_year']['year']}",
            f"Ausschuss: {snapshot['committee']['name']}",
            f"Status: {lifecycle['status']}",
            f"Revision: {lifecycle['revision']}",
            "",
            "Kandidaten:",
        ]
        lines.extend(
            f"- {item['first_name']} {item['last_name']}: {item['terminal_status']}"
            for item in snapshot["candidates"]
        )
        lines.extend(["", "Ausschussrollen:"])
        lines.extend(
            f"- {item['first_name']} {item['last_name']}: {item['committee_role']}"
            for item in snapshot["roles"]
        )
        lines.extend(["", "Prüfungstage und tatsächliche Durchführung:"])
        lines.extend(
            f"- {item['date']}: {item['status']} / {item['closure_status']}"
            for item in snapshot["days"]
        )
        lines.extend(["", "Ergebnisse und Mitteilungen:"])
        lines.extend(
            f"- Ergebnis {item['id']}: {item['state']}, "
            f"Mitteilungen {len(item['communications'])}"
            for item in snapshot["results"]
        )
        lines.extend(["", "Abschluss-, Absage- und Wiederöffnungshistorie:"])
        lines.extend(
            f"- Revision {item['round_revision']}: {item['event_type']} ({item['created_at']})"
            for item in lifecycle["history"]
        )
        lines.extend(
            [
                "",
                "Aufbewahrung:",
                f"- bis: {lifecycle['retention']['retain_until'] or 'nicht festgelegt'}",
                f"- Sperre: {'ja' if lifecycle['retention']['legal_hold'] else 'nein'}",
                "",
                "Nachträgliche förmliche IHK-Status:",
            ]
        )
        lines.extend(
            f"- Ergebnis {item['exam_result_id']}: {item['document_status']} "
            f"({item['document_reference']})"
            for item in lifecycle["ihk_statuses"]
        )
        return "\n".join(lines) + "\n"

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
            exam_round = self._required_round(session, round_id)
            actor_id = self._require_management(exam_round, scope)
            belongs = session.scalar(
                select(ExamResult.id)
                .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
                .where(
                    ExamResult.id == result_id,
                    RoundCandidate.exam_round_id == round_id,
                )
            )
            if belongs is None:
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
            exam_round = self._required_round(session, round_id)
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
            exam_round = self._required_round(session, round_id)
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
            resolved = self._round_mutation_token(session, path_parts, payload)
            if resolved is None:
                return
            round_id, token = resolved
            exam_round = self._required_round(session, round_id)
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
        direct_models: dict[str, tuple[type[Any], str, str]] = {
            "planning-settings": (PlanningSettings, "exam_round_id", "planning"),
            "candidate-exam-days": (CandidateExamDay, "exam_round_id", "planning"),
            "member-availabilities": (MemberAvailability, "exam_round_id", "availability"),
            "round-candidates": (RoundCandidate, "exam_round_id", "candidate_assignment"),
            "confirmed-plan-days": (ExamDay, "exam_round_id", "exam_day"),
        }
        if resource in direct_models:
            model, round_field, kind = direct_models[resource]
            row = session.get(model, identifier) if identifier is not None else None
            round_id = getattr(row, round_field) if row is not None else payload.get(round_field)
            if isinstance(round_id, int) and not isinstance(round_id, bool):
                entity_id = (
                    int(round_id)
                    if kind in {"planning", "availability"}
                    else (identifier or int(round_id))
                )
                return int(round_id), _token(kind, entity_id)
        if resource == "exam-protocols" and identifier is not None:
            round_id = session.scalar(
                select(ExamDay.exam_round_id)
                .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
                .join(ExamProtocol, ExamProtocol.exam_slot_id == ExamSlot.id)
                .where(ExamProtocol.id == identifier)
            )
            return (round_id, _token("exam_protocol", identifier)) if round_id else None
        if resource == "exam-results" and identifier is not None:
            round_id = session.scalar(
                select(RoundCandidate.exam_round_id)
                .join(ExamResult, ExamResult.round_candidate_id == RoundCandidate.id)
                .where(ExamResult.id == identifier)
            )
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
        self, session: Session, exam_round: ExamRound, scope: AuthorizationScope
    ) -> dict[str, Any]:
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
        round_candidates = list(
            session.scalars(
                select(RoundCandidate)
                .where(RoundCandidate.exam_round_id == exam_round.id)
                .order_by(RoundCandidate.id)
            )
        )
        return {
            "round_id": exam_round.id,
            "revision": exam_round.revision,
            "status": exam_round.lifecycle_status,
            "legacy_status": exam_round.legacy_status,
            "historical_without_formal_evidence": (
                exam_round.lifecycle_status == "historical" and not decision_rows
            ),
            "evaluation": self._evaluate(session, exam_round, "close"),
            "candidates": [
                {
                    "round_candidate_id": item.id,
                    "candidate_id": item.candidate_id,
                    "terminal_status": item.terminal_status,
                    "terminal_reason": item.terminal_reason,
                    "effective_new_round_id": item.effective_new_round_id,
                    "postponed_until": item.postponed_until,
                    "ihk_decision_reference": item.ihk_decision_reference,
                    "terminal_at": item.terminal_at,
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
            "retention": self._retention_view(session, exam_round.id),
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
        self, session: Session, exam_round: ExamRound, decision_type: str
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        days = list(session.scalars(select(ExamDay).where(ExamDay.exam_round_id == exam_round.id)))
        day_ids = [item.id for item in days]
        slots = (
            list(session.scalars(select(ExamSlot).where(ExamSlot.exam_day_id.in_(day_ids))))
            if day_ids
            else []
        )
        candidates = list(
            session.scalars(
                select(RoundCandidate).where(
                    RoundCandidate.exam_round_id == exam_round.id,
                )
            )
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
                    item.terminal_status in TERMINAL_CANDIDATE_STATUSES - {"result_communicated"}
                    for item in candidates
                ),
                [
                    item.id
                    for item in candidates
                    if item.terminal_status
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
        non_terminal = [item.id for item in candidates if item.terminal_status == "open"]
        invalid_terminal = [
            item.id for item in candidates if not self._candidate_terminal_valid(session, item)
        ]
        self._finding(
            items,
            "candidates_terminal",
            "Jeder Prüfling besitzt einen wirksamen terminalen Status",
            not non_terminal and not invalid_terminal,
            sorted(set(non_terminal + invalid_terminal)),
        )
        result_ids = list(
            session.scalars(
                select(ExamResult.id)
                .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
                .where(RoundCandidate.exam_round_id == exam_round.id)
            )
        )
        corrections = (
            list(
                session.scalars(
                    select(ResultCorrection).where(
                        ResultCorrection.exam_result_id.in_(result_ids),
                        ResultCorrection.status == "open",
                    )
                )
            )
            if result_ids
            else []
        )
        protocol_corrections = (
            list(
                session.scalars(
                    select(ExamProtocolCorrectionRequest)
                    .join(
                        ExamProtocol,
                        ExamProtocol.id == ExamProtocolCorrectionRequest.exam_protocol_id,
                    )
                    .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                    .where(
                        ExamSlot.exam_day_id.in_(day_ids),
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
            [item.id for item in corrections] + [item.id for item in protocol_corrections],
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
        pending_consequences = list(
            session.scalars(
                select(PlanConsequence.id)
                .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
                .join(
                    ConfirmedPlanRevision,
                    ConfirmedPlanRevision.id == PlanConsequenceBatch.confirmed_plan_revision_id,
                )
                .where(
                    ConfirmedPlanRevision.exam_round_id == exam_round.id,
                    PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                )
            )
        )
        self._finding(
            items,
            "plan_consequences_complete",
            "Alle Planänderungsfolgen sind verarbeitet",
            not pending_consequences,
            pending_consequences,
        )
        return {"ready": all(item["ok"] for item in items), "items": items}

    def _snapshot(self, session: Session, exam_round: ExamRound) -> dict[str, Any]:
        half_year = session.get(ExamHalfYear, exam_round.exam_half_year_id)
        committee = session.get(Committee, exam_round.committee_id)
        members = list(
            session.scalars(
                select(CommitteeMember)
                .where(CommitteeMember.committee_id == exam_round.committee_id)
                .order_by(CommitteeMember.id)
            )
        )
        people = {item.id: item for item in session.scalars(select(Person))}
        candidates = []
        round_candidates = list(
            session.scalars(
                select(RoundCandidate)
                .where(RoundCandidate.exam_round_id == exam_round.id)
                .order_by(RoundCandidate.id)
            )
        )
        for item in round_candidates:
            person = session.get(Candidate, item.candidate_id)
            candidates.append(
                {
                    "round_candidate_id": item.id,
                    "candidate_id": person.id,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "ihk_exam_number": person.ihk_exam_number,
                    "terminal_status": item.terminal_status,
                    "terminal_reason": item.terminal_reason,
                    "effective_new_round_id": item.effective_new_round_id,
                    "postponed_until": item.postponed_until,
                    "ihk_decision_reference": item.ihk_decision_reference,
                    "terminal_at": item.terminal_at,
                }
            )
        days = list(
            session.scalars(
                select(ExamDay).where(ExamDay.exam_round_id == exam_round.id).order_by(ExamDay.id)
            )
        )
        day_ids = [item.id for item in days]
        slots = (
            list(
                session.scalars(
                    select(ExamSlot).where(ExamSlot.exam_day_id.in_(day_ids)).order_by(ExamSlot.id)
                )
            )
            if day_ids
            else []
        )
        result_rows = list(
            session.scalars(
                select(ExamResult)
                .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
                .where(RoundCandidate.exam_round_id == exam_round.id)
                .order_by(ExamResult.id)
            )
        )
        protocol_rows = (
            list(
                session.scalars(
                    select(ExamProtocol)
                    .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                    .where(ExamSlot.exam_day_id.in_(day_ids))
                    .order_by(ExamProtocol.id)
                )
            )
            if day_ids
            else []
        )
        result_ids = [item.id for item in result_rows]
        assignment_rows = (
            list(
                session.scalars(
                    select(ExamDayAssignment)
                    .where(ExamDayAssignment.exam_day_id.in_(day_ids))
                    .order_by(ExamDayAssignment.id)
                )
            )
            if day_ids
            else []
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
                "id": half_year.id,
                "season": half_year.season,
                "year": half_year.year,
                "administrative_status": half_year.status,
                "legacy_status": half_year.legacy_status,
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
                    "first_name": people[member.person_id].first_name,
                    "last_name": people[member.person_id].last_name,
                    "committee_role": member.committee_role,
                    "representing_side": member.representing_side,
                    "is_active": bool(member.is_active),
                }
                for member in members
            ],
            "candidates": candidates,
            "candidate_assignment_history": [
                {
                    "id": item.id,
                    "candidate_id": item.candidate_id,
                    "exam_round_id": item.exam_round_id,
                    "round_candidate_id": item.round_candidate_id,
                    "assigned_at": item.assigned_at,
                    "ended_at": item.ended_at,
                    "change_reason": item.change_reason,
                }
                for item in session.scalars(
                    select(CandidateCommitteeAssignment)
                    .where(
                        CandidateCommitteeAssignment.exam_half_year_id
                        == exam_round.exam_half_year_id,
                        CandidateCommitteeAssignment.candidate_id.in_(
                            [item.candidate_id for item in round_candidates]
                        ),
                    )
                    .order_by(CandidateCommitteeAssignment.id)
                )
            ],
            "plan_revisions": [
                {
                    "id": item.id,
                    "previous_revision": item.previous_revision,
                    "resulting_revision": item.resulting_revision,
                    "reason": item.reason,
                    "actor_member_id": item.actor_member_id,
                    "created_at": item.created_at,
                }
                for item in session.scalars(
                    select(ConfirmedPlanRevision)
                    .where(ConfirmedPlanRevision.exam_round_id == exam_round.id)
                    .order_by(ConfirmedPlanRevision.id)
                )
            ],
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
                    "id": item.id,
                    "round_candidate_id": item.round_candidate_id,
                    "state": item.current_state,
                    "correction_open": bool(item.correction_open),
                    "version": item.version,
                    "communications": [
                        {
                            "id": communication.id,
                            "determination_id": communication.result_determination_id,
                            "communicated_at": communication.communicated_at,
                            "method": communication.method,
                            "external_document_status": communication.external_document_status,
                            "external_document_reference": (
                                communication.external_document_reference
                            ),
                            "status": communication.status,
                        }
                        for communication in session.scalars(
                            select(ResultCommunication)
                            .where(ResultCommunication.exam_result_id == item.id)
                            .order_by(ResultCommunication.id)
                        )
                    ],
                }
                for item in result_rows
            ],
            "assessments": {
                "individual": (
                    [
                        {
                            "id": item.id,
                            "exam_result_id": item.exam_result_id,
                            "component_key": item.component_key,
                            "criterion_key": item.criterion_key,
                            "assessor_member_id": item.assessor_member_id,
                            "revision": item.revision,
                            "normalized_points": item.normalized_points,
                            "status": item.status,
                        }
                        for item in session.scalars(
                            select(IndividualAssessment)
                            .where(IndividualAssessment.exam_result_id.in_(result_ids))
                            .order_by(IndividualAssessment.id)
                        )
                    ]
                    if result_ids
                    else []
                ),
                "committee": (
                    [
                        {
                            "id": item.id,
                            "exam_result_id": item.exam_result_id,
                            "component_key": item.component_key,
                            "revision": item.revision,
                            "points": item.points,
                            "participant_member_ids": json.loads(item.participant_member_ids_json),
                            "status": item.status,
                        }
                        for item in session.scalars(
                            select(CommitteeAssessment)
                            .where(CommitteeAssessment.exam_result_id.in_(result_ids))
                            .order_by(CommitteeAssessment.id)
                        )
                    ]
                    if result_ids
                    else []
                ),
            },
        }

    def _retention_view(self, session: Session, round_id: int) -> dict[str, Any]:
        protocol_rows = list(
            session.execute(
                select(
                    ExamProtocolRetention.exam_protocol_id,
                    ExamProtocolRetention.retain_until,
                    ExamProtocolRetention.legal_hold,
                    ExamProtocolRetention.hold_reason,
                )
                .join(ExamProtocol, ExamProtocol.id == ExamProtocolRetention.exam_protocol_id)
                .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                .join(ExamDay, ExamDay.id == ExamSlot.exam_day_id)
                .where(ExamDay.exam_round_id == round_id)
            )
        )
        result_rows = list(
            session.execute(
                select(
                    ResultRetention.exam_result_id,
                    ResultRetention.retain_until,
                    ResultRetention.legal_hold,
                    ResultRetention.hold_reason,
                )
                .join(ExamResult, ExamResult.id == ResultRetention.exam_result_id)
                .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
                .where(RoundCandidate.exam_round_id == round_id)
            )
        )
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
                "id": row.exam_result_id,
                "retain_until": row.retain_until,
                "legal_hold": bool(row.legal_hold),
                "hold_reason": row.hold_reason,
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

    def _impact(self, session: Session, exam_round: ExamRound, raw_scope: Any) -> dict[str, Any]:
        requested = self._normalize_scope(raw_scope)
        day_ids = set(
            session.scalars(select(ExamDay.id).where(ExamDay.exam_round_id == exam_round.id))
        )
        candidate_ids = set(
            session.scalars(
                select(RoundCandidate.id).where(RoundCandidate.exam_round_id == exam_round.id)
            )
        )
        protocol_ids = (
            set(
                session.scalars(
                    select(ExamProtocol.id)
                    .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                    .where(ExamSlot.exam_day_id.in_(day_ids))
                )
            )
            if day_ids
            else set()
        )
        result_ids = set(
            session.scalars(
                select(ExamResult.id)
                .join(RoundCandidate, RoundCandidate.id == ExamResult.round_candidate_id)
                .where(RoundCandidate.exam_round_id == exam_round.id)
            )
        )
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
                day_slot_ids = set(
                    session.scalars(select(ExamSlot.id).where(ExamSlot.exam_day_id == entity_id))
                )
                expanded.update(
                    _token("exam_protocol", item)
                    for item in session.scalars(
                        select(ExamProtocol.id).where(ExamProtocol.exam_slot_id.in_(day_slot_ids))
                    )
                )
                day_candidate_ids = set(
                    session.scalars(
                        select(ExamSlot.round_candidate_id).where(ExamSlot.id.in_(day_slot_ids))
                    )
                )
                expanded.update(
                    _token("exam_result", item)
                    for item in session.scalars(
                        select(ExamResult.id).where(
                            ExamResult.round_candidate_id.in_(day_candidate_ids)
                        )
                    )
                )
        impacted_result_ids = sorted(
            int(item.split(":", 1)[1]) for item in expanded if item.startswith("exam_result:")
        )
        recipients = self._management_member_ids(session, exam_round)
        for result_id in impacted_result_ids:
            determination = session.scalar(
                select(ResultDetermination).where(
                    ResultDetermination.exam_result_id == result_id,
                    ResultDetermination.status == "current",
                )
            )
            if determination is not None:
                recipients.update(json.loads(determination.participant_member_ids_json))
        ihk_processed = [
            result_id
            for result_id in impacted_result_ids
            if session.scalar(
                select(func.count())
                .select_from(ResultCommunication)
                .where(
                    ResultCommunication.exam_result_id == result_id,
                    ResultCommunication.external_document_status.is_not(None),
                )
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

    def _apply_cancellation(self, session: Session, exam_round: ExamRound, now: str) -> set[int]:
        recipients = self._management_member_ids(session, exam_round)
        days = list(session.scalars(select(ExamDay).where(ExamDay.exam_round_id == exam_round.id)))
        day_ids = [item.id for item in days]
        for day in days:
            day.status = "cancelled"
            day.updated_at = now
        if day_ids:
            for slot in session.scalars(select(ExamSlot).where(ExamSlot.exam_day_id.in_(day_ids))):
                slot.status = "cancelled"
                slot.execution_status = "cancelled"
                slot.status_reason = "Prüfungsrunde vollständig abgesagt"
                slot.status_changed_at = now
                slot.updated_at = now
            recipients.update(
                session.scalars(
                    select(ExamDayAssignment.committee_member_id).where(
                        ExamDayAssignment.exam_day_id.in_(day_ids)
                    )
                )
            )
        for event in session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.exam_round_id == exam_round.id,
                CalendarEvent.date >= now[:10],
                CalendarEvent.status != "cancelled",
            )
        ):
            event.status = "cancelled"
            event.version += 1
            event.updated_at = now
            recipients.add(event.recipient_member_id)
        return recipients

    def _candidate_terminal_valid(self, session: Session, candidate: RoundCandidate) -> bool:
        if candidate.terminal_status == "result_communicated":
            try:
                self._assert_result_communicated(session, candidate)
            except ValueError:
                return False
            return True
        if candidate.terminal_status == "transferred":
            if (
                candidate.effective_new_round_id is None
                or not candidate.terminal_reason
                or candidate.is_active
                or not self._original_assignment_ended(session, candidate)
            ):
                return False
            return (
                session.scalar(
                    select(CandidateCommitteeAssignment.id).where(
                        CandidateCommitteeAssignment.candidate_id == candidate.candidate_id,
                        CandidateCommitteeAssignment.exam_round_id
                        == candidate.effective_new_round_id,
                        CandidateCommitteeAssignment.ended_at.is_(None),
                    )
                )
                is not None
            )
        if candidate.terminal_status == "postponed":
            return bool(
                candidate.terminal_reason
                and candidate.postponed_until
                and not candidate.is_active
                and self._original_assignment_ended(session, candidate)
            )
        if candidate.terminal_status == "ihk_terminated":
            return bool(
                candidate.terminal_reason
                and candidate.ihk_decision_reference
                and not candidate.is_active
                and self._original_assignment_ended(session, candidate)
            )
        return False

    @staticmethod
    def _original_assignment_ended(session: Session, candidate: RoundCandidate) -> bool:
        assignment = session.scalar(
            select(CandidateCommitteeAssignment).where(
                CandidateCommitteeAssignment.round_candidate_id == candidate.id,
                CandidateCommitteeAssignment.exam_round_id == candidate.exam_round_id,
            )
        )
        return assignment is not None and assignment.ended_at is not None

    @staticmethod
    def _assert_result_communicated(session: Session, candidate: RoundCandidate) -> None:
        result = session.scalar(
            select(ExamResult).where(ExamResult.round_candidate_id == candidate.id)
        )
        if result is None or result.current_state != "determined" or result.correction_open:
            raise ValueError("Das Ergebnis ist nicht vollständig festgestellt")
        determination = session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == result.id,
                ResultDetermination.status == "current",
            )
        )
        communication = session.scalar(
            select(ResultCommunication).where(
                ResultCommunication.exam_result_id == result.id,
                ResultCommunication.status == "current",
            )
        )
        if determination is None or communication is None:
            raise ValueError("Ergebnisfeststellung und Ergebnismitteilung sind erforderlich")
        unconfirmed_external = session.scalar(
            select(func.count())
            .select_from(ExternalExamResult)
            .where(
                ExternalExamResult.exam_result_id == result.id,
                ExternalExamResult.status != "confirmed",
            )
        )
        if unconfirmed_external:
            raise ValueError("Externe Eingangsergebnisse sind noch nicht bestätigt")

    def _dependency_counts(self, session: Session, exam_round: ExamRound) -> dict[str, int]:
        day_ids = select(ExamDay.id).where(ExamDay.exam_round_id == exam_round.id)
        return {
            "Prüflinge": self._count(
                session, RoundCandidate, RoundCandidate.exam_round_id == exam_round.id
            ),
            "Verfügbarkeiten": self._count(
                session, MemberAvailability, MemberAvailability.exam_round_id == exam_round.id
            ),
            "Planungsparameter": self._count(
                session, PlanningSettings, PlanningSettings.exam_round_id == exam_round.id
            ),
            "Planrevisionen": self._count(
                session, ConfirmedPlanRevision, ConfirmedPlanRevision.exam_round_id == exam_round.id
            ),
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

    def _require_mutable_scope(self, session: Session, exam_round: ExamRound, token: str) -> None:
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
    def _required_round(session: Session, round_id: int) -> ExamRound:
        exam_round = session.get(ExamRound, round_id)
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
    def _require_access(exam_round: ExamRound, scope: AuthorizationScope) -> int | None:
        if not scope.can_read_committee(exam_round.committee_id):
            raise PermissionError("Forbidden.")
        return scope.member_for_committee(exam_round.committee_id)

    def _require_management(self, exam_round: ExamRound, scope: AuthorizationScope) -> int:
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
    def _management_member_ids(session: Session, exam_round: ExamRound) -> set[int]:
        return set(
            session.scalars(
                select(CommitteeMember.id).where(
                    CommitteeMember.committee_id == exam_round.committee_id,
                    CommitteeMember.is_active == 1,
                    CommitteeMember.committee_role.in_({"chair", "deputy_chair"}),
                )
            )
        )

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
