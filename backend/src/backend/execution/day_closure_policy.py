"""Pure closure readiness rules over detached owner facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.execution.lifecycle_ports import (
    DayClosureFacts,
    PlanAssignmentLifecycleSnapshot,
    PlanSlotLifecycleSnapshot,
)
from backend.execution.protocol_ports import ExecutionProtocolSnapshot, ProtocolDaySnapshot
from backend.identity.lifecycle_ports import IdentityMemberLifecycleSnapshot

TERMINAL_SLOT_STATUSES = {"completed", "cancelled"}
TERMINAL_ABSENCE_STATUSES = {
    "replacement_selected",
    "resolved",
    "withdrawn",
    "exam_day_cancelled",
}
COMPLETE_PROTOCOL_STATES = {"fully_confirmed", "fully_with_reservation"}


@dataclass(frozen=True)
class ExamDayClosureSnapshot:
    """Bounded detached input for one closure checklist evaluation."""

    slots: tuple[PlanSlotLifecycleSnapshot, ...]
    candidate_attendance: dict[int, str]
    assignments: tuple[PlanAssignmentLifecycleSnapshot, ...]
    member_attendance: dict[int, str]
    members: dict[int, IdentityMemberLifecycleSnapshot]
    absences: tuple[tuple[int, str], ...]


class ExamDayClosurePolicy:
    """Compute readiness findings without persistence, transport, or notifications."""

    def _evaluate(self, facts: DayClosureFacts, day_id: int) -> dict[str, Any]:
        snapshot = self._load_closure_snapshot(facts)
        items: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        protocol_references: list[dict[str, Any]] = []
        result_references: list[dict[str, Any]] = []
        self._evaluate_slot_execution(snapshot, items)
        self._evaluate_staffing(snapshot, items)
        self._evaluate_absence_processes(snapshot, items)
        if facts.protocol_day_snapshot is None:
            raise RuntimeError("Protocol day snapshot is required for closure evaluation")
        exception_candidates = self._evaluate_protocols(
            snapshot.slots,
            items,
            warnings,
            protocol_references,
            protocol_day_snapshot=facts.protocol_day_snapshot,
        )
        self._evaluate_results(
            day_id,
            snapshot.slots,
            items,
            result_references,
            facts.assessment_completion,
        )

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

    @staticmethod
    def _load_closure_snapshot(
        facts: DayClosureFacts,
    ) -> ExamDayClosureSnapshot:
        slots = facts.slots
        plan_assignments = facts.assignments
        member_values = facts.members
        members = {member.id: member for member in member_values}
        slots = tuple(slots)
        assignments = tuple(item for item in plan_assignments if item.assignment_role == "examiner")
        candidate_attendance = {
            slot_id: item["status"] for slot_id, item in facts.candidate_attendance.items()
        }
        member_attendance = {
            member_id: item["status"] for member_id, item in facts.member_attendance.items()
        }
        absences = tuple((item["id"], item["status"]) for item in facts.absences)
        return ExamDayClosureSnapshot(
            slots=slots,
            candidate_attendance=candidate_attendance,
            assignments=assignments,
            member_attendance=member_attendance,
            members=members,
            absences=absences,
        )

    def _evaluate_slot_execution(
        self, snapshot: ExamDayClosureSnapshot, items: list[dict[str, Any]]
    ) -> None:
        slots = snapshot.slots
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
        missing_attendance = self._missing_candidate_attendance(snapshot)
        self._finding(
            items,
            "candidate_attendance_complete",
            "Anwesenheit der Prüflinge ist vollständig",
            not missing_attendance,
            missing_attendance,
        )

    @staticmethod
    def _missing_candidate_attendance(snapshot: ExamDayClosureSnapshot) -> list[int]:
        missing: list[int] = []
        for slot in snapshot.slots:
            if slot.execution_status != "completed":
                continue
            attendance = snapshot.candidate_attendance.get(slot.id)
            if attendance not in {"present", "late"}:
                missing.append(slot.id)
        return missing

    def _evaluate_staffing(
        self, snapshot: ExamDayClosureSnapshot, items: list[dict[str, Any]]
    ) -> None:
        open_attendance, invalid_staffing = self._staffing_findings(snapshot)
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
        snapshot: ExamDayClosureSnapshot,
    ) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
        open_attendance: list[dict[str, int]] = []
        invalid_staffing: list[dict[str, Any]] = []
        for slot in (item for item in snapshot.slots if item.execution_status == "completed"):
            present_members = self._present_members(snapshot, slot, open_attendance)
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
        snapshot: ExamDayClosureSnapshot,
        slot: PlanSlotLifecycleSnapshot,
        open_attendance: list[dict[str, int]],
    ) -> list[IdentityMemberLifecycleSnapshot]:
        present_members: list[IdentityMemberLifecycleSnapshot] = []
        for assignment in snapshot.assignments:
            if not self._assignment_applies_to_slot(assignment, slot):
                continue
            attendance = snapshot.member_attendance.get(assignment.committee_member_id)
            if attendance not in {"present", "late"}:
                open_attendance.append(
                    {"exam_slot_id": slot.id, "committee_member_id": assignment.committee_member_id}
                )
                continue
            member = snapshot.members.get(assignment.committee_member_id)
            if member is not None and member.is_active == 1:
                present_members.append(member)
        return present_members

    def _evaluate_absence_processes(
        self, snapshot: ExamDayClosureSnapshot, items: list[dict[str, Any]]
    ) -> None:
        open_absences = [
            item_id
            for item_id, status in snapshot.absences
            if status not in TERMINAL_ABSENCE_STATUSES
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
        slots: Sequence[PlanSlotLifecycleSnapshot],
        items: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        references: list[dict[str, Any]],
        *,
        protocol_day_snapshot: ProtocolDaySnapshot,
    ) -> list[dict[str, Any]]:
        regular_ready = True
        exception_ready = True
        candidates: list[dict[str, Any]] = []
        protocols_by_slot = {
            item["exam_slot_id"]: item["protocol"] for item in protocol_day_snapshot["slots"]
        }
        for slot in slots:
            regular, exception, candidate = self._evaluate_slot_protocol_snapshot(
                slot, protocols_by_slot.get(slot.id), warnings, references
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

    def _evaluate_slot_protocol_snapshot(
        self,
        slot: PlanSlotLifecycleSnapshot,
        protocol: ExecutionProtocolSnapshot | None,
        warnings: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> tuple[bool, bool, dict[str, Any] | None]:
        if slot.execution_status == "cancelled":
            return True, False, None
        if protocol is None:
            references.append(
                {"exam_slot_id": slot.id, "exam_protocol_id": None, "state": "missing"}
            )
            return False, False, None
        revision = next(
            (
                item
                for item in protocol["revisions"]
                if item["version"] == protocol["current_version"]
            ),
            None,
        )
        if revision is None:
            raise ValueError("Der aktuelle Protokollstand fehlt")
        responses = list(revision["responses"])
        participants = set(protocol["participants"])
        missing = sorted(participants - {item["committee_member_id"] for item in responses})
        state = self._protocol_snapshot_state(revision, responses, missing)
        regular = (
            state in COMPLETE_PROTOCOL_STATES and revision["workflow_state"] != "correction_open"
        )
        candidate = None
        if (
            state == "reaction_missing"
            and len(missing) == 1
            and revision["declaration"] is not None
            and revision["workflow_state"] != "correction_open"
        ):
            candidate = {
                "exam_slot_id": slot.id,
                "exam_protocol_id": protocol["id"],
                "exam_protocol_revision_id": revision["id"],
                "protocol_version": revision["version"],
                "committee_member_id": missing[0],
            }
        reservations = [
            {"committee_member_id": item["committee_member_id"], "statement": item["statement"]}
            for item in responses
            if item["response"] == "reservation"
        ]
        if revision["entries"] or reservations:
            warnings.append(
                {
                    "exam_protocol_id": protocol["id"],
                    "entries": [
                        {"category": item["category"], "statement": item["statement"]}
                        for item in revision["entries"]
                    ],
                    "reservations": reservations,
                }
            )
        references.append(
            {
                "exam_slot_id": slot.id,
                "exam_protocol_id": protocol["id"],
                "revision_id": revision["id"],
                "version": revision["version"],
                "state": state,
                "missing_response_member_ids": missing,
            }
        )
        return regular, candidate is not None, candidate

    @staticmethod
    def _protocol_snapshot_state(revision, responses, missing: list[int]) -> str:
        if revision["submitted_at"] is None:
            return (
                "correction_open"
                if revision["workflow_state"] == "correction_open"
                else "in_progress"
            )
        if not responses:
            return "awaiting_confirmation"
        if missing:
            return "reaction_missing"
        return (
            "fully_with_reservation"
            if any(item["response"] == "reservation" for item in responses)
            else "fully_confirmed"
        )

    def _evaluate_results(
        self,
        day_id: int,
        slots: Sequence[PlanSlotLifecycleSnapshot],
        items: list[dict[str, Any]],
        references: list[dict[str, Any]],
        completion: Mapping[str, Any],
    ) -> None:
        by_slot = {item["exam_slot_id"]: item for item in completion["slots"]}
        for slot in slots:
            references.append(
                by_slot.get(
                    slot.id,
                    self._no_result_completion(slot, "missing", False),
                )
            )
        result_ready = all(item["regular_close_ready"] for item in references)
        self._finding(
            items,
            "results_complete",
            "Tagesbewertungen sind abgeschlossen und berechnungsbereite Ergebnisse festgestellt",
            result_ready,
            [item for item in references if not item["regular_close_ready"]],
        )

    @staticmethod
    def _no_result_completion(
        slot: PlanSlotLifecycleSnapshot, state: str, ready: bool
    ) -> dict[str, Any]:
        return {
            "exam_slot_id": slot.id,
            "exam_result_id": None,
            "state": state,
            "regular_close_ready": ready,
            "external_inputs_pending": [],
        }

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
    def _assignment_applies_to_slot(
        assignment: PlanAssignmentLifecycleSnapshot, slot: PlanSlotLifecycleSnapshot
    ) -> bool:
        if assignment.day_part == "full_day":
            return True
        try:
            start = datetime.fromisoformat(slot.starts_at.replace(" ", "T"))
        except TypeError, ValueError:
            return True
        return (assignment.day_part == "morning" and start.hour < 12) or (
            assignment.day_part == "afternoon" and start.hour >= 12
        )


_POLICY = ExamDayClosurePolicy()


def evaluate_day_closure(facts: DayClosureFacts, day_id: int) -> dict[str, Any]:
    """Evaluate regular and exception closure readiness from detached facts."""
    return _POLICY._evaluate(facts, day_id)


def day_closure_view(scope, facts: DayClosureFacts, read_snapshot):
    """Render a day closure view from detached facts and a detached read snapshot."""
    if read_snapshot is None:
        return None
    committee_id = facts.committee_id
    if not scope.can_read_committee(committee_id):
        raise PermissionError("Forbidden.")
    day = read_snapshot.day
    day_id = day["id"]
    if not isinstance(day_id, int):
        raise TypeError("Day read snapshot id must be an integer")
    evaluation = evaluate_day_closure(facts, day_id)
    actor_id = scope.member_for_committee(committee_id)
    history = [dict(item) for item in read_snapshot.history]
    return {
        "exam_day_id": day["id"],
        "revision": day["revision"],
        "status": day["closure_status"],
        "legacy_status": day["status"] if day["closure_status"] == "historical" else None,
        "evaluation": evaluation,
        "active_reopening": next(
            (item for item in history if item["kind"] == "reopening" and item["status"] == "open"),
            None,
        ),
        "history": history,
        "tasks": [dict(item) for item in read_snapshot.tasks],
        "permissions": {
            "close": scope.can_manage_committee(committee_id)
            and day["closure_status"] in {"open", "reopening"},
            "reopen": scope.can_manage_committee(committee_id)
            and day["closure_status"] in {"closed", "closed_exception", "historical"},
            "export": actor_id is not None,
        },
    }
