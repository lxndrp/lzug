"""Framework-neutral execution commands for attendance and exam start."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from backend.execution.slot_ports import (
    AttendanceCommand,
    AttendanceValues,
    ExecutionUnitOfWorkFactory,
    SlotSnapshot,
    SlotStartCommand,
    SlotStatusCommand,
)

ATTENDANCE_VALUES = frozenset({"open", "present", "late", "absent"})
REPRESENTING_SIDES = frozenset({"employer", "employee", "school"})
EXECUTION_STATUS_VALUES = frozenset(
    {"open", "running", "completed", "cancelled", "needs_follow_up"}
)
EXECUTION_STATUS_TRANSITIONS = {
    "open": {"cancelled"},
    "running": {"completed", "needs_follow_up"},
    "needs_follow_up": {"completed"},
}


class ExecutionService:
    """Apply attendance and start rules through an execution-owned UoW."""

    def __init__(
        self,
        unit_of_work_factory: ExecutionUnitOfWorkFactory,
        *,
        clock=None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC).replace(microsecond=0).isoformat())

    def save_candidate_attendance(
        self,
        day_id: int,
        slot_id: int,
        command: AttendanceCommand,
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with self._unit_of_work_factory(write=True) as work:
            work.confirmed_slot(day_id, slot_id)
            existing = work.candidate_attendance(slot_id)
            values = self._attendance_values(command, existing)
            if (
                existing is not None
                and existing["status"] == values["status"]
                and existing["arrived_at"] == values["arrived_at"]
            ):
                return dict(existing)
            return dict(
                work.save_candidate_attendance(
                    day_id,
                    slot_id,
                    values,
                    actor_member_id=actor_member_id,
                    expected_day_revision=command.get("expected_day_revision"),
                )
            )

    def save_member_attendance(
        self,
        day_id: int,
        assignment_id: int,
        command: AttendanceCommand,
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with self._unit_of_work_factory(write=True) as work:
            assignment = work.confirmed_assignment(day_id, assignment_id)
            member_id = assignment["committee_member_id"]
            existing = work.member_attendance(day_id, member_id)
            values = self._attendance_values(command, existing)
            if (
                existing is not None
                and existing["status"] == values["status"]
                and existing["arrived_at"] == values["arrived_at"]
            ):
                return dict(existing)
            return dict(
                work.save_member_attendance(
                    day_id,
                    assignment_id,
                    member_id,
                    values,
                    actor_member_id=actor_member_id,
                    expected_day_revision=command.get("expected_day_revision"),
                )
            )

    def start_slot(
        self,
        day_id: int,
        slot_id: int,
        command: SlotStartCommand,
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with self._unit_of_work_factory(write=True) as work:
            slot = work.confirmed_slot(day_id, slot_id)
            self._validate_startable_slot(slot)
            candidate = work.candidate_attendance(slot_id)
            if candidate is None or candidate["status"] not in {"present", "late"}:
                raise ValueError("Prüfling muss als anwesend oder verspätet erfasst sein")

            assignments = work.assignments(day_id)
            eligible = [
                assignment
                for assignment in assignments
                if assignment["assignment_role"] == "examiner"
                and self._assignment_applies_to_slot(assignment, slot)
            ]
            attendance = {
                assignment["committee_member_id"]: work.member_attendance(
                    day_id, assignment["committee_member_id"]
                )
                for assignment in eligible
            }
            present_ids = {
                member_id
                for member_id, record in attendance.items()
                if record is not None and record["status"] in {"present", "late"}
            }
            members = work.members_by_id(sorted(present_ids))
            participant_ids = frozenset(present_ids & members.keys())
            sides = {members[member_id]["representing_side"] for member_id in participant_ids}
            if len(participant_ids) < 3 or not REPRESENTING_SIDES.issubset(sides):
                raise ValueError(
                    "Mindestens drei anwesende reguläre Prüfer mit allen drei "
                    "Vertreterseiten sind erforderlich"
                )

            requested = command.get("actual_started_at")
            started_at = slot["actual_started_at"]
            if started_at is not None:
                if slot["execution_status"] != "running":
                    raise ValueError("Der Prüfungsslot kann nicht erneut gestartet werden")
                if requested and started_at != requested:
                    raise ValueError(f"Prüfungsstart wurde bereits um {started_at} erfasst")
                work.ensure_started_protocol(
                    slot_id,
                    participant_member_ids=participant_ids,
                    actor_member_id=actor_member_id,
                    started_at=started_at,
                )
                return dict(slot)
            if requested is None:
                requested = self._clock()
            if not isinstance(requested, str) or not requested.strip():
                raise ValueError("Tatsächlicher Startzeitpunkt ist erforderlich")
            return dict(
                work.start_slot(
                    day_id,
                    slot_id,
                    started_at=requested,
                    participant_member_ids=participant_ids,
                    actor_member_id=actor_member_id,
                    expected_day_revision=command.get("expected_day_revision"),
                )
            )

    def update_slot_status(
        self,
        day_id: int,
        slot_id: int,
        command: SlotStatusCommand,
        *,
        actor_member_id: int,
    ) -> dict[str, Any]:
        with self._unit_of_work_factory(write=True) as work:
            slot = work.confirmed_slot(day_id, slot_id)
            correction_mode = work.day_execution_state(day_id)["closure_status"] == "reopening"
            target_status = command.get("status")
            if not isinstance(target_status, str) or target_status not in EXECUTION_STATUS_VALUES:
                raise ValueError("Unbekannter Durchführungsstatus")
            reason = self._slot_status_reason(slot, command, target_status)
            changed_at = self._clock()
            actual_started_at = slot["actual_started_at"]
            actual_completed_at = slot["actual_completed_at"]
            if correction_mode:
                actual_started_at = cast(
                    str | None, command.get("actual_started_at", actual_started_at)
                )
                actual_completed_at = cast(
                    str | None, command.get("actual_completed_at", actual_completed_at)
                )
                self._validate_corrected_slot_facts(
                    target_status, actual_started_at, actual_completed_at
                )
            elif target_status == "completed":
                actual_completed_at = changed_at
            if self._slot_status_is_unchanged(
                slot,
                target_status,
                reason,
                actual_started_at,
                actual_completed_at,
            ):
                return dict(slot)
            work.assert_slot_status_mutable(
                day_id,
                slot_id,
                actor_member_id=actor_member_id,
                expected_day_revision=command.get("expected_day_revision"),
            )
            self._validate_slot_status_transition(slot, target_status, correction_mode)
            return dict(
                work.update_slot_status(
                    day_id,
                    slot_id,
                    status=target_status,
                    changed_at=changed_at,
                    reason=reason,
                    actual_started_at=actual_started_at,
                    actual_completed_at=actual_completed_at,
                    actor_member_id=actor_member_id,
                    expected_day_revision=command.get("expected_day_revision"),
                )
            )

    @staticmethod
    def _attendance_values(
        command: AttendanceCommand, existing: Mapping[str, Any] | None
    ) -> AttendanceValues:
        status = command.get("status")
        if not isinstance(status, str) or status not in ATTENDANCE_VALUES:
            raise ValueError("Unbekannter Anwesenheitsstatus")
        arrived_at = command.get("arrived_at", existing.get("arrived_at") if existing else None)
        if status in {"open", "absent"}:
            arrived_at = None
        elif status == "late" and (not isinstance(arrived_at, str) or not arrived_at.strip()):
            raise ValueError("Für verspätete Personen ist die Ankunftszeit erforderlich")
        return {"status": status, "arrived_at": cast(str | None, arrived_at)}

    @staticmethod
    def _validate_startable_slot(slot: SlotSnapshot) -> None:
        if slot["execution_status"] not in {"open", "running"}:
            raise ValueError(
                "Ein abgeschlossener oder ausgefallener Prüfungsslot kann nicht gestartet werden"
            )
        if slot["execution_status"] == "running" and slot["actual_started_at"] is None:
            raise ValueError("Der laufende Prüfungsslot hat keinen tatsächlichen Startzeitpunkt")

    @staticmethod
    def _slot_status_reason(
        slot: SlotSnapshot, command: SlotStatusCommand, target_status: str
    ) -> str | None:
        if target_status not in {"cancelled", "needs_follow_up"}:
            return slot["status_reason"]
        reason = command.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                "Für einen Ausfall oder eine Nachbereitung ist eine Begründung erforderlich"
            )
        return reason.strip()

    @staticmethod
    def _slot_status_is_unchanged(
        slot: SlotSnapshot,
        target_status: str,
        reason: str | None,
        actual_started_at: Any,
        actual_completed_at: Any,
    ) -> bool:
        return (
            target_status == slot["execution_status"]
            and reason == slot["status_reason"]
            and actual_started_at == slot["actual_started_at"]
            and actual_completed_at == slot["actual_completed_at"]
        )

    @staticmethod
    def _validate_slot_status_transition(
        slot: SlotSnapshot,
        target_status: str,
        correction_mode: bool,
    ) -> None:
        if target_status == "running" and not correction_mode:
            raise ValueError("Der Status Läuft wird ausschließlich durch die Startaktion gesetzt")
        if (
            not correction_mode
            and target_status == "cancelled"
            and slot["actual_started_at"] is not None
        ):
            raise ValueError(
                "Ein gestarteter Prüfungsslot kann nicht als ausgefallen markiert werden"
            )
        allowed = EXECUTION_STATUS_TRANSITIONS.get(slot["execution_status"], set())
        if not correction_mode and target_status not in allowed:
            raise ValueError(
                f"Der Statuswechsel von {slot['execution_status']} "
                f"zu {target_status} ist nicht erlaubt"
            )

    @staticmethod
    def _validate_corrected_slot_facts(
        target_status: str,
        actual_started_at: Any,
        actual_completed_at: Any,
    ) -> None:
        def parsed(value: Any, label: str) -> datetime | None:
            if value is None:
                return None
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} ist ungültig")
            try:
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(f"{label} ist ungültig") from error
            if result.tzinfo is None:
                raise ValueError(f"{label} benötigt eine Zeitzone")
            return result

        started = parsed(actual_started_at, "Tatsächlicher Beginn")
        completed = parsed(actual_completed_at, "Tatsächliches Ende")
        if target_status == "completed" and (started is None or completed is None):
            raise ValueError(
                "Ein korrigierter abgeschlossener Slot benötigt tatsächlichen Beginn und Ende"
            )
        if target_status in {"open", "cancelled"} and (
            started is not None or completed is not None
        ):
            raise ValueError(
                "Ein offener oder ausgefallener Slot darf keine tatsächlichen Zeiten enthalten"
            )
        if target_status in {"running", "needs_follow_up"} and started is None:
            raise ValueError("Ein begonnener Slot benötigt einen tatsächlichen Beginn")
        if started is not None and completed is not None and completed <= started:
            raise ValueError("Das tatsächliche Ende muss nach dem tatsächlichen Beginn liegen")

    @staticmethod
    def _assignment_applies_to_slot(assignment: Mapping[str, Any], slot: SlotSnapshot) -> bool:
        day_part = assignment["day_part"]
        if day_part == "full_day":
            return True
        try:
            start = datetime.fromisoformat(slot["starts_at"].replace(" ", "T"))
        except TypeError, ValueError:
            return True
        return (day_part == "morning" and start.hour < 12) or (
            day_part == "afternoon" and start.hour >= 12
        )
