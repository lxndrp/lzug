"""SQLite implementation of the application's resource access query ports."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from sqlalchemy import false, select, true
from sqlalchemy.sql.elements import ColumnElement

from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_ATTENDANCE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    EXAM_VENUE,
    MEMBER_AVAILABILITY,
    MEMBER_EXAM_ATTENDANCE,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Candidate,
    CandidateCommitteeAssignment,
    CandidateExamAttendance,
    Committee,
    CommitteeMember,
    ExamDay,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    Person,
    Resource,
    RoundCandidate,
)
from backend.persistence.store import Store


class _ResourceKind(StrEnum):
    COMMITTEE = "committee"
    PERSON = "person"
    COMMITTEE_MEMBER = "committee_member"
    EXAM_HALF_YEAR = "exam_half_year"
    EXAM_ROUND = "exam_round"
    ROUND_CANDIDATE = "round_candidate"
    CANDIDATE = "candidate"
    CANDIDATE_COMMITTEE_ASSIGNMENT = "candidate_committee_assignment"
    PLANNING_SETTINGS = "planning_settings"
    CANDIDATE_EXAM_DAY = "candidate_exam_day"
    MEMBER_AVAILABILITY = "member_availability"
    EXAM_DAY = "exam_day"
    EXAM_SLOT = "exam_slot"
    EXAM_DAY_ASSIGNMENT = "exam_day_assignment"
    CANDIDATE_EXAM_ATTENDANCE = "candidate_exam_attendance"
    MEMBER_EXAM_ATTENDANCE = "member_exam_attendance"
    EXAM_VENUE = "exam_venue"


class _Scope(Protocol):
    committee_ids: frozenset[int]
    person_ids: frozenset[int]


class _ReferenceField(StrEnum):
    COMMITTEE_ID = "committee_id"
    PERSON_ID = "person_id"
    EXAM_HALF_YEAR_ID = "exam_half_year_id"
    EXAM_ROUND_ID = "exam_round_id"
    CANDIDATE_ID = "candidate_id"
    ROUND_CANDIDATE_ID = "round_candidate_id"
    EXAM_DAY_ID = "exam_day_id"
    EXAM_SLOT_ID = "exam_slot_id"
    COMMITTEE_MEMBER_ID = "committee_member_id"
    CANDIDATE_EXAM_DAY_ID = "candidate_exam_day_id"


_REFERENCE_FIELDS = tuple(_ReferenceField)


class _ReferenceFieldValue(Protocol):
    value: str


class _ReferenceChange(Protocol):
    field: _ReferenceFieldValue
    value: int | None


@dataclass(frozen=True)
class _SQLiteReferences:
    committee_id: int | None = None
    person_id: int | None = None
    exam_half_year_id: int | None = None
    exam_round_id: int | None = None
    candidate_id: int | None = None
    round_candidate_id: int | None = None
    exam_day_id: int | None = None
    exam_slot_id: int | None = None
    committee_member_id: int | None = None
    candidate_exam_day_id: int | None = None

    def value(self, field: object) -> int | None:
        name = getattr(field, "value", field)
        return getattr(self, str(name))

    def overlay(self, changes: Sequence[_ReferenceChange]) -> _SQLiteReferences:
        values = {str(change.field.value): change.value for change in changes}
        return _SQLiteReferences(**{**self.__dict__, **values})


@dataclass(frozen=True)
class _SQLiteOwnership:
    committee_id: int | None
    round_id: int | None
    references: _SQLiteReferences
    exists: bool


@dataclass(frozen=True)
class _SQLiteCommitteeMemberIdentity:
    member_id: int
    person_id: int
    committee_id: int
    is_active: bool


_RESOURCES: dict[_ResourceKind, Resource] = {
    _ResourceKind.COMMITTEE: COMMITTEE,
    _ResourceKind.PERSON: PERSON,
    _ResourceKind.COMMITTEE_MEMBER: COMMITTEE_MEMBER,
    _ResourceKind.EXAM_HALF_YEAR: EXAM_HALF_YEAR,
    _ResourceKind.EXAM_ROUND: EXAM_ROUND,
    _ResourceKind.ROUND_CANDIDATE: ROUND_CANDIDATE,
    _ResourceKind.CANDIDATE: CANDIDATE,
    _ResourceKind.CANDIDATE_COMMITTEE_ASSIGNMENT: CANDIDATE_COMMITTEE_ASSIGNMENT,
    _ResourceKind.PLANNING_SETTINGS: PLANNING_SETTINGS,
    _ResourceKind.CANDIDATE_EXAM_DAY: CANDIDATE_EXAM_DAY,
    _ResourceKind.MEMBER_AVAILABILITY: MEMBER_AVAILABILITY,
    _ResourceKind.EXAM_DAY: EXAM_DAY,
    _ResourceKind.EXAM_SLOT: EXAM_SLOT,
    _ResourceKind.EXAM_DAY_ASSIGNMENT: EXAM_DAY_ASSIGNMENT,
    _ResourceKind.CANDIDATE_EXAM_ATTENDANCE: CANDIDATE_EXAM_ATTENDANCE,
    _ResourceKind.MEMBER_EXAM_ATTENDANCE: MEMBER_EXAM_ATTENDANCE,
    _ResourceKind.EXAM_VENUE: EXAM_VENUE,
}
_ROUND_OWNED = frozenset(
    {
        _ResourceKind.ROUND_CANDIDATE,
        _ResourceKind.CANDIDATE_COMMITTEE_ASSIGNMENT,
        _ResourceKind.PLANNING_SETTINGS,
        _ResourceKind.CANDIDATE_EXAM_DAY,
        _ResourceKind.MEMBER_AVAILABILITY,
        _ResourceKind.EXAM_DAY,
    }
)
_DAY_OWNED = frozenset(
    {
        _ResourceKind.EXAM_SLOT,
        _ResourceKind.EXAM_DAY_ASSIGNMENT,
        _ResourceKind.MEMBER_EXAM_ATTENDANCE,
    }
)


class SQLiteResourceAccessQueryFactory:
    """Create short-lived query adapters over explicit SQLite read snapshots."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def snapshot(self) -> Iterator[SQLiteResourceAccessQueries]:
        with read_session_scope(self.db_path) as session:
            yield SQLiteResourceAccessQueries(Store(session))

    def for_transaction(self, transaction: object) -> SQLiteResourceAccessQueries:
        """Bind to a repository-owned Store without opening another session."""
        if not isinstance(transaction, Store):
            raise TypeError("SQLite resource queries require a repository Store")
        return SQLiteResourceAccessQueries(transaction)


