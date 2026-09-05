"""Presentation of the declarative public-demo scenarios."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.database import session_scope
from backend.models import AbsenceReport, ConfirmedPlanRevision, ReplacementResponse
from backend.planning import PlanningService

TIME_ZONE = ZoneInfo("Europe/Berlin")


def _scenario(
    identifier: str,
    title: str,
    completed_steps: int,
    total_steps: int,
    next_role: str,
    next_action: str,
    path: str,
    *,
    complete: bool = False,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "status": "complete" if complete else "in_progress" if completed_steps else "ready",
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "next_role": next_role,
        "next_action": next_action,
        "path": path,
    }


def scenario_overview(
    db_path: Path,
    *,
    role: str,
    created_at: datetime,
    expires_at: datetime,
    now: datetime,
    runtime_profile: dict[str, Any],
) -> dict[str, Any]:
    """Derive presentation progress exclusively from persisted domain state."""
    round_id = runtime_profile["round_id"]
    absence_day_id = runtime_profile["absence"]["day_id"]
    replacement_member_id = runtime_profile["roles"]["replacement"]["committee_member_id"]
    plan = runtime_profile["plan_change"]

    with session_scope(db_path) as session:
        report = session.scalar(
            select(AbsenceReport).where(AbsenceReport.exam_day_id == absence_day_id)
        )
        response = (
            session.scalar(
                select(ReplacementResponse).where(
                    ReplacementResponse.absence_report_id == report.id,
                    ReplacementResponse.committee_member_id == replacement_member_id,
                )
            )
            if report is not None
            else None
        )
        revision = session.scalar(
            select(ConfirmedPlanRevision)
            .where(ConfirmedPlanRevision.exam_round_id == round_id)
            .order_by(ConfirmedPlanRevision.resulting_revision.desc())
        )
        report_status = report.status if report is not None else None
        response_value = response.response if response is not None else None
        has_revision = revision is not None

    if report_status is None:
        absence = _scenario(
            "absence",
            "Dringlicher Ausfall und Ersatz",
            0,
            3,
            "examiner",
            "Eigenen Ausfall am vorbereiteten Prüfungstag melden",
            f"/confirmed-plans/{round_id}/days/{absence_day_id}",
        )
    elif response_value in {None, "pending"}:
        absence = _scenario(
            "absence",
            "Dringlicher Ausfall und Ersatz",
            1,
            3,
            "replacement",
            "Eigene Ersatzanfrage mit verfügbar beantworten",
            "/absence-reports",
        )
    elif report_status != "replacement_selected":
        absence = _scenario(
            "absence",
            "Dringlicher Ausfall und Ersatz",
            2,
            3,
            "chair",
            "Verfügbaren Ersatz auswählen",
            "/absence-reports",
        )
    else:
        absence = _scenario(
            "absence",
            "Dringlicher Ausfall und Ersatz",
            3,
            3,
            role,
            "Benachrichtigungs- und Kalenderfolgen ansehen",
            "/notifications",
            complete=True,
        )

    plan_change = _scenario(
        "plan-change",
        "Bestätigte Planänderung",
        int(has_revision),
        1,
        role if has_revision else "chair",
        (
            "Benachrichtigungs- und Kalenderfolgen ansehen"
            if has_revision
            else "Vorbereitete Ortsänderung und Personentausch bestätigen"
        ),
        "/notifications" if has_revision else f"/confirmed-plans/{round_id}/edit",
        complete=has_revision,
    )
    return {
        "mode": "demo",
        "demo_matrix_version": runtime_profile["demo_matrix_version"],
        "current_role": role,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "remaining_seconds": max(0, int((expires_at - now.astimezone(UTC)).total_seconds())),
        "roles": [
            {
                "name": name,
                "display_name": runtime_profile["roles"][name]["display_name"],
                "task": task,
            }
            for name, task in (
                ("chair", "Koordination und Planrevision"),
                ("examiner", "Eigenen Ausfall melden"),
                ("replacement", "Eigene Ersatzanfrage beantworten"),
            )
        ],
        "scenarios": [absence, plan_change],
        "prepared_plan_change": {"round_id": round_id, **plan},
        "notices": [
            "Der Arbeitsstand wird 60 Minuten nach seinem Start verworfen.",
            "Keine realen personenbezogenen Daten eingeben.",
            "Externe Zustellung ist in der öffentlichen Demo deaktiviert.",
        ],
        "location_contract": (
            "Reale Athener Anschriften und Referenzpunkte verorten ausschließlich synthetische "
            "Prüfungsstätten. In Ortsdetails lädt OpenStreetMap automatisch externe "
            "Kartenkacheln; ein Routenlink öffnet den Zielpunkt erst nach bewusster Auswahl."
        ),
    }


def expected_plan_change(db_path: Path, runtime_profile: dict[str, Any]) -> dict[str, Any]:
    """Return the single complete aggregate accepted by the demo allowlist."""
    round_id = runtime_profile["round_id"]
    plan = runtime_profile["plan_change"]
    service = PlanningService(db_path)
    payload = deepcopy(service.confirmed_plan_payload(service.get_confirmed_plan(round_id)))
    for day in payload["exam_days"]:
        day["location_id"] = day["room_id"]
    target_day = next(day for day in payload["exam_days"] if day["id"] == plan["day_id"])
    target_day["room_id"] = plan["target_location_id"]
    target_day["location_id"] = plan["target_location_id"]
    target_assignment = next(
        assignment
        for assignment in target_day["assignments"]
        if assignment["id"] == plan["assignment_id"]
    )
    target_assignment["committee_member_id"] = plan["replacement_member_id"]
    return {**payload, "reason": plan["reason"]}
