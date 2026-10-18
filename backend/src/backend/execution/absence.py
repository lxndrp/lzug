"""Transactional absence and replacement workflow for confirmed exam plans."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.execution.absence_ports import (
    AbsenceAssignmentSnapshot,
    AbsenceDaySnapshot,
    AbsenceMemberSnapshot,
    AbsenceReportSnapshot,
    AbsenceRoundSnapshot,
    AbsenceTargetSnapshot,
    AbsenceUnitOfWork,
    AbsenceUnitOfWorkFactory,
    AbsenceViewSnapshot,
)
from backend.execution.calendar_ports import ExecutionCalendarPort
from backend.execution.lifecycle_ports import MutationLockCommand, MutationLockKind
from backend.identity.authorization import AuthorizationScope
from backend.notifications.service import NotificationService

ACTIVE_STATUSES = {
    "reported",
    "fallback_requested",
    "fallback_confirmed",
    "fallback_expired",
    "replacement_requested",
}
TERMINAL_STATUSES = {"replacement_selected", "resolved", "withdrawn", "exam_day_cancelled"}
SIDES = {"employer", "employee", "school"}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _stamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    return _now(datetime.fromisoformat(value.replace("Z", "+00:00")))


class AbsenceService:
    """Own absence rules while Application/Persistence own transaction mechanics."""

    def __init__(
        self,
        unit_of_work_factory: AbsenceUnitOfWorkFactory,
        *,
        notification_service: NotificationService,
        calendar_service: ExecutionCalendarPort,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.notification_service = notification_service
        self.calendar_service = calendar_service

    def list(self, scope: AuthorizationScope) -> list[dict[str, Any]]:
        with self.unit_of_work_factory.read_scope() as unit_of_work:
            reports = unit_of_work.reports_for_committees(tuple(scope.committee_ids))
            return [self._view(report) for report in reports]

    def get(self, scope: AuthorizationScope, report_id: int) -> dict[str, Any] | None:
        with self.unit_of_work_factory.read_scope() as unit_of_work:
            snapshot = unit_of_work.report_view(report_id)
            if snapshot is None or snapshot.round.committee_id not in scope.committee_ids:
                return None
            return self._view(snapshot)

    def report(
        self,
        scope: AuthorizationScope,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        notification_data: tuple[int, int, set[int], str, bool] | None = None
        with self.unit_of_work_factory() as unit_of_work:
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, None, payload)
            )
            target = self._target(unit_of_work, payload)
            actor_id = scope.member_for_committee(target.round.committee_id)
            if actor_id is None:
                raise ValueError("Akteur gehört nicht zum Prüfungsausschuss")
            if not scope.can_manage_committee(target.round.committee_id) and actor_id != (
                target.target.id
            ):
                raise PermissionError(
                    "Ein Ausfall darf nur für das eigene Mitglied gemeldet werden"
                )
            self._assert_before_start(unit_of_work, target.day, target.assignment, current)
            if target.round.status != "plan_confirmed" or target.day.status != "confirmed":
                raise ValueError(
                    "Ausfälle können nur in einem bestätigten Prüfungsplan gemeldet werden"
                )
            if unit_of_work.active_report_exists(
                target.assignment.id, frozenset(ACTIVE_STATUSES | TERMINAL_STATUSES)
            ):
                raise ValueError("Für diese Besetzung existiert bereits eine Ausfallmeldung")

            day_guard = unit_of_work.guard_day_mutation(
                day_id=target.day.id,
                kind="staffing",
                entity_id=target.assignment.id,
                payload=payload,
                actor_member_id=actor_id,
            )
            urgent = current + timedelta(hours=48) > self._assignment_start(
                unit_of_work, target.day, target.assignment
            )
            eligible, fallback = self._eligible_candidates(
                unit_of_work, target.day, target.assignment, target.target, urgent=urgent
            )
            selected_ids: set[int] = set()
            expires_at: str | None = None
            status = "reported"
            if (
                target.assignment.assignment_role == "examiner"
                and fallback is not None
                and not urgent
            ):
                selected_ids.add(fallback.id)
                expires_at = _stamp(current + timedelta(hours=24))
                status = "fallback_requested"
            else:
                selected_ids.update(member.id for member in eligible)
                if urgent and fallback is not None:
                    selected_ids.add(fallback.id)
                status = "replacement_requested" if selected_ids else "no_replacement_available"

            report = unit_of_work.insert_report(
                target=target,
                reported_by_member_id=actor_id,
                reported_at=_stamp(current),
                reason=self._optional_reason(payload.get("reason")),
                status=status,
            )
            for member_id in sorted(selected_ids):
                unit_of_work.insert_response(
                    report_id=report.id,
                    member_id=member_id,
                    requested_at=_stamp(current),
                    expires_at=expires_at if fallback and member_id == fallback.id else None,
                    urgent=urgent,
                )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=actor_id,
                event_type="reported",
                from_status=None,
                to_status=status,
                created_at=_stamp(current),
            )
            unit_of_work.complete_day_mutation(
                day_guard,
                actor_member_id=actor_id,
                reason=report.reason,
            )
            notify_ids = {actor_id, target.target.id} | set(
                unit_of_work.notification_recipients(
                    target.round.committee_id,
                    roles=frozenset({"chair", "deputy_chair"}),
                )
            )
            notify_ids.update(selected_ids)
            notification_data = (
                target.round.committee_id,
                target.round.id,
                notify_ids,
                "urgent_replacement_requested" if urgent else "examiner_absence_reported",
                urgent,
            )
            result = self._required_view(unit_of_work, report.id)
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
        with self.unit_of_work_factory() as unit_of_work:
            response = unit_of_work.response(response_id)
            if response is None or response.committee_member_id not in scope.member_ids:
                raise PermissionError("Ersatzanfrage ist nicht zugänglich")
            context = unit_of_work.report_context(response.absence_report_id)
            if context is None:
                raise PermissionError("Ersatzanfrage ist nicht zugänglich")
            report, day, round_row = context
            if round_row.committee_id not in scope.committee_ids:
                raise PermissionError("Ersatzanfrage ist nicht zugänglich")
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, payload)
            )
            answer = payload.get("response")
            if answer not in {"available", "unavailable"}:
                raise ValueError("Antwort muss available oder unavailable sein")
            if response.response != "pending":
                raise ValueError("Diese Ersatzanfrage wurde bereits beantwortet")
            day_guard = unit_of_work.guard_day_mutation(
                day_id=day.id,
                kind="absence",
                entity_id=report.id,
                payload=payload,
                actor_member_id=response.committee_member_id,
            )
            expired = bool(response.expires_at and _parse(response.expires_at) <= current)
            if expired:
                answer = "unavailable"
            old_status = report.status
            unit_of_work.update_response(
                response_id,
                response=answer,
                responded_at=_stamp(current),
            )
            status = report.status
            if answer == "available" and report.status == "fallback_requested":
                status = "fallback_confirmed"
            elif answer == "unavailable" and report.status == "fallback_requested":
                if expired:
                    status = "fallback_expired"
                    unit_of_work.insert_audit(
                        report_id=report.id,
                        actor_member_id=response.committee_member_id,
                        event_type="fallback_expired",
                        from_status=old_status,
                        to_status=status,
                        created_at=_stamp(current),
                    )
                status = self._open_further_search(unit_of_work, report, day, status, current)
            updated_report = unit_of_work.update_report(
                report.id, status=status, current=_stamp(current), increment_version=True
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=response.committee_member_id,
                event_type="response",
                from_status=old_status,
                to_status=updated_report.status,
                created_at=_stamp(current),
            )
            recipient_ids = set(
                unit_of_work.notification_recipients(
                    round_row.committee_id,
                    roles=frozenset({"chair", "deputy_chair"}),
                )
            )
            recipient_ids.update(unit_of_work.response_member_ids(report.id))
            notification_data = (
                round_row.committee_id,
                round_row.id,
                recipient_ids,
                (
                    "fallback_confirmation_expired"
                    if expired
                    else (
                        "replacement_requested"
                        if updated_report.status == "replacement_requested"
                        else "fallback_confirmation_requested"
                    )
                ),
                False,
            )
            unit_of_work.complete_day_mutation(
                day_guard,
                actor_member_id=response.committee_member_id,
            )
            result = self._required_view(unit_of_work, report.id)
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
        sync_calendar = True
        report_round_id: int | None = None
        with self.unit_of_work_factory.read_scope() as unit_of_work:
            context = unit_of_work.report_context(report_id)
            if context is not None and context[1].closure_status == "open":
                report, day, round_row = context
                report_round_id = round_row.id
                self._require_replacement_selection(
                    unit_of_work, report, day, round_row, scope, payload, current
                )
                unit_of_work.assert_mutation_allowed(
                    MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, payload)
                )
        if report_round_id is not None:
            self.calendar_service.sync_round(report_round_id)

        with self.unit_of_work_factory() as unit_of_work:
            context = unit_of_work.report_context(report_id)
            if context is None:
                raise ValueError("Ausfallmeldung nicht gefunden")
            report, day, round_row = context
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, payload)
            )
            actor_id = self._require_replacement_selection(
                unit_of_work, report, day, round_row, scope, payload, current
            )
            day_guard = unit_of_work.guard_day_mutation(
                day_id=day.id,
                kind="absence",
                entity_id=report.id,
                payload=payload,
                actor_member_id=actor_id,
            )
            member_id = self._required_int(payload, "committee_member_id")
            assignment, replacement = self._available_replacement(
                unit_of_work, report, day, member_id
            )
            old_status = report.status
            old_member_id = assignment.committee_member_id
            unit_of_work.update_assignment_member(
                assignment.id,
                replacement.id,
                fallback_status=("confirmed" if assignment.assignment_role == "fallback" else None),
            )
            updated_report = unit_of_work.update_report(
                report.id,
                status="replacement_selected",
                current=_stamp(current),
                selected_replacement_member_id=replacement.id,
                update_selected_replacement=True,
                increment_version=True,
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=actor_id,
                event_type="replacement_selected",
                from_status=old_status,
                to_status=updated_report.status,
                created_at=_stamp(current),
                details={"member_id": replacement.id},
            )
            unit_of_work.complete_day_mutation(day_guard, actor_member_id=actor_id)
            notify_ids = {old_member_id, replacement.id} | set(
                unit_of_work.notification_recipients(
                    round_row.committee_id, exclude_member_id=replacement.id
                )
            )
            notification_data = (
                round_row.committee_id,
                round_row.id,
                notify_ids,
                "replacement_selected",
                False,
            )
            calendar_round_id = round_row.id
            sync_calendar = day.closure_status == "open"
            result = self._required_view(unit_of_work, report.id)
        if calendar_round_id is not None and sync_calendar:
            self.calendar_service.sync_round(calendar_round_id)
        self._notify(
            notification_data,
            title="Ersatzmitglied ausgewählt",
            message="Die Ersatzbesetzung wurde kontrolliert ausgewählt.",
            report_id=result["id"],
        )
        return result

    def _available_replacement(
        self,
        unit_of_work: AbsenceUnitOfWork,
        report: AbsenceReportSnapshot,
        day: AbsenceDaySnapshot,
        member_id: int,
    ) -> tuple[AbsenceAssignmentSnapshot, AbsenceMemberSnapshot]:
        """Recheck response and current eligibility inside the selection transaction."""
        view = unit_of_work.report_view(report.id)
        response = next(
            (
                row
                for row in (view.responses if view is not None else ())
                if row.committee_member_id == member_id and row.response == "available"
            ),
            None,
        )
        if response is None:
            raise ValueError("Nur ein verfügbares angefragtes Mitglied kann ausgewählt werden")
        assignment = unit_of_work.assignment(report.exam_day_assignment_id)
        target = unit_of_work.member(report.committee_member_id)
        replacement = unit_of_work.member(member_id)
        if assignment is None or target is None or replacement is None:
            raise ValueError("Besetzung oder Mitglied nicht gefunden")
        eligible, fallback = self._eligible_candidates(
            unit_of_work, day, assignment, target, urgent=True, include_member=member_id
        )
        if replacement.id not in {member.id for member in eligible} and replacement.id != (
            fallback.id if fallback else None
        ):
            raise ValueError("Das gewählte Mitglied ist nicht mehr geeignet oder verfügbar")
        return assignment, replacement

    def _require_replacement_selection(
        self,
        unit_of_work: AbsenceUnitOfWork,
        report: AbsenceReportSnapshot,
        day: AbsenceDaySnapshot,
        round_row: AbsenceRoundSnapshot,
        scope: AuthorizationScope,
        payload: dict[str, Any],
        current: datetime,
    ) -> int:
        """Check access, start time, and report version before guarding the day."""
        if not scope.can_manage_committee(round_row.committee_id):
            raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen Ersatz auswählen")
        assignment = unit_of_work.assignment(report.exam_day_assignment_id)
        self._assert_before_start(unit_of_work, day, assignment, current)
        if report.status not in {
            "fallback_confirmed",
            "replacement_requested",
            "fallback_expired",
        }:
            raise ValueError("Die Ausfallmeldung ist nicht auswählbar")
        self._check_version(report, payload)
        actor_id = scope.member_for_committee(round_row.committee_id)
        if actor_id is None:
            raise PermissionError("Forbidden.")
        return actor_id

    def withdraw(
        self,
        scope: AuthorizationScope,
        report_id: int,
        payload: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _now(now)
        mutation_payload = payload or {}
        with self.unit_of_work_factory() as unit_of_work:
            report, day, round_row = self._authorized_report(unit_of_work, scope, report_id)
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, mutation_payload)
            )
            actor_id = scope.member_for_committee(round_row.committee_id)
            if actor_id != report.committee_member_id and not scope.can_manage_committee(
                round_row.committee_id
            ):
                raise PermissionError("Nur die meldende Person oder die Leitung darf zurücknehmen")
            assignment = unit_of_work.assignment(report.exam_day_assignment_id)
            self._assert_before_start(unit_of_work, day, assignment, current)
            if report.selected_replacement_member_id is not None:
                raise ValueError("Nach einer Ersatzwahl ist eine Rücknahme nicht mehr möglich")
            effective_actor_id = actor_id or report.committee_member_id
            day_guard = unit_of_work.guard_day_mutation(
                day_id=day.id,
                kind="absence",
                entity_id=report.id,
                payload=mutation_payload,
                actor_member_id=effective_actor_id,
            )
            updated_report = unit_of_work.update_report(
                report.id, status="withdrawn", current=_stamp(current), increment_version=True
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=effective_actor_id,
                event_type="withdrawn",
                from_status=report.status,
                to_status=updated_report.status,
                created_at=_stamp(current),
            )
            unit_of_work.complete_day_mutation(day_guard, actor_member_id=effective_actor_id)
            return self._required_view(unit_of_work, report.id)

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
        sync_calendar = True
        with self.unit_of_work_factory() as unit_of_work:
            report, day, round_row = self._authorized_report(unit_of_work, scope, report_id)
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, payload)
            )
            actor_id = scope.member_for_committee(round_row.committee_id)
            if not scope.can_manage_committee(round_row.committee_id):
                raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen wieder öffnen")
            assignment = unit_of_work.assignment(report.exam_day_assignment_id)
            self._assert_before_start(unit_of_work, day, assignment, current)
            if report.status not in {"replacement_selected", "resolved", "exam_day_cancelled"}:
                raise ValueError("Die Ausfallmeldung ist nicht wieder zu öffnen")
            effective_actor_id = actor_id or report.committee_member_id
            day_guard = unit_of_work.guard_day_mutation(
                day_id=day.id,
                kind="absence",
                entity_id=report.id,
                payload=payload,
                actor_member_id=effective_actor_id,
            )
            if assignment is None:
                raise ValueError("Besetzung nicht gefunden")
            if report.selected_replacement_member_id is not None:
                unit_of_work.update_assignment_member(assignment.id, report.committee_member_id)
            updated_report = unit_of_work.update_report(
                report.id,
                status="replacement_requested",
                current=_stamp(current),
                selected_replacement_member_id=None,
                update_selected_replacement=True,
                increment_version=True,
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=effective_actor_id,
                event_type="reopened",
                from_status=report.status,
                to_status=updated_report.status,
                created_at=_stamp(current),
                details={"reason": reason},
            )
            unit_of_work.complete_day_mutation(
                day_guard, actor_member_id=effective_actor_id, reason=reason
            )
            calendar_round_id = round_row.id
            sync_calendar = day.closure_status == "open"
            result = self._required_view(unit_of_work, report.id)
        if calendar_round_id is not None and sync_calendar:
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
        sync_calendar = True
        with self.unit_of_work_factory() as unit_of_work:
            report, day, round_row = self._authorized_report(unit_of_work, scope, report_id)
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(MutationLockKind.ABSENCE_REPORT, report.id, payload)
            )
            actor_id = scope.member_for_committee(round_row.committee_id)
            if not scope.can_manage_committee(round_row.committee_id):
                raise PermissionError("Nur Vorsitz oder Stellvertretung dürfen Slots absagen")
            if report.status in {"withdrawn", "exam_day_cancelled"}:
                raise ValueError("Die Ausfallmeldung ist bereits abgeschlossen")
            effective_actor_id = actor_id or report.committee_member_id
            day_guard = unit_of_work.guard_day_mutation(
                day_id=day.id,
                kind="absence",
                entity_id=report.id,
                payload=payload,
                actor_member_id=effective_actor_id,
            )
            self._assert_before_start(
                unit_of_work,
                day,
                unit_of_work.assignment(report.exam_day_assignment_id),
                current,
            )
            assignment = unit_of_work.assignment(report.exam_day_assignment_id)
            if assignment is None:
                raise ValueError("Besetzung nicht gefunden")
            updated_report = unit_of_work.update_report(
                report.id,
                status="exam_day_cancelled",
                current=_stamp(current),
                increment_version=True,
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=effective_actor_id,
                event_type="cancelled",
                from_status=report.status,
                to_status=updated_report.status,
                created_at=_stamp(current),
                details={"reason": reason},
            )
            unit_of_work.complete_day_mutation(
                day_guard, actor_member_id=effective_actor_id, reason=reason
            )
            calendar_target = (round_row.id, assignment.id)
            sync_calendar = day.closure_status == "open"
            result = self._required_view(unit_of_work, report.id)
        if calendar_target is not None and sync_calendar:
            self.calendar_service.cancel_assignment(*calendar_target)
        return result

    def _target(
        self, unit_of_work: AbsenceUnitOfWork, payload: dict[str, Any]
    ) -> AbsenceTargetSnapshot:
        day_id = self._required_int(payload, "exam_day_id")
        assignment_id = payload.get("exam_day_assignment_id")
        member_id = payload.get("committee_member_id")
        target = unit_of_work.target(
            day_id,
            int(assignment_id) if assignment_id is not None else None,
            int(member_id) if member_id is not None else None,
        )
        if target is None:
            raise ValueError("Bestätigte Besetzung nicht gefunden")
        return target

    def _eligible_candidates(
        self,
        unit_of_work: AbsenceUnitOfWork,
        day: AbsenceDaySnapshot,
        assignment: AbsenceAssignmentSnapshot,
        target: AbsenceMemberSnapshot,
        *,
        urgent: bool,
        include_member: int | None = None,
    ) -> tuple[Sequence[AbsenceMemberSnapshot], AbsenceMemberSnapshot | None]:
        del urgent  # Urgency changes the caller's requests, not candidate eligibility.
        facts = unit_of_work.candidate_facts(day, assignment)
        eligible = [
            member
            for member in facts.active_members
            if member.id != target.id
            and member.id not in facts.regular_member_ids
            and member.id in facts.available_member_ids
            and member.id in facts.conflict_free_member_ids
            and (
                assignment.assignment_role == "fallback"
                or member.representing_side == target.representing_side
            )
        ]
        fallback = None
        if assignment.assignment_role == "examiner":
            fallback = next(
                (member for member in eligible if member.id in facts.fallback_member_ids), None
            )
            eligible = [member for member in eligible if member.id not in facts.fallback_member_ids]
        if include_member is not None:
            candidate = next(
                (member for member in facts.active_members if member.id == include_member), None
            )
            if (
                candidate
                and candidate.id not in {member.id for member in eligible}
                and candidate.id != (fallback.id if fallback else None)
                and candidate.id != target.id
                and candidate.id in facts.available_member_ids
                and candidate.id in facts.conflict_free_member_ids
                and (
                    assignment.assignment_role == "fallback"
                    or candidate.representing_side == target.representing_side
                )
            ):
                eligible.append(candidate)
        return eligible, fallback

    def _open_further_search(
        self,
        unit_of_work: AbsenceUnitOfWork,
        report: AbsenceReportSnapshot,
        day: AbsenceDaySnapshot,
        initial_status: str,
        current: datetime,
    ) -> str:
        assignment = unit_of_work.assignment(report.exam_day_assignment_id)
        target = unit_of_work.member(report.committee_member_id)
        if assignment is None or target is None:
            return initial_status
        eligible, _fallback = self._eligible_candidates(
            unit_of_work, day, assignment, target, urgent=True
        )
        status = "replacement_requested" if eligible else "no_replacement_available"
        response_member_ids = unit_of_work.response_member_ids(report.id)
        for member in eligible:
            if member.id not in response_member_ids:
                unit_of_work.insert_response(
                    report_id=report.id,
                    member_id=member.id,
                    requested_at=_stamp(current),
                    expires_at=None,
                    urgent=True,
                )
        unit_of_work.insert_audit(
            report_id=report.id,
            actor_member_id=report.reported_by_member_id,
            event_type="replacement_search_opened",
            from_status=initial_status,
            to_status=status,
            created_at=_stamp(current),
        )
        return status

    def _authorized_report(
        self, unit_of_work: AbsenceUnitOfWork, scope: AuthorizationScope, report_id: int
    ) -> tuple[AbsenceReportSnapshot, AbsenceDaySnapshot, AbsenceRoundSnapshot]:
        context = unit_of_work.report_context(report_id)
        if context is None:
            raise ValueError("Ausfallmeldung nicht gefunden")
        report, day, round_row = context
        if round_row.committee_id not in scope.committee_ids:
            raise PermissionError("Ausfallmeldung ist nicht zugänglich")
        return report, day, round_row

    def _assert_before_start(
        self,
        unit_of_work: AbsenceUnitOfWork,
        day: AbsenceDaySnapshot,
        assignment: AbsenceAssignmentSnapshot | None,
        current: datetime,
    ) -> None:
        if day.closure_status == "reopening":
            return
        if assignment is None or current >= self._assignment_start(unit_of_work, day, assignment):
            raise ValueError(
                "Ausfallmeldungen und Korrekturen sind nach Beginn des "
                "Tagesabschnitts nicht zulässig"
            )

    def _assignment_start(
        self,
        unit_of_work: AbsenceUnitOfWork,
        day: AbsenceDaySnapshot,
        assignment: AbsenceAssignmentSnapshot,
    ) -> datetime:
        slots = self._affected_slots(unit_of_work, day, assignment)
        if slots:
            return min(_parse(slot) for slot in slots)
        return datetime.fromisoformat(day.date).replace(tzinfo=UTC)

    def _affected_slots(
        self,
        unit_of_work: AbsenceUnitOfWork,
        day: AbsenceDaySnapshot,
        assignment: AbsenceAssignmentSnapshot,
    ) -> Sequence[str]:
        slots = unit_of_work.assignment_slots(day.id)
        if assignment.day_part == "full_day":
            return slots
        return [
            starts_at
            for starts_at in slots
            if (assignment.day_part == "morning" and _parse(starts_at).hour < 12)
            or (assignment.day_part == "afternoon" and _parse(starts_at).hour >= 12)
        ]

    @staticmethod
    def _view(snapshot: AbsenceViewSnapshot) -> dict[str, Any]:
        report = snapshot.report
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
                    "urgent": row.urgent,
                    "responded_at": row.responded_at,
                }
                for row in snapshot.responses
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
                for row in snapshot.audit
            ],
        }

    @staticmethod
    def _required_view(unit_of_work: AbsenceUnitOfWork, report_id: int) -> dict[str, Any]:
        snapshot = unit_of_work.report_view(report_id)
        if snapshot is None:
            raise ValueError("Ausfallmeldung nicht gefunden")
        return AbsenceService._view(snapshot)

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
    def _check_version(report: AbsenceReportSnapshot, payload: dict[str, Any]) -> None:
        if "version" in payload and int(payload["version"]) != report.version:
            raise ValueError("Die Ausfallmeldung wurde zwischenzeitlich geändert")