class SQLiteResourceAccessQueries:
    """Materialize resource ownership and visibility without leaking SQLAlchemy."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def ownership(
        self,
        resource: _ResourceKind,
        resource_id: int | None,
        changes: Sequence[_ReferenceChange] = (),
    ) -> _SQLiteOwnership:
        row = (
            self._store.get(_RESOURCES[resource], resource_id) if resource_id is not None else None
        )
        references = self._references(row).overlay(changes)
        round_id = self._round_id(resource, resource_id, references)
        committee_id = self._committee_id(resource, resource_id, references, round_id)
        return _SQLiteOwnership(committee_id, round_id, references, row is not None)

    def committee_member(self, member_id: int) -> _SQLiteCommitteeMemberIdentity | None:
        member = self._store.get(COMMITTEE_MEMBER, member_id)
        if member is None:
            return None
        return _SQLiteCommitteeMemberIdentity(
            member_id=int(member["id"]),
            person_id=int(member["person_id"]),
            committee_id=int(member["committee_id"]),
            is_active=bool(member["is_active"]),
        )

    def list_visible(
        self,
        resource: _ResourceKind,
        scope: _Scope,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[dict[str, object]]:
        definition = _RESOURCES[resource]
        return self._store.where(
            definition,
            _visibility_condition(resource, scope),
            **dict(filters or {}),
        )

    def get_visible(
        self, resource: _ResourceKind, resource_id: int, scope: _Scope
    ) -> dict[str, object] | None:
        rows = self.list_visible(resource, scope, {"id": resource_id})
        return rows[0] if rows else None

    def list_members(
        self,
        filters: Mapping[str, object] | None = None,
        scope: _Scope | None = None,
    ) -> Sequence[dict[str, object]]:
        conditions = (
            (_visibility_condition(_ResourceKind.COMMITTEE_MEMBER, scope),) if scope else ()
        )
        rows = self._store.where(COMMITTEE_MEMBER, *conditions, **dict(filters or {}))
        people = {
            person["id"]: person
            for person in self._store.where(
                PERSON, Person.id.in_({row["person_id"] for row in rows})
            )
        }
        return [self._member_projection(row, people[row["person_id"]]) for row in rows]

    def get_member(self, member_id: int, scope: _Scope | None = None) -> dict[str, object] | None:
        conditions = (
            (_visibility_condition(_ResourceKind.COMMITTEE_MEMBER, scope),) if scope else ()
        )
        rows = self._store.where(COMMITTEE_MEMBER, *conditions, id=member_id)
        if not rows:
            return None
        person = self._store.get(PERSON, rows[0]["person_id"])
        return self._member_projection(rows[0], person) if person is not None else None

    @staticmethod
    def _references(row: Mapping[str, object] | None) -> _SQLiteReferences:
        row = row or {}
        values = {field.value: row.get(field.value) for field in _REFERENCE_FIELDS}
        return _SQLiteReferences(**values)

    def _round_id(
        self, resource: _ResourceKind, resource_id: int | None, values: _SQLiteReferences
    ) -> int | None:
        if resource == _ResourceKind.EXAM_ROUND:
            return resource_id
        if resource in _ROUND_OWNED:
            return values.exam_round_id
        if resource == _ResourceKind.CANDIDATE:
            if values.exam_round_id is not None:
                return values.exam_round_id
            assignment = self._store.first(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                candidate_id=resource_id,
                ended_at=None,
            )
            return assignment.get("exam_round_id") if assignment else None
        if resource in _DAY_OWNED:
            return self._day_round_id(values.exam_day_id)
        if resource == _ResourceKind.CANDIDATE_EXAM_ATTENDANCE:
            slot = self._store.get(EXAM_SLOT, values.exam_slot_id)
            return self._day_round_id(slot["exam_day_id"]) if slot else None
        return None

    def _day_round_id(self, day_id: int | None) -> int | None:
        day = self._store.get(EXAM_DAY, day_id)
        return day.get("exam_round_id") if day else None

    def _committee_id(
        self,
        resource: _ResourceKind,
        resource_id: int | None,
        values: _SQLiteReferences,
        round_id: int | None,
    ) -> int | None:
        if resource == _ResourceKind.COMMITTEE:
            return resource_id
        if resource in {_ResourceKind.EXAM_ROUND, _ResourceKind.COMMITTEE_MEMBER}:
            return values.committee_id
        if resource == _ResourceKind.PERSON:
            member = self._store.first(COMMITTEE_MEMBER, person_id=resource_id)
            return member["committee_id"] if member else None
        if resource == _ResourceKind.EXAM_HALF_YEAR:
            exam_round = self._store.first(EXAM_ROUND, exam_half_year_id=resource_id)
        else:
            exam_round = self._store.get(EXAM_ROUND, round_id)
        return exam_round.get("committee_id") if exam_round else None

    @staticmethod
    def _member_projection(
        member: Mapping[str, object], person: Mapping[str, object]
    ) -> dict[str, object]:
        return {
            **member,
            **{key: person[key] for key in ("first_name", "last_name", "email", "mobile")},
            "email_verified_at": None,
        }


def _visibility_condition(resource: _ResourceKind, scope: _Scope | None) -> ColumnElement[bool]:
    """Keep scoped SQL predicates inside the SQLite adapter."""
    if scope is None:
        return true()
    direct = {
        _ResourceKind.COMMITTEE: Committee.id.in_(scope.committee_ids),
        _ResourceKind.PERSON: Person.id.in_(scope.person_ids),
        _ResourceKind.COMMITTEE_MEMBER: CommitteeMember.committee_id.in_(scope.committee_ids),
        _ResourceKind.EXAM_HALF_YEAR: true() if scope.committee_ids else false(),
        _ResourceKind.EXAM_ROUND: ExamRound.committee_id.in_(scope.committee_ids),
    }
    if resource in direct:
        return direct[resource]
    rounds = select(ExamRound.id).where(ExamRound.committee_id.in_(scope.committee_ids))
    if resource in {
        _ResourceKind.ROUND_CANDIDATE,
        _ResourceKind.CANDIDATE_COMMITTEE_ASSIGNMENT,
        _ResourceKind.PLANNING_SETTINGS,
        _ResourceKind.CANDIDATE_EXAM_DAY,
        _ResourceKind.EXAM_DAY,
    }:
        return _RESOURCES[resource].model.exam_round_id.in_(rounds)
    if resource == _ResourceKind.CANDIDATE:
        return Candidate.id.in_(
            select(RoundCandidate.candidate_id)
            .join(
                CandidateCommitteeAssignment,
                CandidateCommitteeAssignment.round_candidate_id == RoundCandidate.id,
            )
            .where(
                CandidateCommitteeAssignment.ended_at.is_(None),
                RoundCandidate.exam_round_id.in_(rounds),
            )
        )
    if resource == _ResourceKind.MEMBER_AVAILABILITY:
        members = select(CommitteeMember.id).where(
            CommitteeMember.committee_id.in_(scope.committee_ids)
        )
        return MemberAvailability.exam_round_id.in_(rounds) & (
            MemberAvailability.committee_member_id.in_(members)
        )
    days = select(ExamDay.id).where(ExamDay.exam_round_id.in_(rounds))
    if resource in {
        _ResourceKind.EXAM_SLOT,
        _ResourceKind.EXAM_DAY_ASSIGNMENT,
        _ResourceKind.MEMBER_EXAM_ATTENDANCE,
    }:
        return _RESOURCES[resource].model.exam_day_id.in_(days)
    if resource == _ResourceKind.CANDIDATE_EXAM_ATTENDANCE:
        slots = select(ExamSlot.id).where(ExamSlot.exam_day_id.in_(days))
        return CandidateExamAttendance.exam_slot_id.in_(slots)
    return false()
