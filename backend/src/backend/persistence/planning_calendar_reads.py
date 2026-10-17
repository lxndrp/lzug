"""SQLite read adapters for Planning calendar projections."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from sqlalchemy.orm import Session

from backend.identity.authorization import AuthorizationScope
from backend.identity.calendar_reads import IdentityCalendarMember
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_EXAM_ATTENDANCE,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROOM,
    EXAM_ROUND,
    EXAM_SLOT,
    EXAM_VENUE,
    MEMBER_EXAM_ATTENDANCE,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.persistence.store import Store

if TYPE_CHECKING:
    from backend.application.planning_calendar_reads import (
        ClosureCalendarRead,
        ExecutionCalendarQueries,
        IdentityCalendarQueries,
        PlanningCalendarQueries,
        PlanningCalendarReadUnitOfWork,
    )
    from backend.planning.calendar_reads import (
        PlanningCalendarAssignment,
        PlanningCalendarDay,
        PlanningCalendarRecord,
        PlanningCalendarSlot,
        PlanningConfirmedPlan,
    )


ClosureView = Callable[[Session, int, AuthorizationScope], dict[str, Any] | None]


class _SQLiteCalendarRecord(NamedTuple):
    values: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.values)


class _SQLiteCalendarSlot(NamedTuple):
    slot: PlanningCalendarRecord
    candidate: PlanningCalendarRecord | None


class _SQLiteCalendarAssignment(NamedTuple):
    assignment: PlanningCalendarRecord
    member_id: int


class _SQLiteCalendarDay(NamedTuple):
    day: PlanningCalendarRecord
    room: PlanningCalendarRecord | None
    venue: PlanningCalendarRecord | None
    slots: tuple[PlanningCalendarSlot, ...]
    assignments: tuple[PlanningCalendarAssignment, ...]


class _SQLiteConfirmedPlan(NamedTuple):
    exam_round: PlanningCalendarRecord
    half_year: PlanningCalendarRecord | None
    days: tuple[PlanningCalendarDay, ...]


class SQLitePlanningCalendarReadUnitOfWorkFactory:
    """Bind Planning, Identity, and Execution query adapters to one read session."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        closure_view: ClosureView,
    ) -> None:
        self.db_path = Path(db_path)
        self._closure_view = closure_view

    def __call__(self) -> AbstractContextManager[PlanningCalendarReadUnitOfWork]:
        return self._unit_of_work()

    @contextmanager
    def _unit_of_work(self) -> Iterator[PlanningCalendarReadUnitOfWork]:
        with read_session_scope(self.db_path) as session:
            yield SQLitePlanningCalendarReadUnitOfWork(session, self._closure_view)


class SQLitePlanningCalendarReadUnitOfWork:
    """Domain-owned read adapters sharing one SQLite snapshot."""

    def __init__(self, session: Session, closure_view: ClosureView) -> None:
        self._session = session
        self._closure_view = closure_view
        self.planning: PlanningCalendarQueries = _SQLitePlanningCalendarQueries(session)
        self.identity: IdentityCalendarQueries = _SQLiteIdentityCalendarQueries(session)
        self.execution: ExecutionCalendarQueries = _SQLiteExecutionCalendarQueries(session)

    def closure_view(self, day_id: int, scope: AuthorizationScope) -> ClosureCalendarRead | None:
        view = self._closure_view(self._session, day_id, scope)
        return cast("ClosureCalendarRead | None", view)


