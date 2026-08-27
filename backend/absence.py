"""Transactional absence and replacement workflow for confirmed exam plans."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .authorization import AuthorizationScope
from .calendar import CalendarService
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    AbsenceAuditEvent,
    AbsenceReport,
    CandidateExamDay,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    ReplacementResponse,
)
from .notifications import NotificationService

ACTIVE_STATUSES = {
    "reported",
    "fallback_requested",
    "fallback_confirmed",
    "fallback_expired",
    "replacement_requested",
}
TERMINAL_STATUSES = {"replacement_selected", "resolved", "withdrawn", "exam_day_cancelled"}
RESPONSE_VALUES = {"pending", "available", "unavailable"}
SIDES = {"employer", "employee", "school"}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _stamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    return _now(datetime.fromisoformat(value.replace("Z", "+00:00")))


class AbsenceService:
    """Own all state transitions that can replace a confirmed assignment."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        notification_service: NotificationService | None = None,
        calendar_service: CalendarService | None = None,
    ) -> None:
        self.db_path = db_path
        self.notification_service = notification_service or NotificationService(db_path)
        self.calendar_service = calendar_service or CalendarService(db_path)

    def list(self, scope: AuthorizationScope) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            reports = session.scalars(
                select(AbsenceReport)
                .join(ExamDay, ExamDay.id == AbsenceReport.exam_day_id)
                .join(ExamRound, ExamRound.id == ExamDay.exam_round_id)
                .where(ExamRound.committee_id.in_(scope.committee_ids))
                .order_by(AbsenceReport.reported_at.desc(), AbsenceReport.id.desc())
            ).all()
            return [self._view(session, report) for report in reports]

    def get(self, scope: AuthorizationScope, report_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            report = session.get(AbsenceReport, report_id)
            if report is None or not self._visible(session, report, scope):
                return None
            return self._view(session, report)

    def report(
        self,
        scope: AuthorizationScope,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        notification_data: tuple[int, int, set[int], str, bool] | None = None
        with session_scope(self.db_path) as session:
            day, exam_round, assignment, target = self._target(session, payload)
            actor_id = scope.member_for_committee(exam_round.committee_id)
            if actor_id is None:
                raise ValueError("Akteur gehört nicht zum Prüfungsausschuss")
            if not scope.can_manage_committee(exam_round.committee_id) and actor_id != target.id:
                raise PermissionError(
                    "Ein Ausfall darf nur für das eigene Mitglied gemeldet werden"
                )
            self._assert_before_start(session, day, assignment, current)
            if exam_round.status != "plan_confirmed" or day.status != "confirmed":
                raise ValueError(
                    "Ausfälle können nur in einem bestätigten Prüfungsplan gemeldet werden"
                )
            if session.scalars(
                select(AbsenceReport).where(
                    AbsenceReport.exam_day_assignment_id == assignment.id,
                    AbsenceReport.status.in_(ACTIVE_STATUSES | TERMINAL_STATUSES),
                )
            ).first():
                raise ValueError("Für diese Besetzung existiert bereits eine Ausfallmeldung")

            urgent = current + timedelta(hours=48) > self._assignment_start(
                session, day, assignment
            )
            report = AbsenceReport(
                exam_day_id=day.id,
                exam_day_assignment_id=assignment.id,
                committee_member_id=target.id,
                reported_by_member_id=actor_id,
                reported_at=_stamp(current),
                reason=self._optional_reason(payload.get("reason")),
                status="reported",
                version=0,
            )
            session.add(report)
            session.flush()
            eligible, fallback = self._eligible_candidates(
                session, day, assignment, target, urgent=urgent
            )
            selected_ids: set[int] = set()
            expires_at: str | None = None
            if assignment.assignment_role == "examiner" and fallback is not None and not urgent:
                selected_ids.add(fallback.id)
                expires_at = _stamp(current + timedelta(hours=24))
                report.status = "fallback_requested"
            else:
                selected_ids.update(member.id for member in eligible)
                if urgent and fallback is not None:
                    selected_ids.add(fallback.id)
                report.status = (
                    "replacement_requested" if selected_ids else "no_replacement_available"
                )
            for member_id in sorted(selected_ids):
                session.add(
                    ReplacementResponse(
                        absence_report_id=report.id,
                        committee_member_id=member_id,
                        response="pending",
                        requested_at=_stamp(current),
                        expires_at=expires_at if fallback and member_id == fallback.id else None,
                        urgent=int(urgent),
                    )
                )
            self._audit(session, report, actor_id, "reported", None, report.status, current)
            session.flush()
            notify_ids = {actor_id, target.id} | {
                member.id
                for member in session.scalars(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == exam_round.committee_id,
                        CommitteeMember.committee_role.in_({"chair", "deputy_chair"}),
                        CommitteeMember.is_active == 1,
                    )
                ).all()
            }
            notify_ids.update(selected_ids)
            notification_data = (
                exam_round.committee_id,
                exam_round.id,
                notify_ids,
                "urgent_replacement_requested" if urgent else "examiner_absence_reported",
                urgent,
            )
            result = self._view(session, report)
        self._notify(
            notification_data,
            title="Ausfallmeldung und Ersatzsuche",
            message="Für einen bestätigten Prüfungstag wurde eine Ausfallmeldung erfasst.",
            report_id=result["id"],
        )
        return result

    def respond(
        self,
        scope: AuthorizationScope,
        response_id: int,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        notification_data = None
        with session_scope(self.db_path) as session:
            response = session.get(ReplacementResponse, response_id)
            if response is None or response.committee_member_id not in scope.member_ids:
                raise PermissionError("Ersatzanfrage ist nicht zugänglich")
            report = session.get(AbsenceReport, response.absence_report_id)
            if report is None or not self._visible(session, report, scope):
                raise PermissionError("Ersatzanfrage ist nicht zugänglich")
            answer = payload.get("response")
            if answer not in {"available", "unavailable"}:
                raise ValueError("Antwort muss available oder unavailable sein")
            if response.response != "pending":
                raise ValueError("Diese Ersatzanfrage wurde bereits beantwortet")
            expired = bool(response.expires_at and _parse(response.expires_at) <= current)
            if expired:
                answer = "unavailable"
            old_status = report.status
            response.response = answer
            response.responded_at = _stamp(current)
            if answer == "available" and report.status == "fallback_requested":
                report.status = "fallback_confirmed"
            elif answer == "unavailable" and report.status == "fallback_requested":
                if expired:
                    report.status = "fallback_expired"
                    self._audit(
                        session,
                        report,
                        response.committee_member_id,
                        "fallback_expired",
                        old_status,
                        report.status,
                        current,
                    )
                self._open_further_search(session, report, current)
            report.version += 1
            report.updated_at = _stamp(current)
            self._audit(
                session,
                report,
                response.committee_member_id,
                "response",
                old_status,
                report.status,
                current,
            )
            day = session.get(ExamDay, report.exam_day_id)
            round_row = session.get(ExamRound, day.exam_round_id) if day else None
            if round_row:
                recipient_ids = {
                    member.id
                    for member in session.scalars(
                        select(CommitteeMember).where(
                            CommitteeMember.committee_id == round_row.committee_id,
                            CommitteeMember.committee_role.in_({"chair", "deputy_chair"}),
                            CommitteeMember.is_active == 1,
                        )
                    ).all()
                }
                recipient_ids.update(
                    row.committee_member_id
                    for row in session.scalars(
                        select(ReplacementResponse).where(
                            ReplacementResponse.absence_report_id == report.id
                        )
                    ).all()
                )
                notification_data = (
                    round_row.committee_id,
                    round_row.id,
                    recipient_ids,
                    (
                        "fallback_confirmation_expired"
                        if expired
                        else (
                            "replacement_requested"
                            if report.status == "replacement_requested"
                            else "fallback_confirmation_requested"
                        )
                    ),
                    False,
                )
            result = self._view(session, report)
        self._notify(
            notification_data,
            title="Antwort zur Ersatzanfrage",
            message="Eine Ersatzanfrage wurde beantwortet und der Ausfallprozess aktualisiert.",
            report_id=result["id"],
        )
        return result

    def select_replacement(
        self,
        scope: AuthorizationScope,
        report_id: int,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        notification_data = None
        calendar_round_id: int | None = None
        report_round_id = self._report_round_id(report_id)
        if report_round_id is not None:
            self.calendar_service.sync_round(report_round_id)
        with session_scope(self.db_path) as session:
            report = session.get(AbsenceReport, report_id)
            if report is None:
                raise ValueError("Ausfallmeldung nicht gefunden")
            day = session.get(ExamDay, report.exam_day_id)
            round_row = session.get(ExamRound, day.exam_round_id) if day else None
            if (
                day is None
                or round_row is None
                or not scope.can_manage_committee(round_row.committee_id)
            ):
                raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen Ersatz auswählen")
            self._assert_before_start(
                session, day, session.get(ExamDayAssignment, report.exam_day_assignment_id), current
            )
            if report.status not in {
                "fallback_confirmed",
                "replacement_requested",
                "fallback_expired",
            }:
                raise ValueError("Die Ausfallmeldung ist nicht auswählbar")
            self._check_version(report, payload)
            member_id = self._required_int(payload, "committee_member_id")
            response = session.scalars(
                select(ReplacementResponse).where(
                    ReplacementResponse.absence_report_id == report.id,
                    ReplacementResponse.committee_member_id == member_id,
                    ReplacementResponse.response == "available",
                )
            ).first()
            if response is None:
                raise ValueError("Nur ein verfügbares angefragtes Mitglied kann ausgewählt werden")
            assignment = session.get(ExamDayAssignment, report.exam_day_assignment_id)
            target = session.get(CommitteeMember, report.committee_member_id)
            replacement = session.get(CommitteeMember, member_id)
            if assignment is None or target is None or replacement is None:
                raise ValueError("Besetzung oder Mitglied nicht gefunden")
            eligible, fallback = self._eligible_candidates(
                session, day, assignment, target, urgent=True, include_member=member_id
            )
            if replacement.id not in {member.id for member in eligible} and replacement.id != (
                fallback.id if fallback else None
            ):
                raise ValueError("Das gewählte Mitglied ist nicht mehr geeignet oder verfügbar")
            old_status = report.status
            old_member_id = assignment.committee_member_id
            assignment.committee_member_id = replacement.id
            if assignment.assignment_role == "fallback":
                assignment.fallback_status = "confirmed"
            report.selected_replacement_member_id = replacement.id
            report.status = "replacement_selected"
            report.version += 1
            report.updated_at = _stamp(current)
            self._audit(
                session,
                report,
                scope.member_for_committee(round_row.committee_id) or replacement.id,
                "replacement_selected",
                old_status,
                report.status,
                current,
                {"member_id": replacement.id},
            )
            session.flush()
            notify_ids = {old_member_id, replacement.id} | {
                member.id
                for member in session.scalars(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == round_row.committee_id,
                        CommitteeMember.is_active == 1,
                        CommitteeMember.id != replacement.id,
                    )
                ).all()
            }
            notification_data = (
                round_row.committee_id,
                round_row.id,
                notify_ids,
                "replacement_selected",
                False,
            )
            calendar_round_id = round_row.id
            result = self._view(session, report)
        if calendar_round_id is not None:
            self.calendar_service.sync_round(calendar_round_id)
        self._notify(
            notification_data,
            title="Ersatzmitglied ausgewählt",
            message="Die Ersatzbesetzung wurde kontrolliert ausgewählt.",
            report_id=result["id"],
        )
        return result

    def withdraw(
        self,
        scope: AuthorizationScope,
        report_id: int,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        with session_scope(self.db_path) as session:
            report, day, round_row = self._authorized_report(session, scope, report_id)
            actor_id = scope.member_for_committee(round_row.committee_id)
            if actor_id != report.committee_member_id and not scope.can_manage_committee(
                round_row.committee_id
            ):
                raise PermissionError("Nur die meldende Person oder die Leitung darf zurücknehmen")
            if report.selected_replacement_member_id is not None:
                raise ValueError("Nach einer Ersatzwahl ist eine Rücknahme nicht mehr möglich")
            self._assert_before_start(
                session, day, session.get(ExamDayAssignment, report.exam_day_assignment_id), current
            )
            old_status = report.status
            report.status = "withdrawn"
            report.version += 1
            report.updated_at = _stamp(current)
            self._audit(
                session,
                report,
                actor_id or report.committee_member_id,
                "withdrawn",
                old_status,
                report.status,
                current,
            )
            return self._view(session, report)

    def reopen(
        self,
        scope: AuthorizationScope,
        report_id: int,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        reason = self._required_reason(payload)
        calendar_round_id: int | None = None
        report_round_id = self._report_round_id(report_id)
        if report_round_id is not None:
            self.calendar_service.sync_round(report_round_id)
        with session_scope(self.db_path) as session:
            report, day, round_row = self._authorized_report(session, scope, report_id)
            actor_id = scope.member_for_committee(round_row.committee_id)
            if not scope.can_manage_committee(round_row.committee_id):
                raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen wieder öffnen")
            self._assert_before_start(
                session, day, session.get(ExamDayAssignment, report.exam_day_assignment_id), current
            )
            if report.status not in {"replacement_selected", "resolved", "exam_day_cancelled"}:
                raise ValueError("Die Ausfallmeldung ist nicht wieder zu öffnen")
            assignment = session.get(ExamDayAssignment, report.exam_day_assignment_id)
            if assignment is None:
                raise ValueError("Besetzung nicht gefunden")
            selected_id = report.selected_replacement_member_id
            if selected_id is not None:
                assignment.committee_member_id = report.committee_member_id
            old_status = report.status
            report.selected_replacement_member_id = None
            report.status = "replacement_requested"
            report.version += 1
            report.updated_at = _stamp(current)
            self._audit(
                session,
                report,
                actor_id or report.committee_member_id,
                "reopened",
                old_status,
                report.status,
                current,
                {"reason": reason},
            )
            calendar_round_id = round_row.id
            result = self._view(session, report)
        if calendar_round_id is not None:
            self.calendar_service.sync_round(calendar_round_id)
        return result

    def cancel(
        self,
        scope: AuthorizationScope,
        report_id: int,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        reason = self._required_reason(payload)
        calendar_target: tuple[int, int] | None = None
        with session_scope(self.db_path) as session:
            report, day, round_row = self._authorized_report(session, scope, report_id)
            actor_id = scope.member_for_committee(round_row.committee_id)
            if not scope.can_manage_committee(round_row.committee_id):
                raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen Slots absagen")
            if report.status in {"withdrawn", "exam_day_cancelled"}:
                raise ValueError("Die Ausfallmeldung ist bereits abgeschlossen")
            self._assert_before_start(
                session, day, session.get(ExamDayAssignment, report.exam_day_assignment_id), current
            )
            assignment = session.get(ExamDayAssignment, report.exam_day_assignment_id)
            if assignment is None:
                raise ValueError("Besetzung nicht gefunden")
            old_status = report.status
            report.status = "exam_day_cancelled"
            report.version += 1
            report.updated_at = _stamp(current)
            self._audit(
                session,
                report,
                actor_id or report.committee_member_id,
                "cancelled",
                old_status,
                report.status,
                current,
                {"reason": reason},
            )
            calendar_target = (round_row.id, assignment.id)
            result = self._view(session, report)
        if calendar_target is not None:
            self.calendar_service.cancel_assignment(*calendar_target)
        return result

    def _target(self, session, payload: dict[str, Any]):
        day_id = self._required_int(payload, "exam_day_id")
        assignment_id = payload.get("exam_day_assignment_id")
        assignment = (
            session.get(ExamDayAssignment, int(assignment_id))
            if assignment_id is not None
            else None
        )
        if assignment is None and payload.get("committee_member_id") is not None:
            assignment = session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == day_id,
                    ExamDayAssignment.committee_member_id == int(payload["committee_member_id"]),
                )
            ).first()
        day = session.get(ExamDay, day_id)
        exam_round = session.get(ExamRound, day.exam_round_id) if day else None
        target = (
            session.get(CommitteeMember, assignment.committee_member_id) if assignment else None
        )
        if (
            day is None
            or exam_round is None
            or assignment is None
            or target is None
            or assignment.exam_day_id != day.id
        ):
            raise ValueError("Bestätigte Besetzung nicht gefunden")
        return day, exam_round, assignment, target

    def _eligible_candidates(
        self, session, day, assignment, target, *, urgent: bool, include_member: int | None = None
    ):
        regular = {
            row.committee_member_id
            for row in session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == day.id,
                    ExamDayAssignment.assignment_role == "examiner",
                )
            ).all()
        }
        members = session.scalars(
            select(CommitteeMember).where(
                CommitteeMember.committee_id
                == session.get(ExamRound, day.exam_round_id).committee_id,
                CommitteeMember.is_active == 1,
            )
        ).all()
        eligible = [
            member
            for member in members
            if member.id != target.id
            and member.id not in regular
            and self._available(session, day, assignment.day_part, member.id)
            and self._conflict_free(session, day, assignment.day_part, member.id)
            and (
                assignment.assignment_role == "fallback"
                or member.representing_side == target.representing_side
            )
        ]
        fallback = None
        if assignment.assignment_role == "examiner":
            fallback_assignments = session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == day.id,
                    ExamDayAssignment.assignment_role == "fallback",
                    ExamDayAssignment.day_part.in_((assignment.day_part, "full_day")),
                )
            ).all()
            fallback_ids = {row.committee_member_id for row in fallback_assignments}
            fallback = next((member for member in eligible if member.id in fallback_ids), None)
            eligible = [member for member in eligible if member.id not in fallback_ids]
        if include_member is not None:
            candidate = session.get(CommitteeMember, include_member)
            if (
                candidate
                and candidate.id not in {member.id for member in eligible}
                and candidate.id != (fallback.id if fallback else None)
            ):
                if (
                    candidate.id != target.id
                    and candidate.is_active
                    and self._available(session, day, assignment.day_part, candidate.id)
                    and self._conflict_free(session, day, assignment.day_part, candidate.id)
                ):
                    if (
                        assignment.assignment_role == "fallback"
                        or candidate.representing_side == target.representing_side
                    ):
                        eligible.append(candidate)
        return eligible, fallback

    def _available(self, session, day, day_part: str, member_id: int) -> bool:
        candidate_day = session.scalars(
            select(CandidateExamDay).where(
                CandidateExamDay.exam_round_id == day.exam_round_id,
                CandidateExamDay.date == day.date,
            )
        ).first()
        if candidate_day is None:
            return False
        availability = session.scalars(
            select(MemberAvailability).where(
                MemberAvailability.candidate_exam_day_id == candidate_day.id,
                MemberAvailability.committee_member_id == member_id,
            )
        ).first()
        return availability is not None and availability.availability in {"full_day", day_part}

    def _conflict_free(self, session, day, day_part: str, member_id: int) -> bool:
        half_year_id = session.get(ExamRound, day.exam_round_id).exam_half_year_id
        other_days = session.scalars(
            select(ExamDay)
            .join(ExamRound, ExamRound.id == ExamDay.exam_round_id)
            .where(
                ExamRound.exam_half_year_id == half_year_id,
                ExamDay.id != day.id,
                ExamDay.status == "confirmed",
            )
        ).all()
        for other_day in other_days:
            if other_day.date != day.date:
                continue
            assignments = session.scalars(
                select(ExamDayAssignment).where(
                    ExamDayAssignment.exam_day_id == other_day.id,
                    ExamDayAssignment.committee_member_id == member_id,
                )
            ).all()
            if any(self._parts_overlap(day_part, row.day_part) for row in assignments):
                return False
        return True

    @staticmethod
    def _parts_overlap(first: str, second: str) -> bool:
        return first == "full_day" or second == "full_day" or first == second

    def _open_further_search(self, session, report, current: datetime) -> None:
        assignment = session.get(ExamDayAssignment, report.exam_day_assignment_id)
        target = session.get(CommitteeMember, report.committee_member_id)
        day = session.get(ExamDay, report.exam_day_id)
        if not assignment or not target or not day:
            return
        eligible, _fallback = self._eligible_candidates(
            session, day, assignment, target, urgent=True
        )
        old_status = report.status
        report.status = "replacement_requested" if eligible else "no_replacement_available"
        for member in eligible:
            existing = session.scalars(
                select(ReplacementResponse).where(
                    ReplacementResponse.absence_report_id == report.id,
                    ReplacementResponse.committee_member_id == member.id,
                )
            ).first()
            if existing is None:
                session.add(
                    ReplacementResponse(
                        absence_report_id=report.id,
                        committee_member_id=member.id,
                        requested_at=_stamp(current),
                        urgent=1,
                    )
                )
        self._audit(
            session,
            report,
            report.reported_by_member_id,
            "replacement_search_opened",
            old_status,
            report.status,
            current,
        )

    def _authorized_report(self, session, scope, report_id):
        report = session.get(AbsenceReport, report_id)
        if report is None:
            raise ValueError("Ausfallmeldung nicht gefunden")
        day = session.get(ExamDay, report.exam_day_id)
        round_row = session.get(ExamRound, day.exam_round_id) if day else None
        if day is None or round_row is None or not self._visible(session, report, scope):
            raise PermissionError("Ausfallmeldung ist nicht zugänglich")
        return report, day, round_row

    def _report_round_id(self, report_id: int) -> int | None:
        with session_scope(self.db_path) as session:
            report = session.get(AbsenceReport, report_id)
            if report is None:
                return None
            day = session.get(ExamDay, report.exam_day_id)
            return day.exam_round_id if day is not None else None

    def _visible(self, session, report, scope) -> bool:
        day = session.get(ExamDay, report.exam_day_id)
        round_row = session.get(ExamRound, day.exam_round_id) if day else None
        return bool(round_row and round_row.committee_id in scope.committee_ids)

    def _assert_before_start(self, session, day, assignment, current):
        if assignment is None or current >= self._assignment_start(session, day, assignment):
            raise ValueError(
                "Ausfallmeldungen und Korrekturen sind nach Beginn des "
                "Tagesabschnitts nicht zulässig"
            )

    def _assignment_start(self, session, day, assignment):
        slots = self._affected_slots(session, day, assignment)
        if slots:
            return min(_parse(slot.starts_at) for slot in slots)
        return datetime.fromisoformat(day.date).replace(tzinfo=UTC)

    def _affected_slots(self, session, day, assignment):
        slots = session.scalars(select(ExamSlot).where(ExamSlot.exam_day_id == day.id)).all()
        if assignment.day_part == "full_day":
            return slots
        return [
            slot
            for slot in slots
            if (assignment.day_part == "morning" and _parse(slot.starts_at).hour < 12)
            or (assignment.day_part == "afternoon" and _parse(slot.starts_at).hour >= 12)
        ]

    @staticmethod
    def _audit(
        session, report, actor_id, event_type, from_status, to_status, current, details=None
    ):
        session.add(
            AbsenceAuditEvent(
                absence_report_id=report.id,
                actor_member_id=actor_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                details=json.dumps(details, ensure_ascii=False) if details else None,
                created_at=_stamp(current),
            )
        )

    @staticmethod
    def _view(session, report):
        responses = session.scalars(
            select(ReplacementResponse)
            .where(ReplacementResponse.absence_report_id == report.id)
            .order_by(ReplacementResponse.requested_at, ReplacementResponse.id)
        ).all()
        audit = session.scalars(
            select(AbsenceAuditEvent)
            .where(AbsenceAuditEvent.absence_report_id == report.id)
            .order_by(AbsenceAuditEvent.created_at, AbsenceAuditEvent.id)
        ).all()
        return {
            "id": report.id,
            "exam_day_id": report.exam_day_id,
            "exam_day_assignment_id": report.exam_day_assignment_id,
            "committee_member_id": report.committee_member_id,
            "reported_by_member_id": report.reported_by_member_id,
            "reported_at": report.reported_at,
            "reason": report.reason,
            "status": report.status,
            "selected_replacement_member_id": report.selected_replacement_member_id,
            "version": report.version,
            "created_at": report.created_at,
            "updated_at": report.updated_at,
            "responses": [
                {
                    "id": row.id,
                    "committee_member_id": row.committee_member_id,
                    "response": row.response,
                    "requested_at": row.requested_at,
                    "expires_at": row.expires_at,
                    "urgent": bool(row.urgent),
                    "responded_at": row.responded_at,
                }
                for row in responses
            ],
            "audit": [
                {
                    "id": row.id,
                    "actor_member_id": row.actor_member_id,
                    "event_type": row.event_type,
                    "from_status": row.from_status,
                    "to_status": row.to_status,
                    "details": row.details,
                    "created_at": row.created_at,
                }
                for row in audit
            ],
        }

    def _notify(self, data, *, title, message, report_id):
        if not data:
            return
        committee_id, round_id, member_ids, event_type, urgent = data
        try:
            self.notification_service.create_direct(
                committee_id=committee_id,
                round_id=round_id,
                recipient_member_ids=member_ids,
                event_type=event_type,
                title=title,
                message=message,
                action_path=f"/absence-reports/{report_id}",
                origin_key=f"absence-report:{report_id}:{event_type}",
                urgent=urgent,
            )
        except Exception:
            # Notification delivery must not roll back the committed domain event.
            return

    @staticmethod
    def _required_int(payload, field):
        try:
            value = int(payload[field])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{field} is required") from error
        if value < 1:
            raise ValueError(f"{field} is invalid")
        return value

    @staticmethod
    def _optional_reason(value):
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError("Der Ausfallgrund darf höchstens 500 Zeichen enthalten")
        return value.strip() or None

    @classmethod
    def _required_reason(cls, payload):
        reason = cls._optional_reason(payload.get("reason"))
        if not reason:
            raise ValueError("Eine Begründung ist erforderlich")
        return reason

    @staticmethod
    def _check_version(report, payload):
        if "version" in payload and int(payload["version"]) != report.version:
            raise ValueError("Die Ausfallmeldung wurde zwischenzeitlich geändert")
