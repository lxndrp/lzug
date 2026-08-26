from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Committee(Base):
    __tablename__ = "committee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    occupation: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'Fachinformatiker/in'"),
    )
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class CommitteeMember(Base):
    __tablename__ = "committee_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    committee_id: Mapped[int] = mapped_column(ForeignKey("committee.id"))
    member_status: Mapped[str] = mapped_column(String)
    committee_role: Mapped[str] = mapped_column(String)
    representing_side: Mapped[str] = mapped_column(String)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)
    mobile: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class UserAccount(Base):
    """Authentication identity, deliberately separate from committee roles."""

    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    passkey_enabled: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    two_factor_enabled: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    is_operator: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    last_login_at: Mapped[str | None] = mapped_column(String, nullable=True)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    totp_enabled: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "user_account_one_operator",
            "is_operator",
            sqlite_where=sql_text("is_operator = 1"),
        ),
    )


class AuthSession(Base):
    """Server-side session record; only hashes of bearer material are stored."""

    __tablename__ = "auth_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    expires_at: Mapped[str] = mapped_column(String)
    last_seen_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    rotated_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_session.id", ondelete="SET NULL"), nullable=True
    )


class AuthToken(Base):
    """One-time invitation or recovery material; only its hash is persisted."""

    __tablename__ = "auth_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    expires_at: Mapped[str] = mapped_column(String)
    consumed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("auth_token_account_kind", "account_id", "kind", "expires_at"),)


class AuthRecoveryCode(Base):
    """One Argon2id hash for a single-use local recovery code."""

    __tablename__ = "auth_recovery_code"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    consumed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("auth_recovery_code_account_active", "account_id", "consumed_at"),)