class _SQLitePlanningCalendarQueries:
    """Planning-owned rows materialized within the caller's read session."""

    def __init__(self, session: Session) -> None:
        self._store = Store(session)

    def scheduling_rounds(self, committee_ids: frozenset[int]):
        half_years = {row["id"]: row for row in self._store.all(EXAM_HALF_YEAR)}
        settings = {row["exam_round_id"]: row for row in self._store.all(PLANNING_SETTINGS)}
        return tuple(
            (
                _SQLiteCalendarRecord(
                    self._select(
                        row,
                        ("id", "name", "status", "committee_id", "exam_half_year_id"),
                    )
                ),
                (
                    _SQLiteCalendarRecord(half_years[row["exam_half_year_id"]])
                    if row.get("exam_half_year_id") in half_years
                    else None
                ),
                (
                    _SQLiteCalendarRecord(
                        self._select(
                            settings[row["id"]], ("calendar_week_from", "calendar_week_to")
                        )
                    )
                    if row["id"] in settings
                    else None
                ),
            )
            for row in self._store.all(EXAM_ROUND)
            if row["committee_id"] in committee_ids
        )

    @staticmethod
    def _select(row: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: row[key] for key in keys}

    def confirmed_plans(self, committee_ids: frozenset[int]) -> tuple[PlanningConfirmedPlan, ...]:
        exam_rounds = [
            row
            for row in self._store.where(EXAM_ROUND, status="plan_confirmed")
            if row["committee_id"] in committee_ids
        ]
        return self._plans(exam_rounds)

    def confirmed_plan(
        self, day_id: int, committee_ids: frozenset[int]
    ) -> PlanningConfirmedPlan | None:
        day = self._store.get(EXAM_DAY, day_id)
        if day is None or day["status"] not in {"confirmed", "completed", "cancelled"}:
            return None
        exam_round = self._store.get(EXAM_ROUND, day["exam_round_id"])
        if (
            exam_round is None
            or exam_round["status"] != "plan_confirmed"
            or exam_round["committee_id"] not in committee_ids
        ):
            return None
        return self._plans([exam_round], {day_id})[0]

    def _plans(
        self,
        exam_rounds: list[dict[str, Any]],
        requested_day_ids: set[int] | None = None,
    ) -> tuple[PlanningConfirmedPlan, ...]:
        """Materialize a calendar request's shared context once for all rounds."""
        half_years = {row["id"]: row for row in self._store.all(EXAM_HALF_YEAR)}
        days_by_round: dict[int, list[dict[str, Any]]] = {}
        for row in self._store.all(EXAM_DAY):
            if requested_day_ids is not None and row["id"] not in requested_day_ids:
                continue
            days_by_round.setdefault(row["exam_round_id"], []).append(row)
        slots_by_day: dict[int, list[dict[str, Any]]] = {}
        for row in self._store.all(EXAM_SLOT):
            slots_by_day.setdefault(row["exam_day_id"], []).append(row)
        assignments_by_day: dict[int, list[dict[str, Any]]] = {}
        for row in self._store.all(EXAM_DAY_ASSIGNMENT):
            assignments_by_day.setdefault(row["exam_day_id"], []).append(row)
        calendar_days: list[PlanningCalendarDay] = []
        candidates = {
            row["id"]: {
                key: row[key] for key in ("id", "first_name", "last_name", "ihk_exam_number")
            }
            for row in self._store.all(CANDIDATE)
        }
        round_candidates = {
            row["id"]: row["candidate_id"] for row in self._store.all(ROUND_CANDIDATE)
        }
        rooms = {row["id"]: row for row in self._store.all(EXAM_ROOM)}
        venues = {row["id"]: row for row in self._store.all(EXAM_VENUE)}
        plans = []
        for exam_round in exam_rounds:
            calendar_days = []
            half_year = half_years.get(exam_round["exam_half_year_id"])
            days = sorted(
                days_by_round.get(exam_round["id"], []),
                key=lambda row: (row["date"], row["id"]),
            )
            for day in days:
                if day["status"] not in {"confirmed", "completed", "cancelled"}:
                    continue
                room = rooms.get(day["room_id"])
                venue = venues.get(room["venue_id"]) if room else None
                slots = []
                for slot in sorted(
                    slots_by_day.get(day["id"], []),
                    key=lambda row: (row["starts_at"], row["sequence_number"], row["id"]),
                ):
                    if slot["status"] not in {"confirmed", "completed", "cancelled"}:
                        continue
                    candidate_id = round_candidates.get(slot["round_candidate_id"])
                    candidate = candidates.get(candidate_id) if candidate_id is not None else None
                    slots.append(
                        _SQLiteCalendarSlot(
                            _SQLiteCalendarRecord(
                                {
                                    key: slot[key]
                                    for key in (
                                        "id",
                                        "starts_at",
                                        "ends_at",
                                        "sequence_number",
                                        "slot_type",
                                        "status",
                                    )
                                }
                            ),
                            _SQLiteCalendarRecord(candidate) if candidate else None,
                        )
                    )
                assignments = tuple(
                    _SQLiteCalendarAssignment(
                        _SQLiteCalendarRecord(
                            {
                                key: row[key]
                                for key in (
                                    "id",
                                    "assignment_role",
                                    "day_part",
                                    "fallback_status",
                                )
                            }
                        ),
                        row["committee_member_id"],
                    )
                    for row in assignments_by_day.get(day["id"], [])
                )
                calendar_days.append(
                    _SQLiteCalendarDay(
                        _SQLiteCalendarRecord(
                            {
                                key: day[key]
                                for key in (
                                    "id",
                                    "date",
                                    "revision",
                                    "closure_status",
                                    "room_id",
                                    "status",
                                )
                            }
                        ),
                        (
                            _SQLiteCalendarRecord(
                                {key: room[key] for key in ("id", "name", "venue_id")}
                            )
                            if room
                            else None
                        ),
                        (
                            _SQLiteCalendarRecord(
                                {key: venue[key] for key in ("id", "name", "city")}
                            )
                            if venue
                            else None
                        ),
                        tuple(slots),
                        assignments,
                    )
                )
            plans.append(
                _SQLiteConfirmedPlan(
                    _SQLiteCalendarRecord(
                        {
                            key: exam_round[key]
                            for key in ("id", "name", "committee_id", "exam_half_year_id")
                        }
                    ),
                    _SQLiteCalendarRecord(half_year) if half_year else None,
                    tuple(calendar_days),
                )
            )
        return tuple(plans)


