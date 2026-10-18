"""Detached validation for candidate terminal lifecycle transitions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from backend.execution.lifecycle_errors import ExamRoundConflictError
from backend.execution.lifecycle_ports import RoundLifecycleFacts
from backend.identity.authorization import AuthorizationScope

TERMINAL_CANDIDATE_STATUSES = {
    "result_communicated",
    "transferred",
    "postponed",
    "ihk_terminated",
}


def candidate_terminal_values(
    scope: AuthorizationScope,
    facts: RoundLifecycleFacts,
    round_candidate_id: int,
    payload: Mapping[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Validate a candidate terminal transition and return Planning-owned values."""
    exam_round = facts.round
    if not scope.can_manage_committee(exam_round.committee_id) or (
        scope.member_for_committee(exam_round.committee_id) is None
    ):
        raise PermissionError("Forbidden.")

    expected_revision = payload.get("revision")
    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 1
    ):
        raise ValueError("Eine aktuelle Rundenrevision ist erforderlich")
    status = payload.get("terminal_status")
    if status not in TERMINAL_CANDIDATE_STATUSES | {"open"}:
        raise ValueError("Unbekannter abschließender Kandidatenstatus")
    if expected_revision != exam_round.revision:
        raise ExamRoundConflictError("Die Prüfungsrunde wurde zwischenzeitlich geändert")

    candidate = next((item for item in facts.candidates if item["id"] == round_candidate_id), None)
    if candidate is None:
        raise ValueError("Prüfling gehört nicht zur Prüfungsrunde")

    reason = _optional_text(payload.get("reason"), 3000)
    target_round_id = payload.get("effective_new_round_id")
    postponed_until = _optional_text(payload.get("postponed_until"), 100)
    ihk_reference = _optional_text(payload.get("ihk_decision_reference"), 1000)
    _validate_terminal_evidence(
        facts,
        exam_round.id,
        exam_round.exam_half_year_id,
        candidate,
        round_candidate_id,
        status,
        reason,
        target_round_id,
        postponed_until,
        ihk_reference,
    )

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    values: dict[str, Any] = {
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
    return expected_revision, {
        "round_id": exam_round.id,
        "round_candidate_id": round_candidate_id,
        "values": values,
        "ended_at": now if ends_assignment else None,
        "change_reason": reason,
    }


def _validate_terminal_evidence(
    facts: RoundLifecycleFacts,
    round_id: int,
    half_year_id: int,
    candidate: Mapping[str, Any],
    round_candidate_id: int,
    status: str,
    reason: str | None,
    target_round_id: Any,
    postponed_until: str | None,
    ihk_reference: str | None,
) -> None:
    _require_terminal_details(status, reason, target_round_id, postponed_until, ihk_reference)
    if status == "result_communicated":
        _require_result_communicated(facts, round_candidate_id)
    elif status == "transferred":
        if not isinstance(target_round_id, int) or isinstance(target_round_id, bool):
            raise ValueError("Ein Ausschusswechsel benötigt eine wirksame neue Runde")
        if target_round_id == round_id or not facts.effective_transfer_exists(
            half_year_id, target_round_id, int(candidate["candidate_id"])
        ):
            raise ValueError("Die neue Zuordnung ist nicht wirksam")


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


def _require_terminal_details(
    status: str,
    reason: str | None,
    target_round_id: Any,
    postponed_until: str | None,
    ihk_reference: str | None,
) -> None:
    if status == "transferred":
        if reason is None or not isinstance(target_round_id, int):
            raise ValueError("Ein Ausschusswechsel benötigt Grund und wirksame neue Runde")
    elif status == "postponed":
        if reason is None or postponed_until is None:
            raise ValueError("Eine Verschiebung benötigt Grund und verbindlichen Termin")
    elif status == "ihk_terminated":
        if reason is None or ihk_reference is None:
            raise ValueError("Die IHK-Entscheidung benötigt Grund und Referenz")


def _require_result_communicated(facts: RoundLifecycleFacts, round_candidate_id: int) -> None:
    result = facts.result_for_round_candidate(round_candidate_id)
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
