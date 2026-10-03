"""SQLite Unit of Work adapter for Planning master-data operations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple, cast

from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWork
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROOM,
    EXAM_ROUND,
    EXAM_VENUE,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.persistence.resource_access import SQLiteResourceAccessQueryFactory
from backend.persistence.store import Store

if TYPE_CHECKING:
    from backend.planning.candidate_days import CandidateDayRecord
    from backend.planning.resources import (
        PlanningBlocker,
        PlanningRecord,
        PlanningResourceUnitOfWork,
        PlanningRoundSummary,
        PlanningSnapshot,
        PlanningValue,
    )

_AVAILABILITY_VALUES = {"full_day", "morning", "afternoon", "unavailable", "pending"}
_GERMAN_SUBDIVISION_CODES = frozenset(
    {
        "DE-BB",
        "DE-BE",
        "DE-BW",
        "DE-BY",
        "DE-HB",
        "DE-HE",
        "DE-HH",
        "DE-MV",
        "DE-NI",
        "DE-NW",
        "DE-RP",
        "DE-SH",
        "DE-SL",
        "DE-SN",
        "DE-ST",
        "DE-TH",
    }
)


class _SQLitePlanningRecord(NamedTuple):
    values: Mapping[str, PlanningValue]

    def as_payload(self) -> dict[str, PlanningValue]:
        return dict(self.values)


class _SQLitePlanningSnapshot(NamedTuple):
    exam_round: PlanningRecord
    half_year: PlanningRecord
    settings: PlanningRecord | None
    candidates: tuple[PlanningRecord, ...]
    members: tuple[PlanningRecord, ...]
    round_candidates: tuple[PlanningRecord, ...]
    candidate_assignments: tuple[PlanningRecord, ...]
    candidate_days: tuple[CandidateDayRecord, ...]
    availabilities: tuple[PlanningRecord, ...]
    blocked_assignments: tuple[PlanningBlocker, ...]


class _SQLitePlanningRoundSummary(NamedTuple):
    round_id: int
    name: str
    status: str
    committee_id: int
    committee_name: str | None
    half_year: Mapping[str, object] | None
    candidate_count: int
    mep_count: int
    settings: PlanningRecord | None
    availability_counts: tuple[PlanningRecord, ...]

    def as_payload(self) -> dict[str, object]:
        return {
            "round": {
                "id": self.round_id,
                "name": self.name,
                "status": self.status,
                "committee_name": self.committee_name,
                "exam_half_year": dict(self.half_year) if self.half_year is not None else None,
            },
            "counts": {
                "candidates": self.candidate_count,
                "mep_count": self.mep_count,
                "required_exam_slots": self.candidate_count + self.mep_count,
            },
            "settings": self.settings.as_payload() if self.settings is not None else None,
            "availability": [row.as_payload() for row in self.availability_counts],
        }


class _SQLitePlanningBlocker(NamedTuple):
    date: str
    day_part: str
    person_id: int
    exam_half_year_id: int
    exam_round_id: int
    exam_day_status: str
    committee_name: str


def _record(values: Mapping[str, object]) -> PlanningRecord:
    """Detach a mapping from persistence and expose it as a read-only record."""
    typed_values = {key: cast("PlanningValue", value) for key, value in values.items()}
    return cast("PlanningRecord", _SQLitePlanningRecord(MappingProxyType(typed_values)))


def _required_id(values: Mapping[str, PlanningValue], field: str) -> int:
    value = values.get(field)
    if value is None:
        raise ValueError(f"Missing required field: {field}")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid identifier: {field}") from error


class SQLitePlanningResourceUnitOfWorkFactory:
    """Open a consistent read snapshot or write-serialized Planning transaction."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        require_confirmed_coordinates: bool = False,
    ) -> None:
        self.db_path = db_path
        self.require_confirmed_coordinates = require_confirmed_coordinates

    def __call__(
        self, *, write: bool = False
    ) -> AbstractContextManager[PlanningResourceUnitOfWork]:
        return self._unit_of_work(write=write)

    @contextmanager
    def _unit_of_work(self, *, write: bool) -> Iterator[PlanningResourceUnitOfWork]:
        transaction = (
            session_scope(self.db_path, begin_immediate=True)
            if write
            else read_session_scope(self.db_path)
        )
        with transaction as session:
            yield SQLitePlanningResourceUnitOfWork(
                Store(session),
                require_confirmed_coordinates=self.require_confirmed_coordinates,
            )