class _SQLiteIdentityCalendarQueries:
    """Identity-owned person and committee projections in the shared snapshot."""

    def __init__(self, session: Session) -> None:
        self._store = Store(session)

    def committees(self, committee_ids: frozenset[int]) -> dict[int, dict[str, Any]]:
        return {
            int(row["id"]): {"id": row["id"], "name": row["name"]}
            for row in self._store.all(COMMITTEE)
            if row["id"] in committee_ids
        }

    def members(self, member_ids: frozenset[int]) -> dict[int, IdentityCalendarMember]:
        result = {}
        for member_id in member_ids:
            membership = self._store.get(COMMITTEE_MEMBER, member_id)
            if membership is None:
                continue
            person = self._store.get(PERSON, membership["person_id"])
            if person is not None:
                result[member_id] = IdentityCalendarMember(
                    {
                        "id": membership["id"],
                        "representing_side": membership["representing_side"],
                    },
                    {"first_name": person["first_name"], "last_name": person["last_name"]},
                )
        return result


class _SQLiteExecutionCalendarQueries:
    """Execution-owned attendance and slot-state projections."""

    def __init__(self, session: Session) -> None:
        self._store = Store(session)

    def day_execution(self, day_ids: frozenset[int]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for day_id in day_ids:
            slots = self._store.where(EXAM_SLOT, exam_day_id=day_id)
            slot_ids = {row["id"] for row in slots}
            candidate_attendance = {
                row["exam_slot_id"]: {"status": row["status"], "arrived_at": row["arrived_at"]}
                for row in self._store.all(CANDIDATE_EXAM_ATTENDANCE)
                if row["exam_slot_id"] in slot_ids
            }
            member_attendance = {
                row["committee_member_id"]: {
                    "status": row["status"],
                    "arrived_at": row["arrived_at"],
                }
                for row in self._store.where(MEMBER_EXAM_ATTENDANCE, exam_day_id=day_id)
            }
            result[day_id] = {
                "slots": {
                    row["id"]: {
                        key: row[key]
                        for key in (
                            "actual_started_at",
                            "execution_status",
                            "status_changed_at",
                            "actual_completed_at",
                            "status_reason",
                        )
                    }
                    for row in slots
                },
                "candidate_attendance": candidate_attendance,
                "member_attendance": member_attendance,
            }
        return result
