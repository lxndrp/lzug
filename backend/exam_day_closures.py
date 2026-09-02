"""Revision-bound formal closure and targeted reopening of complete exam days."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    AbsenceReport,
    AssessmentModelVersion,
    CandidateExamAttendance,
    CommitteeAssessment,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamDayAuditEvent,
    ExamDayClosure,
    ExamDayExport,
    ExamDayReopening,
    ExamDayTask,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolEntry,
    ExamProtocolParticipant,
    ExamProtocolResponse,
    ExamProtocolRevision,
    ExamResult,
    ExamRound,
    ExamRoundAssessmentBinding,
    ExamSlot,
    ExternalExamResult,
    IndividualAssessment,
    MemberExamAttendance,
    ResultCommunication,
    ResultCorrection,
    ResultDetermination,
    ResultRecordConfirmation,
    RoundCandidate,
)
from .notifications import NotificationService

CLOSED_STATUSES = {"closed", "closed_exception", "historical"}
TERMINAL_SLOT_STATUSES = {"completed", "cancelled"}
TERMINAL_ABSENCE_STATUSES = {
    "replacement_selected",
    "resolved",
    "withdrawn",
    "exam_day_cancelled",
}
COMPLETE_PROTOCOL_STATES = {"fully_confirmed", "fully_with_reservation"}
POST_CLOSE_RESULT_KINDS = {
    "result_external",
    "result_determine",
    "result_confirm_record",
    "result_communicate",
    "result_retention",
}
REOPENING_SCOPE_KINDS = {
    "slot_status",
    "candidate_attendance",
    "member_attendance",
    "staffing",
    "absence",
    "exam_protocol",
    "exam_result",
}


class ExamDayConflictError(ValueError):
    """Signal a stale, repeated-with-different-content, or parallel day command."""


class ExamDayValidationError(ValueError):
    """Expose the complete failed prerequisite matrix for one close attempt."""

    def __init__(self, message: str, findings: list[dict[str, Any]]):
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class DayMutationGuard:
    day: ExamDay
    token: str
    reopening: ExamDayReopening | None
    touch_revision: bool
    late_protocol_response: bool = False


@dataclass(frozen=True)
class NotificationJob:
    recipient_member_ids: set[int]
    event_type: str
    title: str
    message: str
    origin_key: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _token(kind: str, entity_id: int) -> str:
    return f"{kind}:{entity_id}"


def _mutation_scope_kind(kind: str) -> str:
    if kind in {"protocol_response", "protocol_correction_request"}:
        return "exam_protocol"
    if kind.startswith("result_"):
        return "exam_result"
    return kind


def _supplied_day_revision(payload: dict[str, Any], day_id: int) -> Any:
    revisions = payload.get("day_revisions")
    if isinstance(revisions, dict):
        return revisions.get(str(day_id), revisions.get(day_id))
    return payload.get("day_revision")


def day_for_protocol(session: Session, protocol_id: int) -> ExamDay | None:
    return session.scalar(
        select(ExamDay)
        .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
        .join(ExamProtocol, ExamProtocol.exam_slot_id == ExamSlot.id)
        .where(ExamProtocol.id == protocol_id)
    )


def days_for_result(session: Session, result_id: int) -> list[ExamDay]:
    return list(
        session.scalars(
            select(ExamDay)
            .join(ExamSlot, ExamSlot.exam_day_id == ExamDay.id)
            .join(RoundCandidate, RoundCandidate.id == ExamSlot.round_candidate_id)
            .join(ExamResult, ExamResult.round_candidate_id == RoundCandidate.id)
            .where(ExamResult.id == result_id)
            .order_by(ExamDay.id)
        ).unique()
    )


def guard_day_mutation(
    session: Session,
    *,
    day: ExamDay,
    kind: str,
    entity_id: int,
    payload: dict[str, Any],
    actor_member_id: int | None,
    protocol_revision_id: int | None = None,
) -> DayMutationGuard:
    """Enforce the shared UI/direct-API lock before a day-related mutation."""
    token = _token(_mutation_scope_kind(kind), entity_id)
    supplied = _supplied_day_revision(payload, day.id)
    if day.closure_status == "open":
        return _guard_open_day_mutation(day, token, supplied)

    if kind in POST_CLOSE_RESULT_KINDS or kind == "protocol_correction_request":
        return DayMutationGuard(day, token, None, False)

    if day.closure_status == "closed_exception" and kind == "protocol_response":
        return _guard_late_protocol_response(
            session, day, token, actor_member_id, protocol_revision_id
        )
    return _guard_reopening_mutation(session, day, token, supplied)


def _guard_open_day_mutation(day: ExamDay, token: str, supplied: Any) -> DayMutationGuard:
    if supplied is not None and supplied != day.revision:
        raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
    return DayMutationGuard(day, token, None, True)


def _guard_late_protocol_response(
    session: Session,
    day: ExamDay,
    token: str,
    actor_member_id: int | None,
    protocol_revision_id: int | None,
) -> DayMutationGuard:
    if actor_member_id is None or protocol_revision_id is None:
        raise PermissionError("Forbidden.")
    task = session.scalar(
        select(ExamDayTask).where(
            ExamDayTask.exam_day_id == day.id,
            ExamDayTask.task_type == "protocol_follow_up",
            ExamDayTask.recipient_member_id == actor_member_id,
            ExamDayTask.exam_protocol_revision_id == protocol_revision_id,
            ExamDayTask.status == "open",
        )
    )
    if task is None:
        raise ExamDayConflictError(
            "Für diesen geschlossenen Protokollstand besteht keine offene Nachfassaufgabe"
        )
    return DayMutationGuard(day, token, None, False, late_protocol_response=True)


def _guard_reopening_mutation(
    session: Session, day: ExamDay, token: str, supplied: Any
) -> DayMutationGuard:
    if day.closure_status != "reopening":
        raise ExamDayConflictError(
            "Geschlossene Tagesdaten können nur über eine zielgerichtete "
            "Wiederöffnung geändert werden"
        )
    reopening = session.scalar(
        select(ExamDayReopening).where(
            ExamDayReopening.exam_day_id == day.id,
            ExamDayReopening.status == "open",
        )
    )
    if reopening is None:
        raise ExamDayConflictError("Der Wiederöffnungsstand des Prüfungstags ist inkonsistent")
    if not isinstance(supplied, int) or isinstance(supplied, bool):
        raise ExamDayConflictError("Eine Korrektur benötigt die aktuelle Tagesrevision")
    if supplied != day.revision:
        raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
    if token not in set(json.loads(reopening.scope_json)):
        raise ExamDayConflictError(
            "Diese Daten gehören nicht zum ausdrücklich wieder geöffneten Korrekturumfang"
        )
    return DayMutationGuard(day, token, reopening, True)


def complete_day_mutation(
    session: Session,
    guard: DayMutationGuard,
    *,
    actor_member_id: int,
    reason: str | None = None,
    protocol_revision_id: int | None = None,
) -> None:
    """Advance the day revision only after the guarded mutation really changed state."""
    now = _now()
    if guard.touch_revision:
        guard.day.revision += 1
        guard.day.updated_at = now
        if guard.reopening is not None:
            completed = set(json.loads(guard.reopening.completed_scope_json))
            completed.add(guard.token)
            guard.reopening.completed_scope_json = _json(sorted(completed))
            session.add(
                ExamDayAuditEvent(
                    exam_day_id=guard.day.id,
                    day_revision=guard.day.revision,
                    event_type="correction",
                    actor_member_id=actor_member_id,
                    reopening_id=guard.reopening.id,
                    reason=reason,
                    scope_json=_json([guard.token]),
                    created_at=now,
                )
            )
    if guard.late_protocol_response:
        task = session.scalar(
            select(ExamDayTask).where(
                ExamDayTask.exam_day_id == guard.day.id,
                ExamDayTask.task_type == "protocol_follow_up",
                ExamDayTask.recipient_member_id == actor_member_id,
                ExamDayTask.exam_protocol_revision_id == protocol_revision_id,
                ExamDayTask.status == "open",
            )
        )
        if task is not None:
            task.status = "completed"
            task.completed_at = now
        session.add(
            ExamDayAuditEvent(
                exam_day_id=guard.day.id,
                day_revision=guard.day.revision,
                event_type="late_protocol_response",
                actor_member_id=actor_member_id,
                reason=reason,
                scope_json=_json([guard.token]),
                created_at=now,
            )
        )


class ExamDayClosureService:
    """Evaluate, close, reopen, trace, notify, and export one whole exam day."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.db_path = db_path
        self.notification_service = notification_service or NotificationService(db_path)

    def get(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, day_id)
            if day is None:
                return None
            self._require_access(session, day, scope)
            return self._view(session, day, scope)

    def close(
        self, scope: AuthorizationScope, day_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_revision, closure_type, reason, attempts, fingerprint = self._close_command(
            payload
        )
        notification_jobs: list[NotificationJob] = []
        with session_scope(self.db_path) as session:
            day = self._required_day(session, day_id)
            actor_id, committee_id, round_id = self._require_management(session, day, scope)
            if self._repeated_closure(session, day.id, fingerprint):
                return self._view(session, day, scope)
            reopening = self._prepare_closure(session, day, expected_revision)
            evaluation = self._evaluate(session, day)
            ready_key = (
                "regular_close_ready" if closure_type == "regular" else "exception_close_ready"
            )
            if not evaluation[ready_key]:
                raise ExamDayValidationError(
                    "Die Voraussetzungen für diesen Tagesabschluss sind nicht erfüllt",
                    [item for item in evaluation["items"] if not item["ok"]],
                )
            notification_jobs.extend(
                self._record_closure(
                    session,
                    day,
                    reopening,
                    evaluation,
                    closure_type,
                    actor_id,
                    reason,
                    attempts,
                    fingerprint,
                )
            )
            result = self._view(session, day, scope)
        self._notify(committee_id, round_id, day_id, notification_jobs)
        return result

    def _close_command(
        self, payload: dict[str, Any]
    ) -> tuple[int, str, str | None, str | None, str]:
        expected_revision = self._required_revision(payload)
        closure_type = payload.get("closure_type", "regular")
        if closure_type not in {"regular", "exception"}:
            raise ValueError("Unbekannte Abschlussart")
        if payload.get("confirmed") is not True:
            raise ValueError("Die angezeigten Abschlussvoraussetzungen müssen bestätigt werden")
        reason = self._optional_text(payload.get("reason"), 3000)
        attempts = self._optional_text(payload.get("clarification_attempts"), 3000)
        if closure_type == "regular":
            reason, attempts = None, None
        if closure_type == "exception" and (reason is None or attempts is None):
            raise ValueError(
                "Ein Ausnahmeabschluss benötigt Grund und dokumentierte Klärungsversuche"
            )
        command = {
            "revision": expected_revision,
            "closure_type": closure_type,
            "confirmed": True,
            "reason": reason,
            "clarification_attempts": attempts,
        }
        return expected_revision, closure_type, reason, attempts, _fingerprint(command)

    @staticmethod
    def _repeated_closure(session: Session, day_id: int, fingerprint: str) -> bool:
        return (
            session.scalar(
                select(ExamDayClosure).where(
                    ExamDayClosure.exam_day_id == day_id,
                    ExamDayClosure.command_fingerprint == fingerprint,
                )
            )
            is not None
        )

    def _prepare_closure(
        self, session: Session, day: ExamDay, expected_revision: int
    ) -> ExamDayReopening | None:
        if day.revision != expected_revision:
            raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
        if day.closure_status not in {"open", "reopening"}:
            raise ExamDayConflictError("Der Prüfungstag ist bereits formal geschlossen")
        reopening = self._active_reopening(session, day.id)
        if day.closure_status == "reopening":
            if reopening is None:
                raise ExamDayConflictError("Der Wiederöffnungsstand ist inkonsistent")
            self._require_reopening_completed(reopening)
        return reopening

    @staticmethod
    def _require_reopening_completed(reopening: ExamDayReopening) -> None:
        requested = set(json.loads(reopening.requested_scope_json))
        completed = set(json.loads(reopening.completed_scope_json))
        if requested.issubset(completed):
            return
        raise ExamDayValidationError(
            "Der wieder geöffnete Korrekturumfang ist noch nicht vollständig bearbeitet",
            [
                {
                    "code": "reopening_scope_unresolved",
                    "label": "Korrekturumfang bearbeiten",
                    "ok": False,
                    "details": sorted(requested - completed),
                }
            ],
        )

    def _record_closure(
        self,
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening | None,
        evaluation: dict[str, Any],
        closure_type: str,
        actor_id: int,
        reason: str | None,
        attempts: str | None,
        fingerprint: str,
    ) -> list[NotificationJob]:
        previous = self._current_or_latest_closure(session, day.id)
        if previous is not None:
            previous.status = "superseded"
        now = _now()
        closure = self._new_closure(
            day, previous, evaluation, closure_type, actor_id, reason, attempts, fingerprint, now
        )
        session.add(closure)
        session.flush()
        self._close_day(day, closure_type, now)
        self._complete_reopening(session, reopening, now)
        self._add_closure_audit(
            session, day, closure, reopening, closure_type, actor_id, reason, now
        )
        return self._closure_notification_jobs(
            session, day, closure, reopening, evaluation, closure_type, reason, attempts, now
        )

    @staticmethod
    def _new_closure(
        day: ExamDay,
        previous: ExamDayClosure | None,
        evaluation: dict[str, Any],
        closure_type: str,
        actor_id: int,
        reason: str | None,
        attempts: str | None,
        fingerprint: str,
        now: str,
    ) -> ExamDayClosure:
        return ExamDayClosure(
            exam_day_id=day.id,
            requested_revision=day.revision,
            resulting_revision=day.revision + 1,
            closure_type=closure_type,
            actor_member_id=actor_id,
            reason=reason,
            clarification_attempts=attempts,
            checklist_json=_json(evaluation["items"]),
            warnings_json=_json(evaluation["warnings"]),
            protocol_references_json=_json(evaluation["protocol_references"]),
            result_references_json=_json(evaluation["result_references"]),
            previous_closure_id=previous.id if previous else None,
            status="current",
            command_fingerprint=fingerprint,
            closed_at=now,
        )

    @staticmethod
    def _close_day(day: ExamDay, closure_type: str, now: str) -> None:
        day.revision += 1
        day.closure_status = "closed" if closure_type == "regular" else "closed_exception"
        day.updated_at = now

    @staticmethod
    def _complete_reopening(session: Session, reopening: ExamDayReopening | None, now: str) -> None:
        if reopening is None:
            return
        reopening.status = "completed"
        reopening.completed_at = now
        for task in session.scalars(
            select(ExamDayTask).where(
                ExamDayTask.reopening_id == reopening.id,
                ExamDayTask.status == "open",
            )
        ):
            task.status = "completed"
            task.completed_at = now

    @staticmethod
    def _add_closure_audit(
        session: Session,
        day: ExamDay,
        closure: ExamDayClosure,
        reopening: ExamDayReopening | None,
        closure_type: str,
        actor_id: int,
        reason: str | None,
        now: str,
    ) -> None:
        event_type = (
            "reclosed"
            if reopening
            else f"closed{('_' + closure_type) if closure_type == 'exception' else ''}"
        )
        session.add(
            ExamDayAuditEvent(
                exam_day_id=day.id,
                day_revision=day.revision,
                event_type=event_type,
                actor_member_id=actor_id,
                closure_id=closure.id,
                reopening_id=reopening.id if reopening else None,
                reason=reason,
                scope_json=reopening.requested_scope_json if reopening else "[]",
                created_at=now,
            )
        )

    def _closure_notification_jobs(
        self,
        session: Session,
        day: ExamDay,
        closure: ExamDayClosure,
        reopening: ExamDayReopening | None,
        evaluation: dict[str, Any],
        closure_type: str,
        reason: str | None,
        attempts: str | None,
        now: str,
    ) -> list[NotificationJob]:
        if closure_type == "exception":
            return [
                self._exception_close_job(session, day, closure, evaluation, reason, attempts, now)
            ]
        if reopening is None:
            return []
        recipients = self._affected_recipient_ids(session, reopening)
        if not recipients:
            return []
        return [
            NotificationJob(
                recipients,
                "exam_day_reclosed",
                "Prüfungstag erneut abgeschlossen",
                "Der korrigierte Prüfungstag wurde erneut formal abgeschlossen.",
                f"exam-day-reopening:{reopening.id}:reclosed",
            )
        ]

    @staticmethod
    def _exception_close_job(
        session: Session,
        day: ExamDay,
        closure: ExamDayClosure,
        evaluation: dict[str, Any],
        reason: str | None,
        attempts: str | None,
        now: str,
    ) -> NotificationJob:
        candidate = evaluation["exception_candidate"]
        session.add(
            ExamDayTask(
                exam_day_id=day.id,
                recipient_member_id=candidate["committee_member_id"],
                task_type="protocol_follow_up",
                origin_key=f"exam-day-closure:{closure.id}:protocol-follow-up",
                exam_protocol_revision_id=candidate["exam_protocol_revision_id"],
                details_json=_json(
                    {
                        "reason": reason,
                        "clarification_attempts": attempts,
                        "exam_protocol_id": candidate["exam_protocol_id"],
                    }
                ),
                status="open",
                created_at=now,
            )
        )
        return NotificationJob(
            {candidate["committee_member_id"]},
            "exam_day_protocol_follow_up",
            "Protokollreaktion ausstehend",
            "Ein Prüfungstag wurde mit Ausnahme geschlossen. Bitte reagieren Sie "
            "auf den unveränderten Protokollstand.",
            f"exam-day-closure:{closure.id}:protocol-follow-up",
        )

    def reopening_impact(
        self, scope: AuthorizationScope, day_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            day = self._required_day(session, day_id)
            self._require_management(session, day, scope)
            if day.closure_status not in CLOSED_STATUSES:
                raise ExamDayConflictError(
                    "Nur ein geschlossener Prüfungstag kann wieder geöffnet werden"
                )
            if self._active_reopening(session, day.id) is not None:
                raise ExamDayConflictError("Für den Prüfungstag läuft bereits eine Wiederöffnung")
            return self._impact(session, day, payload.get("scope"))

    def reopen(
        self, scope: AuthorizationScope, day_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        expected_revision = self._required_revision(payload)
        occasion = self._required_text(payload.get("occasion"), "occasion", 1000)
        source = self._required_text(payload.get("source"), "source", 1000)
        reason = self._required_text(payload.get("reason"), "reason", 3000)
        command = {
            "revision": expected_revision,
            "occasion": occasion,
            "source": source,
            "reason": reason,
            "scope": self._normalize_scope(payload.get("scope")),
        }
        fingerprint = _fingerprint(command)
        notification_jobs: list[NotificationJob] = []
        with session_scope(self.db_path) as session:
            day = self._required_day(session, day_id)
            actor_id, committee_id, round_id = self._require_management(session, day, scope)
            repeated = session.scalar(
                select(ExamDayReopening).where(
                    ExamDayReopening.exam_day_id == day.id,
                    ExamDayReopening.command_fingerprint == fingerprint,
                )
            )
            if repeated is not None:
                return self._view(session, day, scope)
            if day.revision != expected_revision:
                raise ExamDayConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
            if day.closure_status not in CLOSED_STATUSES:
                raise ExamDayConflictError(
                    "Nur ein geschlossener Prüfungstag kann wieder geöffnet werden"
                )
            if self._active_reopening(session, day.id) is not None:
                raise ExamDayConflictError("Für den Prüfungstag läuft bereits eine Wiederöffnung")
            impact = self._impact(session, day, payload.get("scope"))
            now = _now()
            previous = self._current_or_latest_closure(session, day.id)
            if previous is not None:
                previous.status = "superseded"
            reopening = ExamDayReopening(
                exam_day_id=day.id,
                previous_closure_id=previous.id if previous else None,
                requested_revision=day.revision,
                resulting_revision=day.revision + 1,
                occasion=occasion,
                source=source,
                reason=reason,
                requested_scope_json=_json(impact["requested_scope"]),
                scope_json=_json(impact["expanded_scope"]),
                completed_scope_json="[]",
                impacts_json=_json(impact["impacts"]),
                actor_member_id=actor_id,
                status="open",
                command_fingerprint=fingerprint,
                opened_at=now,
            )
            session.add(reopening)
            session.flush()
            day.revision += 1
            day.closure_status = "reopening"
            day.updated_at = now
            self._open_dependent_corrections(session, day, reopening, impact, actor_id, reason, now)
            session.add(
                ExamDayAuditEvent(
                    exam_day_id=day.id,
                    day_revision=day.revision,
                    event_type="reopened",
                    actor_member_id=actor_id,
                    reopening_id=reopening.id,
                    reason=reason,
                    scope_json=reopening.requested_scope_json,
                    created_at=now,
                )
            )
            recipients = set(impact["impacts"]["recipient_member_ids"])
            if recipients:
                notification_jobs.append(
                    NotificationJob(
                        recipients,
                        "exam_day_reopened",
                        "Prüfungstag zur Korrektur wieder geöffnet",
                        "Von Ihnen erfasste oder bestätigte Daten sind von einer begründeten "
                        "Korrektur betroffen.",
                        f"exam-day-reopening:{reopening.id}:affected",
                    )
                )
            result = self._view(session, day, scope)
        self._notify(committee_id, round_id, day_id, notification_jobs)
        return result

    def machine_export(self, scope: AuthorizationScope, day_id: int) -> dict[str, Any]:
        return self._export(scope, day_id, "machine")

    def _export(self, scope: AuthorizationScope, day_id: int, export_kind: str) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            day = self._required_day(session, day_id)
            actor_id, _committee_id, _round_id = self._require_access(session, day, scope)
            if actor_id is None:
                raise PermissionError("Forbidden.")
            closure = self._current_or_latest_closure(session, day.id)
            session.add(
                ExamDayExport(
                    exam_day_id=day.id,
                    closure_id=closure.id if closure else None,
                    export_kind=export_kind,
                    status=day.closure_status,
                    generated_by_member_id=actor_id,
                    generated_at=_now(),
                )
            )
            session.flush()
            return {
                "export_version": 1,
                "exam_day": {"id": day.id, "date": day.date, "exam_round_id": day.exam_round_id},
                "closure": self._view(session, day, scope),
            }

    def human_export(self, scope: AuthorizationScope, day_id: int) -> str:
        export = self._export(scope, day_id, "human")
        day = export["exam_day"]
        closure = export["closure"]
        lines = [
            f"Abschlussnachweis Prüfungstag {day['id']}",
            f"Datum: {day['date']}",
            f"Status: {closure['status']}",
            f"Tagesrevision: {closure['revision']}",
            "",
            "Abschlussvoraussetzungen:",
        ]
        lines.extend(
            f"- {'erfüllt' if item['ok'] else 'nicht erfüllt'}: {item['label']}"
            for item in closure["evaluation"]["items"]
        )
        if closure["history"]:
            lines.extend(["", "Abschluss- und Wiederöffnungshistorie:"])
            lines.extend(
                f"- {item['kind']} · Revision {item['revision']} · {item['created_at']}"
                for item in closure["history"]
            )
        return "\n".join(lines) + "\n"

    def _view(self, session: Session, day: ExamDay, scope: AuthorizationScope) -> dict[str, Any]:
        actor_id, _committee_id, _round_id = self._require_access(session, day, scope)
        evaluation = self._evaluate(session, day)
        closures = list(
            session.scalars(
                select(ExamDayClosure)
                .where(ExamDayClosure.exam_day_id == day.id)
                .order_by(ExamDayClosure.id)
            )
        )
        reopenings = list(
            session.scalars(
                select(ExamDayReopening)
                .where(ExamDayReopening.exam_day_id == day.id)
                .order_by(ExamDayReopening.id)
            )
        )
        events: list[dict[str, Any]] = []
        for item in closures:
            events.append(
                {
                    "kind": "closure",
                    "id": item.id,
                    "revision": item.resulting_revision,
                    "closure_type": item.closure_type,
                    "actor_member_id": item.actor_member_id,
                    "reason": item.reason,
                    "clarification_attempts": item.clarification_attempts,
                    "status": item.status,
                    "created_at": item.closed_at,
                    "checklist": json.loads(item.checklist_json),
                    "warnings": json.loads(item.warnings_json),
                    "protocol_references": json.loads(item.protocol_references_json),
                    "result_references": json.loads(item.result_references_json),
                }
            )
        for item in reopenings:
            events.append(
                {
                    "kind": "reopening",
                    "id": item.id,
                    "revision": item.resulting_revision,
                    "actor_member_id": item.actor_member_id,
                    "occasion": item.occasion,
                    "source": item.source,
                    "reason": item.reason,
                    "requested_scope": json.loads(item.requested_scope_json),
                    "expanded_scope": json.loads(item.scope_json),
                    "completed_scope": json.loads(item.completed_scope_json),
                    "impacts": json.loads(item.impacts_json),
                    "status": item.status,
                    "created_at": item.opened_at,
                    "completed_at": item.completed_at,
                }
            )
        for item in session.scalars(
            select(ExamDayAuditEvent)
            .where(ExamDayAuditEvent.exam_day_id == day.id)
            .order_by(ExamDayAuditEvent.id)
        ):
            events.append(
                {
                    "kind": "audit",
                    "id": item.id,
                    "revision": item.day_revision,
                    "event_type": item.event_type,
                    "actor_member_id": item.actor_member_id,
                    "closure_id": item.closure_id,
                    "reopening_id": item.reopening_id,
                    "reason": item.reason,
                    "scope": json.loads(item.scope_json),
                    "created_at": item.created_at,
                }
            )
        for item in session.scalars(
            select(ExamDayExport)
            .where(ExamDayExport.exam_day_id == day.id)
            .order_by(ExamDayExport.id)
        ):
            events.append(
                {
                    "kind": "export",
                    "id": item.id,
                    "revision": day.revision,
                    "export_kind": item.export_kind,
                    "closure_id": item.closure_id,
                    "status": item.status,
                    "actor_member_id": item.generated_by_member_id,
                    "created_at": item.generated_at,
                }
            )
        tasks = list(
            session.scalars(
                select(ExamDayTask)
                .where(ExamDayTask.exam_day_id == day.id)
                .order_by(ExamDayTask.id)
            )
        )
        return {
            "exam_day_id": day.id,
            "revision": day.revision,
            "status": day.closure_status,
            "legacy_status": day.status if day.closure_status == "historical" else None,
            "evaluation": evaluation,
            "active_reopening": next(
                (
                    item
                    for item in events
                    if item["kind"] == "reopening" and item["status"] == "open"
                ),
                None,
            ),
            "history": sorted(events, key=lambda item: (item["revision"], item["id"])),
            "tasks": [
                {
                    "id": item.id,
                    "reopening_id": item.reopening_id,
                    "recipient_member_id": item.recipient_member_id,
                    "task_type": item.task_type,
                    "origin_key": item.origin_key,
                    "exam_protocol_revision_id": item.exam_protocol_revision_id,
                    "result_determination_id": item.result_determination_id,
                    "details": json.loads(item.details_json),
                    "status": item.status,
                    "created_at": item.created_at,
                    "completed_at": item.completed_at,
                }
                for item in tasks
            ],
            "permissions": {
                "close": scope.can_manage_committee(_committee_id)
                and day.closure_status in {"open", "reopening"},
                "reopen": scope.can_manage_committee(_committee_id)
                and day.closure_status in CLOSED_STATUSES,
                "export": actor_id is not None,
            },
            "_links": {
                "self": {"href": f"/api/confirmed-plan-days/{day.id}/closure"},
                "machine_export": {
                    "href": f"/api/confirmed-plan-days/{day.id}/closure/export.json"
                },
                "human_export": {"href": f"/api/confirmed-plan-days/{day.id}/closure/export.txt"},
            },
        }

    def _evaluate(self, session: Session, day: ExamDay) -> dict[str, Any]:
        slots = list(
            session.scalars(
                select(ExamSlot).where(ExamSlot.exam_day_id == day.id).order_by(ExamSlot.id)
            )
        )
        items: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        protocol_references: list[dict[str, Any]] = []
        result_references: list[dict[str, Any]] = []
        self._evaluate_slot_execution(session, slots, items)
        self._evaluate_staffing(session, day, slots, items)
        self._evaluate_absence_processes(session, day, items)
        exception_candidates = self._evaluate_protocols(
            session, slots, items, warnings, protocol_references
        )
        self._evaluate_results(session, slots, items, result_references)

        regular_ready = all(item["ok"] for item in items)
        non_protocol_ready = all(
            item["ok"] for item in items if item["code"] != "protocols_complete"
        )
        exception_only_one = len(exception_candidates) == 1
        return {
            "items": items,
            "warnings": warnings,
            "regular_close_ready": regular_ready,
            "exception_close_ready": non_protocol_ready and exception_only_one,
            "exception_candidate": exception_candidates[0] if exception_only_one else None,
            "protocol_references": protocol_references,
            "result_references": result_references,
        }

    def _evaluate_slot_execution(
        self, session: Session, slots: list[ExamSlot], items: list[dict[str, Any]]
    ) -> None:
        self._finding(items, "day_has_slots", "Der Prüfungstag enthält Prüfungsslots", bool(slots))
        terminal = [
            slot.id for slot in slots if slot.execution_status not in TERMINAL_SLOT_STATUSES
        ]
        self._finding(
            items,
            "slots_terminal",
            "Alle Slots sind abgeschlossen oder begründet ausgefallen",
            not terminal,
            terminal,
        )
        cancelled_without_reason = [
            slot.id
            for slot in slots
            if slot.execution_status == "cancelled" and not (slot.status_reason or "").strip()
        ]
        self._finding(
            items,
            "cancelled_slots_reasoned",
            "Ausgefallene Slots sind begründet",
            not cancelled_without_reason,
            cancelled_without_reason,
        )
        missing_times = [
            slot.id
            for slot in slots
            if slot.execution_status == "completed"
            and (slot.actual_started_at is None or slot.actual_completed_at is None)
        ]
        self._finding(
            items,
            "actual_times_complete",
            "Tatsächliche Beginn- und Endzeiten sind vollständig",
            not missing_times,
            missing_times,
        )
        missing_attendance = self._missing_candidate_attendance(session, slots)
        self._finding(
            items,
            "candidate_attendance_complete",
            "Anwesenheit der Prüflinge ist vollständig",
            not missing_attendance,
            missing_attendance,
        )

    @staticmethod
    def _missing_candidate_attendance(session: Session, slots: list[ExamSlot]) -> list[int]:
        missing: list[int] = []
        for slot in slots:
            if slot.execution_status != "completed":
                continue
            attendance = session.scalar(
                select(CandidateExamAttendance).where(
                    CandidateExamAttendance.exam_slot_id == slot.id
                )
            )
            if attendance is None or attendance.status not in {"present", "late"}:
                missing.append(slot.id)
        return missing

    def _evaluate_staffing(
        self, session: Session, day: ExamDay, slots: list[ExamSlot], items: list[dict[str, Any]]
    ) -> None:
        assignments = list(
            session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == day.id,
                    ExamDayAssignment.assignment_role == "examiner",
                )
            )
        )
        open_attendance, invalid_staffing = self._staffing_findings(
            session, day, slots, assignments
        )
        self._finding(
            items,
            "staff_attendance_complete",
            "Anwesenheit und tatsächliche Besetzung sind vollständig erfasst",
            not open_attendance,
            open_attendance,
        )
        self._finding(
            items,
            "staffing_rule_compliant",
            "Die tatsächliche Besetzung aller durchgeführten Slots ist regelkonform",
            not invalid_staffing,
            invalid_staffing,
        )

    def _staffing_findings(
        self,
        session: Session,
        day: ExamDay,
        slots: list[ExamSlot],
        assignments: list[ExamDayAssignment],
    ) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
        open_attendance: list[dict[str, int]] = []
        invalid_staffing: list[dict[str, Any]] = []
        for slot in (item for item in slots if item.execution_status == "completed"):
            present_members = self._present_members(
                session, day, slot, assignments, open_attendance
            )
            sides = {member.representing_side for member in present_members}
            if len(present_members) < 3 or sides != {"employer", "employee", "school"}:
                invalid_staffing.append(
                    {
                        "exam_slot_id": slot.id,
                        "present_member_ids": sorted(member.id for member in present_members),
                        "representing_sides": sorted(sides),
                    }
                )
        return open_attendance, invalid_staffing

    def _present_members(
        self,
        session: Session,
        day: ExamDay,
        slot: ExamSlot,
        assignments: list[ExamDayAssignment],
        open_attendance: list[dict[str, int]],
    ) -> list[CommitteeMember]:
        present_members: list[CommitteeMember] = []
        for assignment in assignments:
            if not self._assignment_applies_to_slot(assignment, slot):
                continue
            attendance = session.scalar(
                select(MemberExamAttendance).where(
                    MemberExamAttendance.exam_day_id == day.id,
                    MemberExamAttendance.committee_member_id == assignment.committee_member_id,
                )
            )
            if attendance is None or attendance.status not in {"present", "late"}:
                open_attendance.append(
                    {"exam_slot_id": slot.id, "committee_member_id": assignment.committee_member_id}
                )
                continue
            member = session.get(CommitteeMember, assignment.committee_member_id)
            if member is not None and member.is_active == 1:
                present_members.append(member)
        return present_members

    def _evaluate_absence_processes(
        self, session: Session, day: ExamDay, items: list[dict[str, Any]]
    ) -> None:
        open_absences = [
            item.id
            for item in session.scalars(
                select(AbsenceReport).where(AbsenceReport.exam_day_id == day.id)
            )
            if item.status not in TERMINAL_ABSENCE_STATUSES
        ]
        self._finding(
            items,
            "absence_processes_complete",
            "Ausfall- und Ersatzvorgänge sind abgeschlossen",
            not open_absences,
            open_absences,
        )

    def _evaluate_protocols(
        self,
        session: Session,
        slots: list[ExamSlot],
        items: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        regular_ready = True
        exception_ready = True
        candidates: list[dict[str, Any]] = []
        for slot in slots:
            regular, exception, candidate = self._evaluate_slot_protocol(
                session, slot, warnings, references
            )
            regular_ready &= regular
            exception_ready &= regular or exception
            if candidate is not None:
                candidates.append(candidate)
        self._finding(
            items,
            "protocols_complete",
            "Prüfungsprotokolle sind vollständig bestätigt oder mit Vorbehalt behandelt",
            regular_ready,
            [item for item in references if item["state"] not in COMPLETE_PROTOCOL_STATES],
        )
        return candidates if exception_ready else []

    def _evaluate_slot_protocol(
        self,
        session: Session,
        slot: ExamSlot,
        warnings: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> tuple[bool, bool, dict[str, Any] | None]:
        if slot.execution_status == "cancelled":
            return True, False, None
        protocol = session.scalar(select(ExamProtocol).where(ExamProtocol.exam_slot_id == slot.id))
        if protocol is None:
            references.append(
                {"exam_slot_id": slot.id, "exam_protocol_id": None, "state": "missing"}
            )
            return False, False, None
        revision = self._current_protocol_revision(session, protocol)
        participants = set(
            session.scalars(
                select(ExamProtocolParticipant.committee_member_id).where(
                    ExamProtocolParticipant.exam_protocol_id == protocol.id
                )
            )
        )
        responses = list(
            session.scalars(
                select(ExamProtocolResponse).where(
                    ExamProtocolResponse.exam_protocol_revision_id == revision.id
                )
            )
        )
        missing = sorted(participants - {item.committee_member_id for item in responses})
        state = self._protocol_state(revision, responses, missing)
        regular = state in COMPLETE_PROTOCOL_STATES and revision.workflow_state != "correction_open"
        candidate = self._exception_candidate(slot, protocol, revision, state, missing)
        self._append_protocol_warning(session, protocol, revision, responses, warnings)
        references.append(
            {
                "exam_slot_id": slot.id,
                "exam_protocol_id": protocol.id,
                "revision_id": revision.id,
                "version": revision.version,
                "state": state,
                "missing_response_member_ids": missing,
            }
        )
        return regular, candidate is not None, candidate

    @staticmethod
    def _protocol_state(
        revision: ExamProtocolRevision, responses: list[ExamProtocolResponse], missing: list[int]
    ) -> str:
        if revision.submitted_at is None:
            return (
                "correction_open" if revision.workflow_state == "correction_open" else "in_progress"
            )
        if not responses:
            return "awaiting_confirmation"
        if missing:
            return "reaction_missing"
        return (
            "fully_with_reservation"
            if any(item.response == "reservation" for item in responses)
            else "fully_confirmed"
        )

    @staticmethod
    def _exception_candidate(
        slot: ExamSlot,
        protocol: ExamProtocol,
        revision: ExamProtocolRevision,
        state: str,
        missing: list[int],
    ) -> dict[str, Any] | None:
        if (
            state != "reaction_missing"
            or len(missing) != 1
            or revision.declaration is None
            or revision.workflow_state == "correction_open"
        ):
            return None
        return {
            "exam_slot_id": slot.id,
            "exam_protocol_id": protocol.id,
            "exam_protocol_revision_id": revision.id,
            "protocol_version": revision.version,
            "committee_member_id": missing[0],
        }

    @staticmethod
    def _append_protocol_warning(
        session: Session,
        protocol: ExamProtocol,
        revision: ExamProtocolRevision,
        responses: list[ExamProtocolResponse],
        warnings: list[dict[str, Any]],
    ) -> None:
        entries = list(
            session.scalars(
                select(ExamProtocolEntry).where(
                    ExamProtocolEntry.exam_protocol_revision_id == revision.id
                )
            )
        )
        reservations = [
            {"committee_member_id": item.committee_member_id, "statement": item.statement}
            for item in responses
            if item.response == "reservation"
        ]
        if entries or reservations:
            warnings.append(
                {
                    "exam_protocol_id": protocol.id,
                    "entries": [
                        {"category": item.category, "statement": item.statement} for item in entries
                    ],
                    "reservations": reservations,
                }
            )

    def _evaluate_results(
        self,
        session: Session,
        slots: list[ExamSlot],
        items: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> None:
        for slot in slots:
            references.append(self._result_completion(session, slot))
        result_ready = all(item["regular_close_ready"] for item in references)
        self._finding(
            items,
            "results_complete",
            "Tagesbewertungen sind abgeschlossen und berechnungsbereite Ergebnisse festgestellt",
            result_ready,
            [item for item in references if not item["regular_close_ready"]],
        )

    def _result_completion(self, session: Session, slot: ExamSlot) -> dict[str, Any]:
        if slot.execution_status == "cancelled":
            return self._no_result_completion(slot, "not_required", True)
        result = session.scalar(
            select(ExamResult).where(ExamResult.round_candidate_id == slot.round_candidate_id)
        )
        if result is None:
            return self._no_result_completion(slot, "missing", False)
        if result.legacy_status is not None:
            return self._legacy_result_completion(slot, result)
        binding = self._assessment_binding(session, result)
        if binding is None:
            return self._missing_model_completion(slot, result)
        model = session.get(AssessmentModelVersion, binding.assessment_model_version_id)
        rules = json.loads(model.rules_json)
        participant_ids = self._result_participant_ids(session, result)
        incomplete_components = self._incomplete_day_components(
            session, result, rules["components"], participant_ids
        )
        pending_external = self._pending_external_areas(session, result, rules["external_areas"])
        determination, confirmations_complete = self._result_determination_state(session, result)
        calculation_ready_unfixed = self._unfixed_calculation_ready(
            result, incomplete_components, pending_external, determination
        )
        ready = self._result_is_ready(
            result, incomplete_components, calculation_ready_unfixed, confirmations_complete
        )
        return {
            "exam_slot_id": slot.id,
            "exam_result_id": result.id,
            "version": result.version,
            "state": result.current_state,
            "correction_open": bool(result.correction_open),
            "incomplete_day_components": incomplete_components,
            "external_inputs_pending": pending_external,
            "external_follow_up_open": bool(pending_external),
            "determination_id": determination.id if determination else None,
            "record_confirmations_complete": confirmations_complete,
            "regular_close_ready": ready,
        }

    @staticmethod
    def _no_result_completion(slot: ExamSlot, state: str, ready: bool) -> dict[str, Any]:
        return {
            "exam_slot_id": slot.id,
            "exam_result_id": None,
            "state": state,
            "regular_close_ready": ready,
            "external_inputs_pending": [],
        }

    @staticmethod
    def _legacy_result_completion(slot: ExamSlot, result: ExamResult) -> dict[str, Any]:
        return {
            "exam_slot_id": slot.id,
            "exam_result_id": result.id,
            "version": result.version,
            "state": result.legacy_status,
            "regular_close_ready": True,
            "external_inputs_pending": [],
        }

    @staticmethod
    def _missing_model_completion(slot: ExamSlot, result: ExamResult) -> dict[str, Any]:
        return {
            "exam_slot_id": slot.id,
            "exam_result_id": result.id,
            "version": result.version,
            "state": "model_missing",
            "regular_close_ready": False,
            "external_inputs_pending": [],
        }

    @staticmethod
    def _assessment_binding(
        session: Session, result: ExamResult
    ) -> ExamRoundAssessmentBinding | None:
        round_candidate = session.get(RoundCandidate, result.round_candidate_id)
        return session.scalar(
            select(ExamRoundAssessmentBinding).where(
                ExamRoundAssessmentBinding.exam_round_id == round_candidate.exam_round_id
            )
        )

    @staticmethod
    def _result_participant_ids(session: Session, result: ExamResult) -> set[int]:
        return set(
            session.scalars(
                select(ExamProtocolParticipant.committee_member_id)
                .join(ExamProtocol, ExamProtocol.id == ExamProtocolParticipant.exam_protocol_id)
                .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                .where(ExamSlot.round_candidate_id == result.round_candidate_id)
            )
        )

    def _incomplete_day_components(
        self,
        session: Session,
        result: ExamResult,
        components: list[dict[str, Any]],
        participant_ids: set[int],
    ) -> list[str]:
        incomplete: list[str] = []
        for component in components:
            if component.get("day_scoped", False) and not self._component_complete(
                session, result, component, participant_ids
            ):
                incomplete.append(component["key"])
        return incomplete

    @staticmethod
    def _component_complete(
        session: Session,
        result: ExamResult,
        component: dict[str, Any],
        participant_ids: set[int],
    ) -> bool:
        if component["mode"] == "committee":
            return (
                session.scalar(
                    select(CommitteeAssessment.id).where(
                        CommitteeAssessment.exam_result_id == result.id,
                        CommitteeAssessment.component_key == component["key"],
                        CommitteeAssessment.status == "current",
                    )
                )
                is not None
            )
        criteria = {item["key"] for item in component["criteria"]}
        by_member: dict[int, set[str]] = {}
        for item in session.scalars(
            select(IndividualAssessment).where(
                IndividualAssessment.exam_result_id == result.id,
                IndividualAssessment.component_key == component["key"],
                IndividualAssessment.status == "submitted",
            )
        ):
            if item.assessor_member_id in participant_ids:
                by_member.setdefault(item.assessor_member_id, set()).add(item.criterion_key)
        return sum(1 for submitted in by_member.values() if submitted == criteria) >= int(
            component["required_assessors"]
        )

    @staticmethod
    def _pending_external_areas(
        session: Session, result: ExamResult, external_areas: list[dict[str, Any]]
    ) -> list[str]:
        pending: list[str] = []
        for area in external_areas:
            if not area["required"]:
                continue
            external = session.scalar(
                select(ExternalExamResult)
                .where(
                    ExternalExamResult.exam_result_id == result.id,
                    ExternalExamResult.area_key == area["key"],
                    ExternalExamResult.status.in_({"unconfirmed", "confirmed"}),
                )
                .order_by(ExternalExamResult.revision.desc())
            )
            if external is None or external.status != "confirmed":
                pending.append(area["key"])
        return pending

    @staticmethod
    def _result_determination_state(
        session: Session, result: ExamResult
    ) -> tuple[ResultDetermination | None, bool]:
        determination = session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == result.id,
                ResultDetermination.status == "current",
            )
        )
        if determination is None:
            return None, True
        expected = set(json.loads(determination.participant_member_ids_json))
        actual = set(
            session.scalars(
                select(ResultRecordConfirmation.committee_member_id).where(
                    ResultRecordConfirmation.result_determination_id == determination.id
                )
            )
        )
        return determination, expected == actual

    @staticmethod
    def _unfixed_calculation_ready(
        result: ExamResult,
        incomplete_components: list[str],
        pending_external: list[str],
        determination: ResultDetermination | None,
    ) -> bool:
        return result.current_state == "calculation_ready" or (
            not incomplete_components
            and not pending_external
            and determination is None
            and result.current_state != "incomplete"
        )

    @staticmethod
    def _result_is_ready(
        result: ExamResult,
        incomplete_components: list[str],
        calculation_ready_unfixed: bool,
        confirmations_complete: bool,
    ) -> bool:
        return (
            not incomplete_components
            and not calculation_ready_unfixed
            and confirmations_complete
            and not bool(result.correction_open)
        )

    def _impact(self, session: Session, day: ExamDay, raw_scope: Any) -> dict[str, Any]:
        requested = self._normalize_scope(raw_scope)
        slots, assignments, absences, protocols, results = self._reopening_entities(session, day)
        self._validate_reopening_scope(requested, slots, assignments, absences, protocols, results)
        impacted_protocol_ids, impacted_result_ids = self._impacted_entity_ids(
            requested, slots, protocols, results
        )
        impacts = self._impact_details(
            session, protocols, impacted_protocol_ids, impacted_result_ids
        )
        expanded = set(requested)
        expanded.update(_token("exam_protocol", item) for item in impacted_protocol_ids)
        expanded.update(_token("exam_result", item) for item in impacted_result_ids)
        return {
            "exam_day_id": day.id,
            "revision": day.revision,
            "requested_scope": requested,
            "expanded_scope": sorted(expanded),
            "impacts": impacts,
        }

    @staticmethod
    def _reopening_entities(session: Session, day: ExamDay) -> tuple[
        dict[int, ExamSlot],
        dict[int, ExamDayAssignment],
        dict[int, AbsenceReport],
        dict[int, ExamProtocol],
        dict[int, ExamResult],
    ]:
        slots = {
            item.id: item
            for item in session.scalars(select(ExamSlot).where(ExamSlot.exam_day_id == day.id))
        }
        assignments = {
            item.id: item
            for item in session.scalars(
                select(ExamDayAssignment).where(ExamDayAssignment.exam_day_id == day.id)
            )
        }
        absences = {
            item.id: item
            for item in session.scalars(
                select(AbsenceReport).where(AbsenceReport.exam_day_id == day.id)
            )
        }
        protocols = {
            item.id: item
            for item in session.scalars(
                select(ExamProtocol)
                .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                .where(ExamSlot.exam_day_id == day.id)
            )
        }
        results = {
            item.id: item
            for item in session.scalars(
                select(ExamResult)
                .join(ExamSlot, ExamSlot.round_candidate_id == ExamResult.round_candidate_id)
                .where(ExamSlot.exam_day_id == day.id)
            ).unique()
        }
        return slots, assignments, absences, protocols, results

    @staticmethod
    def _validate_reopening_scope(
        requested: list[str],
        slots: dict[int, ExamSlot],
        assignments: dict[int, ExamDayAssignment],
        absences: dict[int, AbsenceReport],
        protocols: dict[int, ExamProtocol],
        results: dict[int, ExamResult],
    ) -> None:
        for token in requested:
            kind, raw_id = token.split(":", 1)
            entity_id = int(raw_id)
            valid = (
                (kind in {"slot_status", "candidate_attendance"} and entity_id in slots)
                or (kind in {"member_attendance", "staffing"} and entity_id in assignments)
                or (kind == "absence" and entity_id in absences)
                or (kind == "exam_protocol" and entity_id in protocols)
                or (kind == "exam_result" and entity_id in results)
            )
            if not valid:
                raise ValueError("Der Korrekturumfang gehört nicht zum ausgewählten Prüfungstag")

    @staticmethod
    def _impacted_entity_ids(
        requested: list[str],
        slots: dict[int, ExamSlot],
        protocols: dict[int, ExamProtocol],
        results: dict[int, ExamResult],
    ) -> tuple[set[int], set[int]]:
        impacted_protocol_ids: set[int] = set()
        impacted_result_ids: set[int] = set()
        broad = any(
            token.split(":", 1)[0] in {"member_attendance", "staffing", "absence"}
            for token in requested
        )
        if broad:
            impacted_protocol_ids.update(protocols)
            impacted_result_ids.update(results)
        for token in requested:
            kind, raw_id = token.split(":", 1)
            entity_id = int(raw_id)
            if kind in {"slot_status", "candidate_attendance"}:
                slot = slots[entity_id]
                impacted_protocol_ids.update(
                    protocol.id
                    for protocol in protocols.values()
                    if protocol.exam_slot_id == slot.id
                )
                impacted_result_ids.update(
                    result.id
                    for result in results.values()
                    if result.round_candidate_id == slot.round_candidate_id
                )
            elif kind == "exam_protocol":
                impacted_protocol_ids.add(entity_id)
                slot = slots[protocols[entity_id].exam_slot_id]
                impacted_result_ids.update(
                    result.id
                    for result in results.values()
                    if result.round_candidate_id == slot.round_candidate_id
                )
            elif kind == "exam_result":
                impacted_result_ids.add(entity_id)
        return impacted_protocol_ids, impacted_result_ids

    def _impact_details(
        self,
        session: Session,
        protocols: dict[int, ExamProtocol],
        impacted_protocol_ids: set[int],
        impacted_result_ids: set[int],
    ) -> dict[str, list[int]]:
        recipient_ids: set[int] = set()
        invalidated_response_ids: list[int] = []
        for protocol_id in impacted_protocol_ids:
            protocol = protocols[protocol_id]
            revision = self._current_protocol_revision(session, protocol)
            responses = list(
                session.scalars(
                    select(ExamProtocolResponse).where(
                        ExamProtocolResponse.exam_protocol_revision_id == revision.id
                    )
                )
            )
            invalidated_response_ids.extend(item.id for item in responses)
            recipient_ids.update(item.committee_member_id for item in responses)
            recipient_ids.update(
                session.scalars(
                    select(ExamProtocolParticipant.committee_member_id).where(
                        ExamProtocolParticipant.exam_protocol_id == protocol.id
                    )
                )
            )
        result_impacts = self._result_impact_details(session, impacted_result_ids, recipient_ids)
        return {
            "exam_protocol_ids": sorted(impacted_protocol_ids),
            "invalidated_protocol_response_ids": sorted(invalidated_response_ids),
            "exam_result_ids": sorted(impacted_result_ids),
            **result_impacts,
            "recipient_member_ids": sorted(recipient_ids),
        }

    @staticmethod
    def _result_impact_details(
        session: Session, impacted_result_ids: set[int], recipient_ids: set[int]
    ) -> dict[str, list[int]]:
        determination_ids: list[int] = []
        communicated_result_ids: list[int] = []
        ihk_processed_result_ids: list[int] = []
        for result_id in impacted_result_ids:
            determination = session.scalar(
                select(ResultDetermination).where(
                    ResultDetermination.exam_result_id == result_id,
                    ResultDetermination.status == "current",
                )
            )
            if determination is None:
                continue
            determination_ids.append(determination.id)
            recipient_ids.update(json.loads(determination.participant_member_ids_json))
            communications = list(
                session.scalars(
                    select(ResultCommunication).where(
                        ResultCommunication.exam_result_id == result_id,
                        ResultCommunication.status == "current",
                    )
                )
            )
            if communications:
                communicated_result_ids.append(result_id)
            if any(item.external_document_status for item in communications):
                ihk_processed_result_ids.append(result_id)
        return {
            "affected_result_determination_ids": sorted(determination_ids),
            "communicated_result_ids": sorted(communicated_result_ids),
            "ihk_processed_result_ids": sorted(ihk_processed_result_ids),
        }

    def _open_dependent_corrections(
        self,
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening,
        impact: dict[str, Any],
        actor_id: int,
        reason: str,
        now: str,
    ) -> None:
        for protocol_id in impact["impacts"]["exam_protocol_ids"]:
            self._open_protocol_correction(
                session, day, reopening, protocol_id, actor_id, reason, now
            )

        for result_id in impact["impacts"]["exam_result_ids"]:
            self._open_result_correction(session, day, reopening, result_id, actor_id, reason, now)

    def _open_protocol_correction(
        self,
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening,
        protocol_id: int,
        actor_id: int,
        reason: str,
        now: str,
    ) -> None:
        protocol = session.get(ExamProtocol, protocol_id)
        current = self._current_protocol_revision(session, protocol)
        request = ExamProtocolCorrectionRequest(
            exam_protocol_id=protocol.id,
            exam_protocol_revision_id=current.id,
            requested_by_member_id=actor_id,
            reason=reason,
            status="opened",
            requested_at=now,
            opened_by_member_id=actor_id,
            opened_at=now,
            reopening_reference=f"exam-day-reopening:{reopening.id}",
        )
        session.add(request)
        session.flush()
        revision = ExamProtocolRevision(
            exam_protocol_id=protocol.id,
            version=current.version + 1,
            declaration=current.declaration,
            workflow_state="correction_open",
            previous_revision_id=current.id,
            correction_request_id=request.id,
            changed_by_member_id=actor_id,
            change_reason=reason,
            created_at=now,
        )
        session.add(revision)
        session.flush()
        self._copy_protocol_entries(session, current, revision)
        protocol.current_version = revision.version
        protocol.updated_at = now
        participants = set(
            session.scalars(
                select(ExamProtocolParticipant.committee_member_id).where(
                    ExamProtocolParticipant.exam_protocol_id == protocol.id
                )
            )
        )
        self._add_reopening_tasks(
            session,
            day,
            reopening,
            participants,
            "protocol_reconfirmation",
            f"exam-day-reopening:{reopening.id}:protocol:{protocol.id}",
            reason,
            now,
            exam_protocol_revision_id=revision.id,
        )

    @staticmethod
    def _copy_protocol_entries(
        session: Session, current: ExamProtocolRevision, revision: ExamProtocolRevision
    ) -> None:
        for entry in session.scalars(
            select(ExamProtocolEntry).where(
                ExamProtocolEntry.exam_protocol_revision_id == current.id
            )
        ):
            session.add(
                ExamProtocolEntry(
                    exam_protocol_revision_id=revision.id,
                    category=entry.category,
                    statement=entry.statement,
                    occurred_from=entry.occurred_from,
                    occurred_to=entry.occurred_to,
                    recorded_by_member_id=entry.recorded_by_member_id,
                    created_at=entry.created_at,
                )
            )

    def _open_result_correction(
        self,
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening,
        result_id: int,
        actor_id: int,
        reason: str,
        now: str,
    ) -> None:
        result = session.get(ExamResult, result_id)
        determination = session.scalar(
            select(ResultDetermination).where(
                ResultDetermination.exam_result_id == result.id,
                ResultDetermination.status == "current",
            )
        )
        if determination is None:
            return
        self._ensure_result_correction(
            session, result, determination, reopening, actor_id, reason, now
        )
        result.correction_open = 1
        result.version += 1
        result.updated_at = now
        participants = set(json.loads(determination.participant_member_ids_json))
        self._add_reopening_tasks(
            session,
            day,
            reopening,
            participants,
            "result_reconfirmation",
            f"exam-day-reopening:{reopening.id}:result:{result.id}",
            reason,
            now,
            result_determination_id=determination.id,
        )
        self._add_result_follow_up_tasks(
            session, day, reopening, result, determination, reason, now
        )

    @staticmethod
    def _ensure_result_correction(
        session: Session,
        result: ExamResult,
        determination: ResultDetermination,
        reopening: ExamDayReopening,
        actor_id: int,
        reason: str,
        now: str,
    ) -> None:
        existing = session.scalar(
            select(ResultCorrection).where(
                ResultCorrection.exam_result_id == result.id,
                ResultCorrection.status == "open",
            )
        )
        if existing is None:
            session.add(
                ResultCorrection(
                    exam_result_id=result.id,
                    result_determination_id=determination.id,
                    reason=reason,
                    requested_by_member_id=actor_id,
                    status="open",
                    reopening_reference=f"exam-day-reopening:{reopening.id}",
                    requested_at=now,
                )
            )

    def _add_result_follow_up_tasks(
        self,
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening,
        result: ExamResult,
        determination: ResultDetermination,
        reason: str,
        now: str,
    ) -> None:
        communications = list(
            session.scalars(
                select(ResultCommunication).where(
                    ResultCommunication.exam_result_id == result.id,
                    ResultCommunication.status == "current",
                )
            )
        )
        chairs = self._management_member_ids(session, day)
        if communications:
            self._add_reopening_tasks(
                session,
                day,
                reopening,
                chairs,
                "result_recommunication",
                f"exam-day-reopening:{reopening.id}:recommunicate:{result.id}",
                reason,
                now,
                result_determination_id=determination.id,
            )
        if any(item.external_document_status for item in communications):
            self._add_reopening_tasks(
                session,
                day,
                reopening,
                chairs,
                "ihk_clarification",
                f"exam-day-reopening:{reopening.id}:ihk:{result.id}",
                reason,
                now,
                result_determination_id=determination.id,
            )

    @staticmethod
    def _add_reopening_tasks(
        session: Session,
        day: ExamDay,
        reopening: ExamDayReopening,
        recipient_ids: set[int],
        task_type: str,
        origin_key: str,
        reason: str,
        now: str,
        *,
        exam_protocol_revision_id: int | None = None,
        result_determination_id: int | None = None,
    ) -> None:
        for member_id in recipient_ids:
            session.add(
                ExamDayTask(
                    exam_day_id=day.id,
                    reopening_id=reopening.id,
                    recipient_member_id=member_id,
                    task_type=task_type,
                    origin_key=origin_key,
                    exam_protocol_revision_id=exam_protocol_revision_id,
                    result_determination_id=result_determination_id,
                    details_json=_json({"reason": reason}),
                    status="open",
                    created_at=now,
                )
            )

    def _notify(
        self,
        committee_id: int,
        round_id: int,
        day_id: int,
        jobs: list[NotificationJob],
    ) -> None:
        for job in jobs:
            try:
                self.notification_service.create_direct(
                    committee_id=committee_id,
                    round_id=round_id,
                    recipient_member_ids=job.recipient_member_ids,
                    event_type=job.event_type,
                    title=job.title,
                    message=job.message,
                    action_path=f"/confirmed-plan-days/{day_id}",
                    origin_key=job.origin_key,
                )
            except Exception:
                # The durable task and domain decision remain committed; delivery problems
                # are deliberately handled by the notification contract.
                continue

    @staticmethod
    def _finding(
        items: list[dict[str, Any]],
        code: str,
        label: str,
        ok: bool,
        details: Any | None = None,
    ) -> None:
        items.append({"code": code, "label": label, "ok": ok, "details": details or []})

    @staticmethod
    def _assignment_applies_to_slot(assignment: ExamDayAssignment, slot: ExamSlot) -> bool:
        if assignment.day_part == "full_day":
            return True
        try:
            start = datetime.fromisoformat(slot.starts_at.replace(" ", "T"))
        except TypeError, ValueError:
            return True
        return (assignment.day_part == "morning" and start.hour < 12) or (
            assignment.day_part == "afternoon" and start.hour >= 12
        )

    @staticmethod
    def _current_protocol_revision(
        session: Session, protocol: ExamProtocol
    ) -> ExamProtocolRevision:
        revision = session.scalar(
            select(ExamProtocolRevision).where(
                ExamProtocolRevision.exam_protocol_id == protocol.id,
                ExamProtocolRevision.version == protocol.current_version,
            )
        )
        if revision is None:
            raise ValueError("Der aktuelle Protokollstand fehlt")
        return revision

    @staticmethod
    def _required_day(session: Session, day_id: int) -> ExamDay:
        day = session.get(ExamDay, day_id)
        if day is None:
            raise ValueError("Prüfungstag nicht gefunden")
        return day

    @staticmethod
    def _required_revision(payload: dict[str, Any]) -> int:
        value = payload.get("revision")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError("Eine aktuelle Tagesrevision ist erforderlich")
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

    def _require_access(
        self, session: Session, day: ExamDay, scope: AuthorizationScope
    ) -> tuple[int | None, int, int]:
        exam_round = session.get(ExamRound, day.exam_round_id)
        if exam_round is None or not scope.can_read_committee(exam_round.committee_id):
            raise PermissionError("Forbidden.")
        return (
            scope.member_for_committee(exam_round.committee_id),
            exam_round.committee_id,
            exam_round.id,
        )

    def _require_management(
        self, session: Session, day: ExamDay, scope: AuthorizationScope
    ) -> tuple[int, int, int]:
        actor_id, committee_id, round_id = self._require_access(session, day, scope)
        if actor_id is None or not scope.can_manage_committee(committee_id):
            raise PermissionError("Forbidden.")
        return actor_id, committee_id, round_id

    @staticmethod
    def _active_reopening(session: Session, day_id: int) -> ExamDayReopening | None:
        return session.scalar(
            select(ExamDayReopening).where(
                ExamDayReopening.exam_day_id == day_id,
                ExamDayReopening.status == "open",
            )
        )

    @staticmethod
    def _current_or_latest_closure(session: Session, day_id: int) -> ExamDayClosure | None:
        return session.scalar(
            select(ExamDayClosure)
            .where(ExamDayClosure.exam_day_id == day_id)
            .order_by(
                (ExamDayClosure.status == "current").desc(),
                ExamDayClosure.id.desc(),
            )
        )

    @staticmethod
    def _management_member_ids(session: Session, day: ExamDay) -> set[int]:
        exam_round = session.get(ExamRound, day.exam_round_id)
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
    def _affected_recipient_ids(session: Session, reopening: ExamDayReopening) -> set[int]:
        return set(json.loads(reopening.impacts_json).get("recipient_member_ids", []))
