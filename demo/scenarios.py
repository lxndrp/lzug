"""Canonical relative seed and derived progress for public demo scenarios."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.calendar import CalendarService
from backend.database import session_scope
from backend.models import (
    AbsenceReport,
    CandidateExamDay,
    CommitteeMember,
    ConfirmedPlanRevision,
    ExamDay,
    ExamDayAssignment,
    ExamHalfYear,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    ReplacementResponse,
    RoundCandidate,
    UserAccount,
)
from backend.planning import PlanningService

from .runtime_contract import DEMO_MATRIX_VERSION, DISPLAY_NAMES, FIXTURE_IDS

TIME_ZONE = ZoneInfo("Europe/Berlin")
ROUND_ID = 1
DEMO_SCENARIO_ID_BASE = 487_000
ABSENCE_DAY_ID = DEMO_SCENARIO_ID_BASE + 1
PLAN_CHANGE_DAY_ID = DEMO_SCENARIO_ID_BASE + 2
ABSENCE_SLOT_START_ID = DEMO_SCENARIO_ID_BASE + 101
PLAN_CHANGE_SLOT_START_ID = DEMO_SCENARIO_ID_BASE + 103
ABSENCE_ASSIGNMENT_START_ID = DEMO_SCENARIO_ID_BASE + 201
PLAN_CHANGE_ASSIGNMENT_START_ID = DEMO_SCENARIO_ID_BASE + 205
ABSENCE_ASSIGNMENT_ID = ABSENCE_ASSIGNMENT_START_ID + 1
PLAN_CHANGE_ASSIGNMENT_ID = PLAN_CHANGE_ASSIGNMENT_START_ID + 1
PLAN_CHANGE_REASON = "Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung"


def fixture_id(key: str) -> int:
    value = FIXTURE_IDS[f"name.papaspyrou.repertoire.lzug.fixture.{key}"].get("id")
    if not isinstance(value, int):
        raise RuntimeError(f"Fixture has no technical id: {key}")
    return value


CHAIR_MEMBER_ID = fixture_id("membership.chair.athen")
EXAMINER_MEMBER_ID = fixture_id("membership.examiner.absent")
REPLACEMENT_MEMBER_ID = fixture_id("membership.examiner.replacement")
PLAN_REPLACEMENT_MEMBER_ID = REPLACEMENT_MEMBER_ID
WRONG_SIDE_MEMBER_ID = fixture_id("membership.examiner.unsuitable")
SOURCE_LOCATION_ID = fixture_id("room.zappeion.theseus")
TARGET_LOCATION_ID = fixture_id("room.gazi.handwerkerensemble")


def seed_demo_scenarios(db_path: Path, created_at: datetime) -> None:
    """Create two valid, independent confirmed-plan examples using only ORM models."""
    current = created_at.astimezone(UTC)
    absence_date = _closest_relative_exam_date(current)
    plan_date = absence_date + timedelta(days=8)
    stamp = current.isoformat(timespec="seconds")

    with session_scope(db_path) as session:
        _assert_fixture_contract(session)
        if (
            session.scalar(select(ExamDay.id).where(ExamDay.exam_round_id == ROUND_ID).limit(1))
            is not None
        ):
            raise RuntimeError("Demo scenario round must start without exam days")

        half_year = session.get(ExamHalfYear, 1)
        exam_round = session.get(ExamRound, ROUND_ID)
        if half_year is None or exam_round is None:
            raise RuntimeError("Demo exam context is incomplete")
        half_year.year = absence_date.year
        half_year.season = "summer" if absence_date.month < 8 else "winter"
        half_year.status = "active"
        exam_round.name = f"Demo-Prüfungsrunde {absence_date.year}"
        exam_round.status = "plan_confirmed"
        exam_round.plan_revision = 1
        exam_round.availability_deadline = stamp
        exam_round.availability_reminder_at = stamp

        candidate_days = list(
            session.scalars(
                select(CandidateExamDay)
                .where(CandidateExamDay.exam_round_id == ROUND_ID)
                .order_by(CandidateExamDay.id)
            )
        )
        if len(candidate_days) < 2:
            raise RuntimeError("Demo candidate-day fixture is incomplete")
        candidate_days[0].date = absence_date.isoformat()
        candidate_days[1].date = plan_date.isoformat()
        for index, candidate_day in enumerate(candidate_days):
            candidate_day.is_active = int(index < 2)

        for candidate in session.scalars(
            select(RoundCandidate).where(RoundCandidate.exam_round_id == ROUND_ID)
        ):
            candidate.is_active = int(candidate.id in {1, 2, 3, 4, 5, 6})
            candidate.requires_mep = int(candidate.id == 2)

        active_day_ids = {candidate_days[0].id, candidate_days[1].id}
        for availability in session.scalars(
            select(MemberAvailability).where(MemberAvailability.exam_round_id == ROUND_ID)
        ):
            if availability.candidate_exam_day_id in active_day_ids:
                availability.availability = "full_day"
                availability.responded_at = stamp

        absence_day = ExamDay(
            id=ABSENCE_DAY_ID,
            exam_round_id=ROUND_ID,
            room_id=SOURCE_LOCATION_ID,
            date=absence_date.isoformat(),
            status="confirmed",
            lunch_break_enabled=1,
            revision=1,
        )
        plan_day = ExamDay(
            id=PLAN_CHANGE_DAY_ID,
            exam_round_id=ROUND_ID,
            room_id=SOURCE_LOCATION_ID,
            date=plan_date.isoformat(),
            status="confirmed",
            lunch_break_enabled=1,
            revision=1,
        )
        session.add_all((absence_day, plan_day))
        session.flush()

        session.add_all(
            _slots(
                ABSENCE_DAY_ID,
                absence_date,
                ((2, "regular"), (2, "mep")),
                start_id=ABSENCE_SLOT_START_ID,
            )
            + _slots(
                PLAN_CHANGE_DAY_ID,
                plan_date,
                ((1, "regular"), (3, "regular"), (4, "regular"), (5, "regular"), (6, "regular")),
                start_id=PLAN_CHANGE_SLOT_START_ID,
            )
        )
        session.add_all(
            [
                ExamDayAssignment(
                    id=ABSENCE_ASSIGNMENT_START_ID,
                    exam_day_id=ABSENCE_DAY_ID,
                    committee_member_id=1,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=ABSENCE_ASSIGNMENT_ID,
                    exam_day_id=ABSENCE_DAY_ID,
                    committee_member_id=3,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=ABSENCE_ASSIGNMENT_START_ID + 2,
                    exam_day_id=ABSENCE_DAY_ID,
                    committee_member_id=2,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=ABSENCE_ASSIGNMENT_START_ID + 3,
                    exam_day_id=ABSENCE_DAY_ID,
                    committee_member_id=5,
                    assignment_role="fallback",
                    day_part="morning",
                    fallback_status="confirmed",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=1,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_ID,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=3,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 2,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=2,
                    assignment_role="examiner",
                    day_part="morning",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 3,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=5,
                    assignment_role="fallback",
                    day_part="morning",
                    fallback_status="confirmed",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 4,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=4,
                    assignment_role="examiner",
                    day_part="afternoon",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 5,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=6,
                    assignment_role="examiner",
                    day_part="afternoon",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 6,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=8,
                    assignment_role="examiner",
                    day_part="afternoon",
                ),
                ExamDayAssignment(
                    id=PLAN_CHANGE_ASSIGNMENT_START_ID + 7,
                    exam_day_id=PLAN_CHANGE_DAY_ID,
                    committee_member_id=7,
                    assignment_role="fallback",
                    day_part="afternoon",
                    fallback_status="confirmed",
                ),
            ]
        )

    CalendarService(db_path, time_zone=TIME_ZONE.key).sync_round(ROUND_ID)
    PlanningService(db_path).get_confirmed_plan(ROUND_ID)


def scenario_overview(
    db_path: Path,
    *,
    role: str,
    created_at: datetime,
    expires_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    """Derive presentation progress exclusively from persisted domain state."""
    with session_scope(db_path) as session:
        report = session.scalar(
            select(AbsenceReport).where(AbsenceReport.exam_day_id == ABSENCE_DAY_ID)
        )
        response = (
            session.scalar(
                select(ReplacementResponse).where(
                    ReplacementResponse.absence_report_id == report.id,
                    ReplacementResponse.committee_member_id == REPLACEMENT_MEMBER_ID,
                )
            )
            if report is not None
            else None
        )
        revision = session.scalar(
            select(ConfirmedPlanRevision)
            .where(ConfirmedPlanRevision.exam_round_id == ROUND_ID)
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
            f"/confirmed-plans/{ROUND_ID}/days/{ABSENCE_DAY_ID}",
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
        "/notifications" if has_revision else f"/confirmed-plans/{ROUND_ID}/edit",
        complete=has_revision,
    )
    return {
        "mode": "demo",
        "demo_matrix_version": DEMO_MATRIX_VERSION,
        "current_role": role,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "remaining_seconds": max(0, int((expires_at - now.astimezone(UTC)).total_seconds())),
        "roles": [
            {
                "name": name,
                "display_name": display_name,
                "task": task,
            }
            for name, display_name, task in (
                ("chair", _display("person.chair.athen"), "Koordination und Planrevision"),
                ("examiner", _display("person.examiner.absent"), "Eigenen Ausfall melden"),
                (
                    "replacement",
                    _display("person.examiner.replacement"),
                    "Eigene Ersatzanfrage beantworten",
                ),
            )
        ],
        "scenarios": [absence, plan_change],
        "prepared_plan_change": {
            "round_id": ROUND_ID,
            "day_id": PLAN_CHANGE_DAY_ID,
            "source_location_id": SOURCE_LOCATION_ID,
            "target_location_id": TARGET_LOCATION_ID,
            "assignment_id": PLAN_CHANGE_ASSIGNMENT_ID,
            "replacement_member_id": PLAN_REPLACEMENT_MEMBER_ID,
            "reason": PLAN_CHANGE_REASON,
        },
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


def expected_plan_change(db_path: Path) -> dict[str, Any]:
    """Return the single complete aggregate accepted by the demo allowlist."""
    service = PlanningService(db_path)
    payload = deepcopy(service.confirmed_plan_payload(service.get_confirmed_plan(ROUND_ID)))
    for day in payload["exam_days"]:
        day["location_id"] = day["room_id"]
    target_day = next(day for day in payload["exam_days"] if day["id"] == PLAN_CHANGE_DAY_ID)
    target_day["room_id"] = TARGET_LOCATION_ID
    target_day["location_id"] = TARGET_LOCATION_ID
    target_assignment = next(
        assignment
        for assignment in target_day["assignments"]
        if assignment["id"] == PLAN_CHANGE_ASSIGNMENT_ID
    )
    target_assignment["committee_member_id"] = PLAN_REPLACEMENT_MEMBER_ID
    return {**payload, "reason": PLAN_CHANGE_REASON}


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


def _assert_fixture_contract(session) -> None:
    expected = {
        1: ("employer", "chair"),
        2: ("school", "deputy_chair"),
        3: ("employee", "member"),
        6: ("employee", "member"),
        7: ("employer", "member"),
        8: ("school", "member"),
    }
    for member_id, (side, role) in expected.items():
        member = session.get(CommitteeMember, member_id)
        if (
            member is None
            or member.committee_id != 1
            or member.representing_side != side
            or member.committee_role != role
            or not member.is_active
        ):
            raise RuntimeError("Demo committee fixture does not match the scenario matrix")
    replacement_account = session.get(UserAccount, 4)
    if replacement_account is None or replacement_account.person_id != 6:
        raise RuntimeError("Demo replacement account is unavailable")


def _closest_relative_exam_date(current: datetime) -> date:
    local_now = current.astimezone(TIME_ZONE)
    candidates = [
        datetime.combine(local_now.date() + timedelta(days=days), time(8, 30), TIME_ZONE)
        for days in (1, 2)
    ]
    future = [candidate for candidate in candidates if candidate.astimezone(UTC) > current]
    return min(
        future,
        key=lambda candidate: abs((candidate.astimezone(UTC) - current) - timedelta(hours=24)),
    ).date()


def _slots(
    day_id: int,
    day: date,
    candidates: tuple[tuple[int, str], ...],
    *,
    start_id: int,
) -> list[ExamSlot]:
    starts = ("08:30", "09:30", "10:30", "11:30", "13:30", "14:30")
    result = []
    for offset, ((candidate_id, slot_type), start) in enumerate(
        zip(candidates, starts[: len(candidates)], strict=True)
    ):
        start_time = datetime.strptime(start, "%H:%M")
        end = (start_time + timedelta(hours=1)).strftime("%H:%M")
        result.append(
            ExamSlot(
                id=start_id + offset,
                exam_day_id=day_id,
                round_candidate_id=candidate_id,
                slot_type=slot_type,
                starts_at=f"{day.isoformat()} {start}:00",
                ends_at=f"{day.isoformat()} {end}:00",
                sequence_number=offset + 1,
                status="confirmed",
            )
        )
    return result


def _display(key: str) -> str:
    return DISPLAY_NAMES[f"name.papaspyrou.repertoire.lzug.fixture.{key}"]
