"""Pure projection of a detached round lifecycle snapshot for authorized readers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from backend.execution.lifecycle_ports import RoundLifecycleFacts
from backend.execution.round_lifecycle_snapshot import ExamRoundLifecycleReadSnapshot
from backend.identity.authorization import AuthorizationScope

TERMINAL_LIFECYCLE_STATUSES = {"closed", "cancelled", "historical"}
TERMINAL_CANDIDATE_STATUSES = {
    "result_communicated",
    "transferred",
    "postponed",
    "ihk_terminated",
}
TERMINAL_ABSENCE_STATUSES = {
    "replacement_selected",
    "resolved",
    "withdrawn",
    "exam_day_cancelled",
}


def round_lifecycle_view(
    scope: AuthorizationScope,
    facts: RoundLifecycleFacts,
    pending_consequence_ids: Sequence[int],
    snapshot: ExamRoundLifecycleReadSnapshot | None,
) -> dict[str, Any] | None:
    """Render the lifecycle view from detached facts and a detached read projection."""
    if snapshot is None:
        return None
    exam_round = facts.round
    if not scope.can_read_committee(exam_round.committee_id):
        raise PermissionError("Forbidden.")
    actor_id = scope.member_for_committee(exam_round.committee_id)
    records = snapshot.records
    decisions = records["decisions"]
    candidates = facts.round_candidates(exam_round.id)
    days = records["days"]
    formal_day_ids = set(records["current_closure_day_ids"])
    incomplete_days = [
        item["id"]
        for item in days
        if item["closure_status"] not in {"closed", "closed_exception", "historical"}
        or (item["closure_status"] != "historical" and item["id"] not in formal_day_ids)
    ]
    results = facts.results_for_round(exam_round.id)
    open_corrections = [
        correction["id"]
        for result in results
        for correction in result["corrections"]
        if correction["status"] == "open"
    ]
    non_terminal = [item["id"] for item in candidates if item["terminal_status"] == "open"]
    invalid_terminal = [
        item["id"] for item in candidates if not _candidate_terminal_valid(dict(item), facts)
    ]
    open_absences = [
        item["id"]
        for item in records["absences"]
        if item["status"] not in TERMINAL_ABSENCE_STATUSES
    ]
    open_slots = [
        item.id for item in facts.slots if item.execution_status not in {"completed", "cancelled"}
    ]
    evaluation_items = [
        (
            "round_has_confirmed_plan",
            "Die Prüfungsrunde besitzt einen bestätigten oder begonnenen Plan",
            exam_round.status in {"plan_confirmed", "in_progress", "completed"} and bool(days),
            {"planning_status": exam_round.status, "exam_day_count": len(days)},
        ),
        (
            "days_closed",
            "Alle Prüfungstage sind mit Nachweis geschlossen",
            not incomplete_days,
            incomplete_days,
        ),
        (
            "no_day_reopening",
            "Kein Prüfungstag ist wieder geöffnet",
            all(item["closure_status"] != "reopening" for item in days),
            [item["id"] for item in days if item["closure_status"] == "reopening"],
        ),
        (
            "no_protocol_follow_up",
            "Keine Protokoll-Nachfassaufgabe ist offen",
            not records["follow_up_task_ids"],
            list(records["follow_up_task_ids"]),
        ),
        (
            "candidates_terminal",
            "Jeder Prüfling besitzt einen wirksamen terminalen Status",
            not non_terminal and not invalid_terminal,
            sorted(set(non_terminal + invalid_terminal)),
        ),
        (
            "no_corrections",
            "Keine Protokoll-, Bewertungs- oder Ergebniskorrektur ist offen",
            not open_corrections and not records["protocol_correction_ids"],
            open_corrections + list(records["protocol_correction_ids"]),
        ),
        (
            "absence_processes_complete",
            "Alle Ausfall- und Ersatzvorgänge sind abgeschlossen",
            not open_absences,
            open_absences,
        ),
        (
            "slots_terminal",
            "Keine offenen Prüfungsslots verbleiben",
            not open_slots,
            open_slots,
        ),
        (
            "plan_consequences_complete",
            "Alle Planänderungsfolgen sind verarbeitet",
            not pending_consequence_ids,
            tuple(pending_consequence_ids),
        ),
    ]
    items = [
        {"code": code, "label": label, "ok": bool(ok), "details": details}
        for code, label, ok, details in evaluation_items
    ]
    return {
        "round_id": exam_round.id,
        "revision": exam_round.revision,
        "status": exam_round.lifecycle_status,
        "legacy_status": exam_round.legacy_status,
        "historical_without_formal_evidence": exam_round.lifecycle_status == "historical"
        and not decisions,
        "evaluation": {"ready": all(item["ok"] for item in items), "items": items},
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
            for item in candidates
        ],
        "current_decision": next(
            (_decision_mapping(item) for item in decisions if item["status"] == "current"), None
        ),
        "decisions": [_decision_mapping(item) for item in decisions],
        "reopenings": [_reopening_mapping(item) for item in records["reopenings"]],
        "history": [_event_mapping(item) for item in records["history"]],
        "tasks": [_task_mapping(item) for item in records["tasks"]],
        "exports": [_export_mapping(item) for item in records["exports"]],
        "ihk_statuses": [
            {
                "id": item["id"],
                "exam_result_id": item["exam_result_id"],
                "document_status": item["document_status"],
                "document_reference": item["document_reference"],
                "recorded_by_member_id": item["recorded_by_member_id"],
                "recorded_at": item["recorded_at"],
            }
            for item in records["ihk_statuses"]
        ],
        "retention": _retention_mapping(records, results),
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
            "machine_export": {"href": f"/api/exam-rounds/{exam_round.id}/lifecycle/export.json"},
            "human_export": {"href": f"/api/exam-rounds/{exam_round.id}/lifecycle/export.txt"},
        },
    }


def _candidate_terminal_valid(candidate: dict[str, Any], facts: RoundLifecycleFacts) -> bool:
    status = candidate["terminal_status"]
    if status == "result_communicated":
        result = facts.result_for_round_candidate(candidate["id"])
        if result is None or result["state"] != "determined" or result["correction_open"]:
            return False
        determination = next(
            (item for item in result["determinations"] if item["status"] == "current"), None
        )
        communication = next(
            (item for item in result["communications"] if item["status"] == "current"), None
        )
        return (
            determination is not None
            and communication is not None
            and all(item["status"] == "confirmed" for item in result["external_results"])
        )
    if status == "transferred":
        return bool(
            candidate["effective_new_round_id"] is not None
            and candidate["terminal_reason"]
            and not candidate["is_active"]
            and facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"])
            and facts.effective_transfer_exists(
                facts.round.exam_half_year_id,
                candidate["effective_new_round_id"],
                candidate["candidate_id"],
            )
        )
    if status in {"postponed", "ihk_terminated"}:
        has_details = (
            candidate["terminal_reason"] and candidate["postponed_until"]
            if status == "postponed"
            else candidate["terminal_reason"] and candidate["ihk_decision_reference"]
        )
        return bool(
            has_details
            and not candidate["is_active"]
            and facts.original_assignment_ended(candidate["id"], candidate["exam_round_id"])
        )
    return False


def _decision_mapping(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "decision_type": item["decision_type"],
        "requested_revision": item["requested_revision"],
        "resulting_revision": item["resulting_revision"],
        "actor_member_id": item["actor_member_id"],
        "reason": item["reason"],
        "checklist": item["checklist_json"],
        "snapshot": item["snapshot_json"],
        "previous_decision_id": item["previous_decision_id"],
        "status": item["status"],
        "decided_at": item["decided_at"],
    }


def _reopening_mapping(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "requested_revision": item["requested_revision"],
        "resulting_revision": item["resulting_revision"],
        "occasion": item["occasion"],
        "source": item["source"],
        "reason": item["reason"],
        "requested_scope": item["requested_scope_json"],
        "scope": item["scope_json"],
        "impacts": item["impacts_json"],
        "actor_member_id": item["actor_member_id"],
        "status": item["status"],
        "opened_at": item["opened_at"],
        "completed_at": item["completed_at"],
    }


def _event_mapping(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "round_revision": item["round_revision"],
        "event_type": item["event_type"],
        "actor_member_id": item["actor_member_id"],
        "decision_id": item["decision_id"],
        "reopening_id": item["reopening_id"],
        "reason": item["reason"],
        "scope": item["scope_json"],
        "created_at": item["created_at"],
    }


def _task_mapping(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "reopening_id": item["reopening_id"],
        "recipient_member_id": item["recipient_member_id"],
        "task_type": item["task_type"],
        "details": item["details_json"],
        "status": item["status"],
        "created_at": item["created_at"],
        "completed_at": item["completed_at"],
    }


def _export_mapping(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "decision_id": item["decision_id"],
        "round_revision": item["round_revision"],
        "export_kind": item["export_kind"],
        "lifecycle_status": item["lifecycle_status"],
        "generated_by_member_id": item["generated_by_member_id"],
        "generated_at": item["generated_at"],
        "superseded_at": item["superseded_at"],
        "superseded_by_revision": item["superseded_by_revision"],
        "obsolete": item["superseded_at"] is not None,
    }


def _retention_mapping(
    records: dict[str, Any], results: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    sources = list(records["protocol_retention"])
    sources.extend(
        {"kind": "result", "id": item["id"], **item["retention"]}
        for item in results
        if item["retention"] is not None
    )
    values = [item["retain_until"] for item in sources if item["retain_until"] is not None]
    return {
        "retain_until": max(values) if values else None,
        "legal_hold": any(item["legal_hold"] for item in sources),
        "sources": sources,
    }