class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    committee_id: Mapped[int] = mapped_column(ForeignKey("committee.id"))
    name: Mapped[str] = mapped_column(String)
    street: Mapped[str] = mapped_column(String)
    postal_code: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    room: Mapped[str] = mapped_column(String)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class Candidate(Base):
    __tablename__ = "candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    ihk_exam_number: Mapped[str] = mapped_column(String)
    specialization: Mapped[str] = mapped_column(String)
    training_company: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class ExamHalfYear(Base):
    __tablename__ = "exam_half_year"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season: Mapped[str] = mapped_column(String)
    year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'draft'"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamRound(Base):
    __tablename__ = "exam_round"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_half_year_id: Mapped[int] = mapped_column(ForeignKey("exam_half_year.id"))
    committee_id: Mapped[int] = mapped_column(ForeignKey("committee.id"))
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'draft'"))
    plan_revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    availability_deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    availability_reminder_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_member_id: Mapped[int] = mapped_column(ForeignKey("committee_member.id"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class RoundCandidate(Base):
    __tablename__ = "round_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    requires_mep: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class CandidateCommitteeAssignment(Base):
    """One time-bounded candidate responsibility within an exam half-year."""

    __tablename__ = "candidate_committee_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    exam_half_year_id: Mapped[int] = mapped_column(ForeignKey("exam_half_year.id"))
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    round_candidate_id: Mapped[int] = mapped_column(ForeignKey("round_candidate.id"))
    assigned_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class PlanningSettings(Base):
    __tablename__ = "planning_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    calendar_week_from: Mapped[str] = mapped_column(String)
    calendar_week_to: Mapped[str] = mapped_column(String)
    exams_per_day: Mapped[int] = mapped_column(Integer)
    max_exam_days_per_week: Mapped[int] = mapped_column(Integer)
    lunch_break_enabled: Mapped[int] = mapped_column(
        Integer,
        server_default=sql_text("1"),
    )
    exclude_public_holidays: Mapped[int] = mapped_column(
        Integer,
        server_default=sql_text("0"),
    )
    holiday_subdivision_code: Mapped[str | None] = mapped_column(String, nullable=True)
    default_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("location.id"),
        nullable=True,
    )
    updated_by_member_id: Mapped[int] = mapped_column(ForeignKey("committee_member.id"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class CandidateExamDay(Base):
    __tablename__ = "candidate_exam_day"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    date: Mapped[str] = mapped_column(String)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class MemberAvailability(Base):
    __tablename__ = "member_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    committee_member_id: Mapped[int] = mapped_column(ForeignKey("committee_member.id"))
    candidate_exam_day_id: Mapped[int] = mapped_column(ForeignKey("candidate_exam_day.id"))
    availability: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'pending'"),
    )
    responded_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class ExamDay(Base):
    __tablename__ = "exam_day"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    date: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'proposed'"))
    lunch_break_enabled: Mapped[int] = mapped_column(
        Integer,
        server_default=sql_text("1"),
    )
    created_from_proposal: Mapped[int] = mapped_column(
        Integer,
        server_default=sql_text("1"),
    )
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class ExamSlot(Base):
    __tablename__ = "exam_slot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id"))
    round_candidate_id: Mapped[int] = mapped_column(ForeignKey("round_candidate.id"))
    slot_type: Mapped[str] = mapped_column(String)
    starts_at: Mapped[str] = mapped_column(String)
    ends_at: Mapped[str] = mapped_column(String)
    sequence_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'proposed'"))
    actual_started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    execution_status: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'open'"),
    )
    status_changed_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    actual_completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class ExamDayAssignment(Base):
    __tablename__ = "exam_day_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id"))
    committee_member_id: Mapped[int] = mapped_column(ForeignKey("committee_member.id"))
    assignment_role: Mapped[str] = mapped_column(String)
    day_part: Mapped[str] = mapped_column(String)
    fallback_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class CandidateExamAttendance(Base):
    __tablename__ = "candidate_exam_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_slot_id: Mapped[int] = mapped_column(ForeignKey("exam_slot.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    arrived_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class MemberExamAttendance(Base):
    __tablename__ = "member_exam_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    arrived_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class Document(Base):
    """Database metadata for one document owned by a storage adapter."""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_id: Mapped[str] = mapped_column(String, unique=True)
    original_filename: Mapped[str] = mapped_column(String)
    media_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class Notification(Base):
    """A durable domain notification, independent from delivery channels."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    committee_id: Mapped[int] = mapped_column(ForeignKey("committee.id", ondelete="CASCADE"))
    exam_round_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round.id", ondelete="CASCADE"), nullable=True
    )
    recipient_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String)
    origin_key: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    action_path: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "notification_recipient_event_origin",
            "recipient_member_id",
            "event_type",
            "origin_key",
            unique=True,
        ),
    )


class PushSubscription(Base):
    """A browser push endpoint. No notification content is stored here."""

    __tablename__ = "push_subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    invalidated_at: Mapped[str | None] = mapped_column(String, nullable=True)


class NotificationDelivery(Base):
    """Technical channel state kept separate from domain notification content."""

    __tablename__ = "notification_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notification.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String)
    target_key: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    next_attempt_at: Mapped[str | None] = mapped_column(String, nullable=True)
    technical_confirmed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


@dataclass(frozen=True)
class Resource:
    model: type[Base]
    fields: tuple[str, ...]
    order_by: tuple[str, ...] = ()
    writable_fields: tuple[str, ...] = ()

    @property
    def readable_fields(self) -> tuple[str, ...]:
        return ("id", *self.fields)

    @property
    def table(self) -> str:
        return self.model.__tablename__


def model_to_dict(model: Any, resource: Resource) -> dict[str, Any]:
    return {field: getattr(model, field) for field in resource.readable_fields}


COMMITTEE = Resource(
    model=Committee,
    fields=("name", "occupation", "created_at", "updated_at"),
    order_by=("name",),
    writable_fields=("name", "occupation"),
)

COMMITTEE_MEMBER = Resource(
    model=CommitteeMember,
    fields=(
        "person_id",
        "committee_id",
        "member_status",
        "committee_role",
        "representing_side",
        "is_active",
        "created_at",
        "updated_at",
    ),
    order_by=("-is_active", "id"),
    writable_fields=(
        "person_id",
        "committee_id",
        "member_status",
        "committee_role",
        "representing_side",
        "is_active",
    ),
)

PERSON = Resource(
    model=Person,
    fields=("first_name", "last_name", "email", "mobile", "created_at", "updated_at"),
    order_by=("last_name", "first_name"),
    writable_fields=("first_name", "last_name", "email", "mobile"),
)

LOCATION = Resource(
    model=Location,
    fields=(
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "room",
        "is_active",
        "created_at",
        "updated_at",
    ),
    order_by=("-is_active", "name"),
    writable_fields=(
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "room",
        "is_active",
    ),
)

CANDIDATE = Resource(
    model=Candidate,
    fields=(
        "first_name",
        "last_name",
        "ihk_exam_number",
        "specialization",
        "training_company",
        "created_at",
        "updated_at",
    ),
    order_by=("last_name", "first_name"),
    writable_fields=(
        "first_name",
        "last_name",
        "ihk_exam_number",
        "specialization",
        "training_company",
    ),
)

EXAM_ROUND = Resource(
    model=ExamRound,
    fields=(
        "exam_half_year_id",
        "committee_id",
        "name",
        "status",
        "availability_deadline",
        "availability_reminder_at",
        "created_by_member_id",
        "created_at",
        "updated_at",
    ),
    order_by=("-created_at",),
    writable_fields=(
        "exam_half_year_id",
        "committee_id",
        "name",
        "status",
        "availability_deadline",
        "availability_reminder_at",
        "created_by_member_id",
    ),
)

EXAM_HALF_YEAR = Resource(
    model=ExamHalfYear,
    fields=("season", "year", "status", "created_at", "updated_at"),
    order_by=("-year", "season"),
    writable_fields=("season", "year", "status"),
)

ROUND_CANDIDATE = Resource(
    model=RoundCandidate,
    fields=(
        "exam_round_id",
        "candidate_id",
        "attempt_number",
        "requires_mep",
        "is_active",
        "created_at",
        "updated_at",
    ),
    order_by=("id",),
    writable_fields=(
        "exam_round_id",
        "candidate_id",
        "attempt_number",
        "requires_mep",
        "is_active",
    ),
)

CANDIDATE_COMMITTEE_ASSIGNMENT = Resource(
    model=CandidateCommitteeAssignment,
    fields=(
        "candidate_id",
        "exam_half_year_id",
        "exam_round_id",
        "round_candidate_id",
        "assigned_at",
        "ended_at",
        "change_reason",
        "created_at",
        "updated_at",
    ),
    order_by=("-assigned_at", "-id"),
    writable_fields=(
        "candidate_id",
        "exam_half_year_id",
        "exam_round_id",
        "round_candidate_id",
        "assigned_at",
        "ended_at",
        "change_reason",
    ),
)

PLANNING_SETTINGS = Resource(
    model=PlanningSettings,
    fields=(
        "exam_round_id",
        "calendar_week_from",
        "calendar_week_to",
        "exams_per_day",
        "max_exam_days_per_week",
        "lunch_break_enabled",
        "exclude_public_holidays",
        "holiday_subdivision_code",
        "default_location_id",
        "updated_by_member_id",
        "created_at",
        "updated_at",
    ),
    writable_fields=(
        "exam_round_id",
        "calendar_week_from",
        "calendar_week_to",
        "exams_per_day",
        "max_exam_days_per_week",
        "lunch_break_enabled",
        "exclude_public_holidays",
        "holiday_subdivision_code",
        "default_location_id",
        "updated_by_member_id",
    ),
)

CANDIDATE_EXAM_DAY = Resource(
    model=CandidateExamDay,
    fields=(
        "exam_round_id",
        "date",
        "is_active",
        "created_at",
        "updated_at",
    ),
    order_by=("date",),
    writable_fields=(
        "exam_round_id",
        "date",
        "is_active",
    ),
)

MEMBER_AVAILABILITY = Resource(
    model=MemberAvailability,
    fields=(
        "exam_round_id",
        "committee_member_id",
        "candidate_exam_day_id",
        "availability",
        "responded_at",
        "created_at",
        "updated_at",
    ),
    writable_fields=(
        "exam_round_id",
        "committee_member_id",
        "candidate_exam_day_id",
        "availability",
        "responded_at",
    ),
)

EXAM_DAY = Resource(
    model=ExamDay,
    fields=(
        "exam_round_id",
        "location_id",
        "date",
        "status",
        "lunch_break_enabled",
        "created_from_proposal",
        "created_at",
        "updated_at",
    ),
    order_by=("date",),
    writable_fields=(
        "exam_round_id",
        "location_id",
        "date",
        "status",
        "lunch_break_enabled",
        "created_from_proposal",
    ),
)

EXAM_SLOT = Resource(
    model=ExamSlot,
    fields=(
        "exam_day_id",
        "round_candidate_id",
        "slot_type",
        "starts_at",
        "ends_at",
        "sequence_number",
        "status",
        "actual_started_at",
        "execution_status",
        "status_changed_at",
        "actual_completed_at",
        "status_reason",
        "created_at",
        "updated_at",
    ),
    order_by=("exam_day_id", "sequence_number"),
    writable_fields=(
        "exam_day_id",
        "round_candidate_id",
        "slot_type",
        "starts_at",
        "ends_at",
        "sequence_number",
        "status",
    ),
)

EXAM_DAY_ASSIGNMENT = Resource(
    model=ExamDayAssignment,
    fields=(
        "exam_day_id",
        "committee_member_id",
        "assignment_role",
        "day_part",
        "fallback_status",
        "created_at",
        "updated_at",
    ),
    order_by=("exam_day_id", "day_part", "assignment_role"),
    writable_fields=(
        "exam_day_id",
        "committee_member_id",
        "assignment_role",
        "day_part",
        "fallback_status",
    ),
)

CANDIDATE_EXAM_ATTENDANCE = Resource(
    model=CandidateExamAttendance,
    fields=("exam_slot_id", "status", "arrived_at", "created_at", "updated_at"),
    order_by=("exam_slot_id",),
    writable_fields=("exam_slot_id", "status", "arrived_at"),
)

MEMBER_EXAM_ATTENDANCE = Resource(
    model=MemberExamAttendance,
    fields=(
        "exam_day_id",
        "committee_member_id",
        "status",
        "arrived_at",
        "created_at",
        "updated_at",
    ),
    order_by=("exam_day_id", "committee_member_id"),
    writable_fields=("exam_day_id", "committee_member_id", "status", "arrived_at"),
)

DOCUMENT = Resource(
    model=Document,
    fields=(
        "storage_id",
        "original_filename",
        "media_type",
        "size_bytes",
        "checksum_sha256",
        "created_at",
        "updated_at",
    ),
    order_by=("-created_at", "-id"),
    writable_fields=(
        "storage_id",
        "original_filename",
        "media_type",
        "size_bytes",
        "checksum_sha256",
    ),
)
