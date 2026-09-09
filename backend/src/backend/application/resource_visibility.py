"""SQL predicates for the application's existing resource visibility rules."""

from __future__ import annotations

from sqlalchemy import false, select, true
from sqlalchemy.sql.elements import ColumnElement

from backend.identity.authorization import AuthorizationScope
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


def visibility_condition(resource: Resource, scope: AuthorizationScope) -> ColumnElement[bool]:
    """Restrict before materialization, preserving history and person scope.

    Membership activity has already been resolved into ``scope``. Rows about
    inactive members remain readable within that scope, as do historical round
    assignments. Candidate master records require an unended assignment.
    """
    direct = {
        COMMITTEE: Committee.id.in_(scope.committee_ids),
        PERSON: Person.id.in_(scope.person_ids),
        COMMITTEE_MEMBER: CommitteeMember.committee_id.in_(scope.committee_ids),
        EXAM_HALF_YEAR: true() if scope.committee_ids else false(),
        EXAM_ROUND: ExamRound.committee_id.in_(scope.committee_ids),
    }
    if resource in direct:
        return direct[resource]
    rounds = select(ExamRound.id).where(ExamRound.committee_id.in_(scope.committee_ids))
    if resource in {
        ROUND_CANDIDATE,
        CANDIDATE_COMMITTEE_ASSIGNMENT,
        PLANNING_SETTINGS,
        CANDIDATE_EXAM_DAY,
        EXAM_DAY,
    }:
        return resource.model.exam_round_id.in_(rounds)
    if resource == CANDIDATE:
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
    if resource == MEMBER_AVAILABILITY:
        members = select(CommitteeMember.id).where(
            CommitteeMember.committee_id.in_(scope.committee_ids)
        )
        return MemberAvailability.exam_round_id.in_(rounds) & (
            MemberAvailability.committee_member_id.in_(members)
        )
    days = select(ExamDay.id).where(ExamDay.exam_round_id.in_(rounds))
    if resource in {EXAM_SLOT, EXAM_DAY_ASSIGNMENT, MEMBER_EXAM_ATTENDANCE}:
        return resource.model.exam_day_id.in_(days)
    if resource == CANDIDATE_EXAM_ATTENDANCE:
        slots = select(ExamSlot.id).where(ExamSlot.exam_day_id.in_(days))
        return CandidateExamAttendance.exam_slot_id.in_(slots)
    return false()