class SQLitePlanningResourceUnitOfWork:
    """Perform use-case-sized Planning operations within one SQLite session."""

    def __init__(self, store: Store, *, require_confirmed_coordinates: bool = False) -> None:
        self._store = store
        self._require_confirmed_coordinates = require_confirmed_coordinates

    def authorization_queries(self) -> object:
        """Bind materialized access queries to the active planning transaction."""
        return SQLiteResourceAccessQueryFactory().for_transaction(self._store)

    def list_half_years(self) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.all(EXAM_HALF_YEAR)))

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None:
        row = self._store.get(EXAM_HALF_YEAR, half_year_id)
        return _record(row) if row is not None else None

    def create_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        normalized = dict(values)
        self._resolve_half_year(normalized)
        self._validate_round_references(normalized)
        self._validate_round(normalized)
        normalized["revision"] = 1
        normalized["lifecycle_status"] = "open"
        return _record(self._store.create(EXAM_ROUND, normalized))

    def list_rounds(self, filters: Mapping[str, PlanningValue]) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.where(EXAM_ROUND, **dict(filters))))

    def get_round(self, round_id: int) -> PlanningRecord | None:
        row = self._store.get(EXAM_ROUND, round_id)
        return _record(row) if row is not None else None

    def delete_round(self, round_id: int) -> bool:
        return self._store.delete(EXAM_ROUND, round_id)

    def update_round(
        self, round_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        existing = self._store.get(EXAM_ROUND, round_id)
        if existing is None:
            return None
        changes = dict(values)
        merged = {**existing, **changes}
        if any(
            merged[field] != existing[field]
            for field in ("exam_half_year_id", "committee_id")
            if field in changes
        ):
            raise ValueError("An exam round cannot be reassigned to another half-year or committee")
        if not str(merged.get("name", "")).strip():
            raise ValueError("Exam round name is required")
        if (
            "status" in changes
            and merged["status"] != existing["status"]
            and {
                merged["status"],
                existing["status"],
            }.intersection({"plan_proposed", "plan_confirmed"})
        ):
            raise ValueError("Planning proposal statuses require the planning aggregate")
        deadline = merged.get("availability_deadline")
        reminder = merged.get("availability_reminder_at")
        if deadline and reminder and reminder > deadline:
            raise ValueError("Availability reminder must be before the deadline")
        row = self._store.update(EXAM_ROUND, round_id, changes)
        return _record(row or existing)

    def list_candidates(self, filters: Mapping[str, PlanningValue]) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.where(CANDIDATE, **dict(filters))))

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None:
        row = self._store.get(CANDIDATE, candidate_id)
        return _record(row) if row is not None else None

    def create_candidate(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        payload = dict(values)
        exam_round_id = payload.pop("exam_round_id", None)
        attempt_number = payload.pop("attempt_number", None)
        requires_mep = payload.pop("requires_mep", None)
        candidate = self._store.create(CANDIDATE, payload)
        if exam_round_id is not None:
            self._assign_candidate(
                candidate["id"], int(exam_round_id), attempt_number, requires_mep, None
            )
        return _record(candidate)

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        payload = dict(values)
        exam_round_id = payload.pop("exam_round_id", None)
        attempt_number = payload.pop("attempt_number", None)
        requires_mep = payload.pop("requires_mep", None)
        change_reason = payload.pop("assignment_change_reason", None)
        if ("attempt_number" in values or "requires_mep" in values) and exam_round_id is None:
            raise ValueError("Missing required field: exam_round_id")
        candidate = self._store.update(CANDIDATE, candidate_id, payload)
        if candidate is None:
            return None
        if exam_round_id is not None:
            self._assign_candidate(
                candidate_id,
                int(exam_round_id),
                attempt_number,
                requires_mep,
                str(change_reason) if change_reason is not None else None,
            )
        return _record(candidate)

    def delete_candidate(self, candidate_id: int) -> bool:
        self._store.delete_where(CANDIDATE_COMMITTEE_ASSIGNMENT, candidate_id=candidate_id)
        self._store.delete_where(ROUND_CANDIDATE, candidate_id=candidate_id)
        return self._store.delete(CANDIDATE, candidate_id)

    def list_candidate_assignments(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(_record, self._store.where(CANDIDATE_COMMITTEE_ASSIGNMENT, **dict(filters)))
        )

    def list_round_candidates(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.where(ROUND_CANDIDATE, **dict(filters))))

    def assign_candidate_to_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        payload = dict(values)
        self._assign_candidate(
            _required_id(payload, "candidate_id"),
            _required_id(payload, "exam_round_id"),
            payload.get("attempt_number"),
            payload.get("requires_mep"),
            (
                str(payload["assignment_change_reason"])
                if payload.get("assignment_change_reason") is not None
                else None
            ),
        )
        row = self._store.first(
            ROUND_CANDIDATE,
            candidate_id=_required_id(payload, "candidate_id"),
            exam_round_id=_required_id(payload, "exam_round_id"),
        )
        if row is None:
            raise ValueError("Round candidate assignment could not be created")
        return _record(row)

    def list_settings(self, filters: Mapping[str, PlanningValue]) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.where(PLANNING_SETTINGS, **dict(filters))))

    def get_settings(self, settings_id: int) -> PlanningRecord | None:
        row = self._store.get(PLANNING_SETTINGS, settings_id)
        return _record(row) if row is not None else None

    def save_settings(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        payload = dict(values)
        self._validate_settings(payload)
        existing = self._store.first(PLANNING_SETTINGS, exam_round_id=payload["exam_round_id"])
        if existing is None:
            return _record(self._store.create(PLANNING_SETTINGS, payload))
        return _record(self._store.update(PLANNING_SETTINGS, existing["id"], payload) or existing)

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        existing = self._store.get(PLANNING_SETTINGS, settings_id)
        if existing is None:
            return None
        payload = dict(values)
        self._validate_settings({**existing, **payload})
        return _record(self._store.update(PLANNING_SETTINGS, settings_id, payload) or existing)

    def delete_settings(self, settings_id: int) -> bool:
        return self._store.delete(PLANNING_SETTINGS, settings_id)

    def list_availabilities(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]:
        return tuple(map(_record, self._store.where(MEMBER_AVAILABILITY, **dict(filters))))

    def get_availability(self, availability_id: int) -> PlanningRecord | None:
        row = self._store.get(MEMBER_AVAILABILITY, availability_id)
        return _record(row) if row is not None else None

    def save_availability(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        payload = self._normalize_availability(dict(values))
        existing = self._store.first(
            MEMBER_AVAILABILITY,
            exam_round_id=payload["exam_round_id"],
            committee_member_id=payload["committee_member_id"],
            candidate_exam_day_id=payload["candidate_exam_day_id"],
        )
        saved = (
            self._store.create(MEMBER_AVAILABILITY, payload)
            if existing is None
            else self._store.update(MEMBER_AVAILABILITY, existing["id"], payload) or existing
        )
        self._propagate_availability(saved)
        return _record(saved)

    def update_availability(
        self, availability_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        existing = self._store.get(MEMBER_AVAILABILITY, availability_id)
        if existing is None:
            return None
        payload = self._normalize_availability({**existing, **dict(values)})
        saved = self._store.update(MEMBER_AVAILABILITY, availability_id, payload) or existing
        self._propagate_availability(saved)
        return _record(saved)

    def delete_availability(self, availability_id: int) -> bool:
        return self._store.delete(MEMBER_AVAILABILITY, availability_id)

    def planning_snapshot(self, round_id: int) -> PlanningSnapshot | None:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            return None
        half_year = self._store.get(EXAM_HALF_YEAR, exam_round["exam_half_year_id"])
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        candidates = self._store.all(CANDIDATE)
        candidate_day_port = SQLiteCandidateDayUnitOfWork(self._store)
        round_candidates = self._store.where(ROUND_CANDIDATE, exam_round_id=round_id)
        active_round_candidate_ids = {row["id"] for row in round_candidates if row["is_active"]}
        candidate_assignments = tuple(
            _record(row)
            for row in self._store.where(
                CANDIDATE_COMMITTEE_ASSIGNMENT, exam_round_id=round_id, ended_at=None
            )
            if row["round_candidate_id"] in active_round_candidate_ids
        )
        members = self._store.where(COMMITTEE_MEMBER, committee_id=exam_round["committee_id"])
        return cast(
            "PlanningSnapshot",
            _SQLitePlanningSnapshot(
                exam_round=_record(exam_round),
                half_year=_record(half_year or {}),
                settings=_record(settings) if settings is not None else None,
                candidates=tuple(map(_record, candidates)),
                members=tuple(map(_record, members)),
                round_candidates=tuple(map(_record, round_candidates)),
                candidate_assignments=candidate_assignments,
                candidate_days=candidate_day_port.candidate_days(round_id),
                availabilities=tuple(
                    map(_record, self._store.where(MEMBER_AVAILABILITY, exam_round_id=round_id))
                ),
                blocked_assignments=self._blocked_assignments(exam_round),
            ),
        )

    def round_summary(self, round_id: int) -> PlanningRoundSummary | None:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            return None
        committee = self._store.get(COMMITTEE, exam_round["committee_id"])
        half_year = self._store.get(EXAM_HALF_YEAR, exam_round["exam_half_year_id"])
        candidate_count = self._store.count(ROUND_CANDIDATE, exam_round_id=round_id, is_active=1)
        mep_count = self._store.count(
            ROUND_CANDIDATE, exam_round_id=round_id, requires_mep=1, is_active=1
        )
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        availability_counts = self._store.grouped_counts(
            MEMBER_AVAILABILITY, "availability", exam_round_id=round_id
        )
        return cast(
            "PlanningRoundSummary",
            _SQLitePlanningRoundSummary(
                round_id=int(exam_round["id"]),
                name=str(exam_round["name"]),
                status=str(exam_round["status"]),
                committee_id=int(exam_round["committee_id"]),
                committee_name=str(committee["name"]) if committee is not None else None,
                half_year=MappingProxyType(dict(half_year)) if half_year is not None else None,
                candidate_count=candidate_count,
                mep_count=mep_count,
                settings=_record(settings) if settings is not None else None,
                availability_counts=tuple(map(_record, availability_counts)),
            ),
        )

    def _blocked_assignments(self, exam_round: Mapping[str, object]) -> tuple[PlanningBlocker, ...]:
        blockers: list[PlanningBlocker] = []
        for assignment in self._store.all(EXAM_DAY_ASSIGNMENT):
            day = self._store.get(EXAM_DAY, assignment["exam_day_id"])
            if day is None or day["status"] in {"cancelled", "completed"}:
                continue
            other_round = self._store.get(EXAM_ROUND, day["exam_round_id"])
            if (
                other_round is None
                or other_round["id"] == exam_round["id"]
                or other_round["exam_half_year_id"] != exam_round["exam_half_year_id"]
            ):
                continue
            member = self._store.get(COMMITTEE_MEMBER, assignment["committee_member_id"])
            committee = self._store.get(COMMITTEE, other_round["committee_id"])
            if member is None or committee is None:
                continue
            blockers.append(
                _SQLitePlanningBlocker(
                    date=str(day["date"]),
                    day_part=str(assignment["day_part"]),
                    person_id=int(member["person_id"]),
                    exam_half_year_id=int(other_round["exam_half_year_id"]),
                    exam_round_id=int(other_round["id"]),
                    exam_day_status=str(day["status"]),
                    committee_name=str(committee["name"]),
                )
            )
        return tuple(blockers)

    def _resolve_half_year(self, values: dict[str, PlanningValue]) -> None:
        if values.get("exam_half_year_id") is not None:
            values.pop("season", None)
            values.pop("year", None)
            if self._store.get(EXAM_HALF_YEAR, values["exam_half_year_id"]) is None:
                raise ValueError("Exam half-year not found")
            return
        season = values.pop("season", None)
        year = values.pop("year", None)
        if season not in {"summer", "winter"}:
            raise ValueError("Season must be summer or winter")
        try:
            year_value = int(year)  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise ValueError("Year must be a four-digit number") from error
        if not 2000 <= year_value <= 2100:
            raise ValueError("Year must be between 2000 and 2100")
        half_year = self._store.first(EXAM_HALF_YEAR, season=season, year=year_value)
        if half_year is None:
            half_year = self._store.create(
                EXAM_HALF_YEAR, {"season": season, "year": year_value, "status": "active"}
            )
        values["exam_half_year_id"] = half_year["id"]

    def _validate_round_references(self, values: Mapping[str, PlanningValue]) -> None:
        for field in ("exam_half_year_id", "committee_id", "created_by_member_id"):
            if field not in values:
                raise ValueError(f"Missing required field: {field}")
        committee = self._store.get(COMMITTEE, values["committee_id"])
        if committee is None:
            raise ValueError("Committee not found")
        if not committee["is_active"] or committee["bootstrap_state"] != "ready":
            raise ValueError("Committee is not ready for an exam round")
        creator = self._store.get(COMMITTEE_MEMBER, values["created_by_member_id"])
        if creator is None or creator["committee_id"] != values["committee_id"]:
            raise ValueError("Creating member does not belong to the exam round committee")

    @staticmethod
    def _validate_round(values: Mapping[str, PlanningValue]) -> None:
        if not str(values.get("name", "")).strip():
            raise ValueError("Exam round name is required")
        if values.get("status") in {"plan_proposed", "plan_confirmed"}:
            raise ValueError("Planning proposal statuses require the planning aggregate")

    def _assign_candidate(
        self,
        candidate_id: int,
        round_id: int,
        attempt_number: PlanningValue,
        requires_mep: PlanningValue,
        reason: str | None,
    ) -> None:
        if self._store.get(CANDIDATE, candidate_id) is None:
            raise ValueError("Candidate not found")
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            raise ValueError("Exam round not found")
        half_year_id = exam_round["exam_half_year_id"]
        active = self._store.first(
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            candidate_id=candidate_id,
            exam_half_year_id=half_year_id,
            ended_at=None,
        )
        round_candidate = self._store.first(
            ROUND_CANDIDATE, candidate_id=candidate_id, exam_round_id=round_id
        )
        if active and active["exam_round_id"] != round_id:
            if not str(reason or "").strip():
                raise ValueError("A reason is required for a committee change")
            ended_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
            self._store.update(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                active["id"],
                {"ended_at": ended_at, "change_reason": reason},
            )
            self._store.update(ROUND_CANDIDATE, active["round_candidate_id"], {"is_active": 0})
            active = None
        if round_candidate is None:
            round_candidate = self._store.create(
                ROUND_CANDIDATE,
                {
                    "exam_round_id": round_id,
                    "candidate_id": candidate_id,
                    "attempt_number": attempt_number or 1,
                    "requires_mep": requires_mep or 0,
                    "is_active": 1,
                },
            )
        else:
            changed: dict[str, object] = {"is_active": 1}
            if attempt_number is not None:
                changed["attempt_number"] = attempt_number
            if requires_mep is not None:
                changed["requires_mep"] = requires_mep
            round_candidate = (
                self._store.update(ROUND_CANDIDATE, round_candidate["id"], changed)
                or round_candidate
            )
        if active is None:
            self._store.create(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                {
                    "candidate_id": candidate_id,
                    "exam_half_year_id": half_year_id,
                    "exam_round_id": round_id,
                    "round_candidate_id": round_candidate["id"],
                },
            )

    def _validate_settings(self, values: Mapping[str, PlanningValue]) -> None:
        for field in ("exam_round_id", "updated_by_member_id"):
            if field not in values:
                raise ValueError(f"Missing required field: {field}")
        exam_round = self._store.get(EXAM_ROUND, values["exam_round_id"])
        if exam_round is None:
            raise ValueError("Exam round not found")
        updater = self._store.get(COMMITTEE_MEMBER, values["updated_by_member_id"])
        if updater is None or updater["committee_id"] != exam_round["committee_id"]:
            raise ValueError("Updating member does not belong to the exam round committee")
        room_id = values.get("default_room_id")
        if room_id is not None and not self._room_is_usable(room_id, exam_round["committee_id"]):
            raise ValueError("Default room is not active for the exam round committee")
        subdivision = values.get("holiday_subdivision_code")
        if subdivision is not None and subdivision not in _GERMAN_SUBDIVISION_CODES:
            raise ValueError("Unknown German federal state")
        if values.get("exclude_public_holidays") and subdivision is None:
            raise ValueError("Federal state is required when public holidays are excluded")

    def _room_is_usable(self, room_id: object, committee_id: object) -> bool:
        room = self._store.session.get(EXAM_ROOM.model, room_id)
        if room is None or not room.is_active:
            return False
        venue = self._store.session.get(EXAM_VENUE.model, room.venue_id)
        return bool(
            venue
            and venue.is_active
            and (venue.scope == "global" or venue.committee_id == committee_id)
            and (not self._require_confirmed_coordinates or venue.coordinate_status == "confirmed")
        )

    def _normalize_availability(self, values: dict[str, PlanningValue]) -> dict[str, PlanningValue]:
        for field in (
            "exam_round_id",
            "committee_member_id",
            "candidate_exam_day_id",
            "availability",
        ):
            if field not in values:
                raise ValueError(f"Missing required field: {field}")
        if values["availability"] not in _AVAILABILITY_VALUES:
            raise ValueError("Unknown availability value")
        exam_round = self._store.get(EXAM_ROUND, values["exam_round_id"])
        if exam_round is None:
            raise ValueError("Exam round not found")
        member = self._store.get(COMMITTEE_MEMBER, values["committee_member_id"])
        if (
            member is None
            or not member["is_active"]
            or member["committee_id"] != exam_round["committee_id"]
        ):
            raise ValueError("Member does not belong to the exam round committee")
        day = self._store.get(CANDIDATE_EXAM_DAY, values["candidate_exam_day_id"])
        if day is None or day["exam_round_id"] != values["exam_round_id"]:
            raise ValueError("Candidate exam day does not belong to the exam round")
        if values["availability"] == "pending":
            values["responded_at"] = None
        else:
            values["responded_at"] = (
                values.get("responded_at") or datetime.now(UTC).replace(microsecond=0).isoformat()
            )
        return values

    def _propagate_availability(self, saved: Mapping[str, object]) -> None:
        member = self._store.get(COMMITTEE_MEMBER, saved["committee_member_id"])
        day = self._store.get(CANDIDATE_EXAM_DAY, saved["candidate_exam_day_id"])
        source_round = self._store.get(EXAM_ROUND, saved["exam_round_id"])
        if member is None or day is None or source_round is None:
            return
        for other_member in self._store.all(COMMITTEE_MEMBER):
            if (
                other_member["id"] == member["id"]
                or other_member["person_id"] != member["person_id"]
            ):
                continue
            for other_day in self._store.all(CANDIDATE_EXAM_DAY):
                if other_day["date"] != day["date"]:
                    continue
                other_round = self._store.get(EXAM_ROUND, other_day["exam_round_id"])
                if (
                    other_round is None
                    or other_round["committee_id"] != other_member["committee_id"]
                    or other_round["exam_half_year_id"] != source_round["exam_half_year_id"]
                ):
                    continue
                existing = self._store.first(
                    MEMBER_AVAILABILITY,
                    exam_round_id=other_day["exam_round_id"],
                    committee_member_id=other_member["id"],
                    candidate_exam_day_id=other_day["id"],
                )
                values = {
                    "exam_round_id": other_day["exam_round_id"],
                    "committee_member_id": other_member["id"],
                    "candidate_exam_day_id": other_day["id"],
                    "availability": saved["availability"],
                    "responded_at": saved["responded_at"],
                }
                if existing is None:
                    self._store.create(MEMBER_AVAILABILITY, values)
                else:
                    self._store.update(MEMBER_AVAILABILITY, existing["id"], values)
