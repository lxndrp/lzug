from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InstanceMetadata(Base):
    """Stable non-secret identity for one self-hosted instance."""

    __tablename__ = "instance_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ArtifactOperation(Base):
    """Secret-free technical evidence for backup, verification, restore, and export."""

    __tablename__ = "artifact_operation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_type: Mapped[str] = mapped_column(String)
    artifact_id: Mapped[str | None] = mapped_column(String, nullable=True)
    artifact_type: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_at: Mapped[str | None] = mapped_column(String, nullable=True)
    recipient_key_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    technical_actor: Mapped[str] = mapped_column(String, server_default=sql_text("'operator-cli'"))
    occurred_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class BackupRecipient(Base):
    """Active, public age recipient configuration for this instance."""

    __tablename__ = "backup_recipient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient: Mapped[str] = mapped_column(String)
    fingerprint: Mapped[str] = mapped_column(String)
    activated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class BackupRecipientAudit(Base):
    """Immutable, secret-free evidence for recipient activation and replacement."""

    __tablename__ = "backup_recipient_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String)
    previous_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String)
    technical_actor: Mapped[str] = mapped_column(String, server_default=sql_text("'operator-cli'"))
    occurred_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class Committee(Base):
    __tablename__ = "committee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    occupation: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'Fachinformatiker/in'"),
    )
    ihk: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'Nicht konfiguriert'"),
    )
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    bootstrap_state: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'needs_clarification'"),
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


class CommitteeAdminOperation(Base):
    """Immutable, secret-free evidence for local committee administration."""

    __tablename__ = "committee_admin_operation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_type: Mapped[str] = mapped_column(String)
    committee_id: Mapped[int] = mapped_column(ForeignKey("committee.id", ondelete="RESTRICT"))
    person_ids_json: Mapped[str] = mapped_column(String)
    membership_ids_json: Mapped[str] = mapped_column(String)
    account_ids_json: Mapped[str] = mapped_column(String)
    result: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    technical_source: Mapped[str] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    response_json: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("committee_admin_operation_committee", "committee_id", "occurred_at"),)


class AuthRecoveryCode(Base):
    """One Argon2id hash for a single-use local recovery code."""

    __tablename__ = "auth_recovery_code"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    consumed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("auth_recovery_code_account_active", "account_id", "consumed_at"),)


class ExamVenue(Base):
    """Reusable venue master data independent from individual exam rooms."""

    __tablename__ = "exam_venue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String)
    committee_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String)
    street: Mapped[str] = mapped_column(String)
    postal_code: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, server_default=sql_text("'Deutschland'"))
    site_name: Mapped[str | None] = mapped_column(String, nullable=True)
    entrance: Mapped[str | None] = mapped_column(String, nullable=True)
    travel_directions: Mapped[str | None] = mapped_column(String, nullable=True)
    is_accessible: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accessibility_status: Mapped[str] = mapped_column(
        String, server_default=sql_text("'needs_clarification'")
    )
    accessibility_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    coordinate_status: Mapped[str] = mapped_column(String, server_default=sql_text("'missing'"))
    coordinate_source: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamRoom(Base):
    """One concrete room or exam area at an :class:`ExamVenue`."""

    __tablename__ = "exam_room"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("exam_venue.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String)
    building: Mapped[str | None] = mapped_column(String, nullable=True)
    wing: Mapped[str | None] = mapped_column(String, nullable=True)
    floor: Mapped[str | None] = mapped_column(String, nullable=True)
    room_number: Mapped[str | None] = mapped_column(String, nullable=True)
    access_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamVenueContact(Base):
    """A non-authentication contact associated with one exam venue."""

    __tablename__ = "exam_venue_contact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("exam_venue.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    availability_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamVenueContactRoom(Base):
    """Optional room-specific visibility for an otherwise venue-wide contact."""

    __tablename__ = "exam_venue_contact_room"

    contact_id: Mapped[int] = mapped_column(
        ForeignKey("exam_venue_contact.id", ondelete="CASCADE"), primary_key=True
    )
    room_id: Mapped[int] = mapped_column(
        ForeignKey("exam_room.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamVenueAuditEvent(Base):
    """Append-only trace for venue, room, and contact master-data mutations."""

    __tablename__ = "exam_venue_audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[int] = mapped_column(Integer)
    entity_revision: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[str] = mapped_column(String)
    actor_kind: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    technical_actor: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    details_json: Mapped[str] = mapped_column(String, server_default=sql_text("'{}'"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamVenueMigrationReport(Base):
    """Immutable evidence produced by the legacy location migration."""

    __tablename__ = "exam_venue_migration_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    migration_name: Mapped[str] = mapped_column(String, unique=True)
    backup_reference: Mapped[str] = mapped_column(String)
    backup_verified: Mapped[int] = mapped_column(Integer)
    source_location_count: Mapped[int] = mapped_column(Integer)
    venue_count: Mapped[int] = mapped_column(Integer)
    room_count: Mapped[int] = mapped_column(Integer)
    grouped_location_count: Mapped[int] = mapped_column(Integer)
    conflict_count: Mapped[int] = mapped_column(Integer)
    clarification_count: Mapped[int] = mapped_column(Integer)
    machine_report_json: Mapped[str] = mapped_column(String)
    human_report: Mapped[str] = mapped_column(String)
    migrated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class LegacyLocationRoomMapping(Base):
    """Permanent mapping from every legacy location identity to its new room."""

    __tablename__ = "legacy_location_room_mapping"

    legacy_location_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("exam_venue.id", ondelete="RESTRICT"))
    room_id: Mapped[int] = mapped_column(
        ForeignKey("exam_room.id", ondelete="RESTRICT"), unique=True
    )
    migration_report_id: Mapped[int] = mapped_column(
        ForeignKey("exam_venue_migration_report.id", ondelete="RESTRICT")
    )
    migrated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


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
    legacy_status: Mapped[str | None] = mapped_column(String, nullable=True)
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
    revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    lifecycle_status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    legacy_status: Mapped[str | None] = mapped_column(String, nullable=True)
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


class ExamRoundDecision(Base):
    """Immutable evidence for one close, cancellation, or repeated decision."""

    __tablename__ = "exam_round_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    decision_type: Mapped[str] = mapped_column(String)
    requested_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    checklist_json: Mapped[str] = mapped_column(String)
    snapshot_json: Mapped[str] = mapped_column(String)
    previous_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round_decision.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'current'"))
    command_fingerprint: Mapped[str] = mapped_column(String)
    decided_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index(
            "exam_round_decision_revision",
            "exam_round_id",
            "resulting_revision",
            unique=True,
        ),
        Index(
            "exam_round_decision_command",
            "exam_round_id",
            "command_fingerprint",
            unique=True,
        ),
    )


class ExamRoundReopening(Base):
    """One bounded correction window for a terminal exam round."""

    __tablename__ = "exam_round_reopening"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    previous_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round_decision.id", ondelete="RESTRICT"), nullable=True
    )
    requested_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    occasion: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    requested_scope_json: Mapped[str] = mapped_column(String)
    scope_json: Mapped[str] = mapped_column(String)
    impacts_json: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    command_fingerprint: Mapped[str] = mapped_column(String)
    opened_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("exam_round_reopening_open", "exam_round_id", "status"),
        Index(
            "exam_round_reopening_command",
            "exam_round_id",
            "command_fingerprint",
            unique=True,
        ),
    )


class ExamRoundTask(Base):
    """A durable follow-up task caused by a round reopening."""

    __tablename__ = "exam_round_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    reopening_id: Mapped[int] = mapped_column(
        ForeignKey("exam_round_reopening.id", ondelete="CASCADE")
    )
    recipient_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="CASCADE")
    )
    task_type: Mapped[str] = mapped_column(String)
    origin_key: Mapped[str] = mapped_column(String)
    details_json: Mapped[str] = mapped_column(String, server_default=sql_text("'{}'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "exam_round_task_origin",
            "recipient_member_id",
            "task_type",
            "origin_key",
            unique=True,
        ),
        Index("exam_round_task_round_status", "exam_round_id", "status"),
    )


class ExamRoundAuditEvent(Base):
    """Append-only lifecycle history for one committee-specific round."""

    __tablename__ = "exam_round_audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    round_revision: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round_decision.id", ondelete="RESTRICT"), nullable=True
    )
    reopening_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round_reopening.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    scope_json: Mapped[str] = mapped_column(String, server_default=sql_text("'[]'"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("exam_round_audit_history", "exam_round_id", "id"),)


class ExamRoundExport(Base):
    """Trace of a human or machine export and its later obsolescence."""

    __tablename__ = "exam_round_export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round_decision.id", ondelete="RESTRICT"), nullable=True
    )
    round_revision: Mapped[int] = mapped_column(Integer)
    export_kind: Mapped[str] = mapped_column(String)
    lifecycle_status: Mapped[str] = mapped_column(String)
    generated_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    generated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    superseded_at: Mapped[str | None] = mapped_column(String, nullable=True)
    superseded_by_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("exam_round_export_history", "exam_round_id", "generated_at"),)


class ExamRoundIhkStatus(Base):
    """Append-only documentation of a later formal IHK process state."""

    __tablename__ = "exam_round_ihk_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="RESTRICT"))
    document_status: Mapped[str] = mapped_column(String)
    document_reference: Mapped[str] = mapped_column(String)
    recorded_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    command_fingerprint: Mapped[str] = mapped_column(String, unique=True)
    recorded_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (Index("exam_round_ihk_status_history", "exam_round_id", "id"),)


class ConfirmedPlanRevision(Base):
    """Immutable audit record for one revision of a confirmed exam plan."""

    __tablename__ = "confirmed_plan_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id", ondelete="CASCADE"))
    previous_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    before_state_json: Mapped[str] = mapped_column(String)
    after_state_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("confirmed_plan_revision_history", "exam_round_id", "resulting_revision"),
        Index("confirmed_plan_revision_unique", "exam_round_id", "resulting_revision", unique=True),
    )


class PlanConsequenceBatch(Base):
    """Derivation state for one immutable domain origin."""

    __tablename__ = "plan_consequence_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_type: Mapped[str] = mapped_column(String)
    origin_key: Mapped[str] = mapped_column(String)
    confirmed_plan_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("confirmed_plan_revision.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    notification_scope_json: Mapped[str] = mapped_column(String, server_default=sql_text("'[]'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    next_attempt_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("plan_consequence_batch_origin", "origin_type", "origin_key", unique=True),
    )


class PlanConsequence(Base):
    """One recipient-specific notification or calendar consequence."""

    __tablename__ = "plan_consequence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("plan_consequence_batch.id", ondelete="CASCADE")
    )
    recipient_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="CASCADE")
    )
    consequence_type: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    identity_key: Mapped[str] = mapped_column(String)
    details_json: Mapped[str] = mapped_column(String, server_default=sql_text("'{}'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    next_attempt_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    calendar_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("calendar_event.id", ondelete="SET NULL"), nullable=True
    )
    calendar_event_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index(
            "plan_consequence_identity",
            "batch_id",
            "recipient_member_id",
            "consequence_type",
            "identity_key",
            unique=True,
        ),
        Index("plan_consequence_due", "status", "next_attempt_at", "id"),
    )


class RoundCandidate(Base):
    __tablename__ = "round_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    requires_mep: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    is_active: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    terminal_status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    terminal_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_new_round_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_round.id", ondelete="RESTRICT"), nullable=True
    )
    postponed_until: Mapped[str | None] = mapped_column(String, nullable=True)
    ihk_decision_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    terminal_at: Mapped[str | None] = mapped_column(String, nullable=True)
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
    default_room_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_room.id"),
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
    room_id: Mapped[int] = mapped_column(ForeignKey("exam_room.id"))
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
    revision: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    closure_status: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'open'"),
    )
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )


class ExamDayClosure(Base):
    """Immutable evidence for one formal close or re-close decision."""

    __tablename__ = "exam_day_closure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    requested_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    closure_type: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    clarification_attempts: Mapped[str | None] = mapped_column(String, nullable=True)
    checklist_json: Mapped[str] = mapped_column(String)
    warnings_json: Mapped[str] = mapped_column(String)
    protocol_references_json: Mapped[str] = mapped_column(String)
    result_references_json: Mapped[str] = mapped_column(String)
    previous_closure_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_closure.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'current'"))
    command_fingerprint: Mapped[str] = mapped_column(String)
    closed_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("exam_day_closure_revision", "exam_day_id", "resulting_revision", unique=True),
        Index("exam_day_closure_command", "exam_day_id", "command_fingerprint", unique=True),
    )


class ExamDayReopening(Base):
    """One bounded correction window for a closed or historical exam day."""

    __tablename__ = "exam_day_reopening"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    previous_closure_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_closure.id", ondelete="RESTRICT"), nullable=True
    )
    requested_revision: Mapped[int] = mapped_column(Integer)
    resulting_revision: Mapped[int] = mapped_column(Integer)
    occasion: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    requested_scope_json: Mapped[str] = mapped_column(String)
    scope_json: Mapped[str] = mapped_column(String)
    completed_scope_json: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("'[]'"),
    )
    impacts_json: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    command_fingerprint: Mapped[str] = mapped_column(String)
    opened_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("exam_day_reopening_open", "exam_day_id", "status"),
        Index("exam_day_reopening_command", "exam_day_id", "command_fingerprint", unique=True),
    )


class ExamDayTask(Base):
    """A durable, recipient-specific follow-up caused by a day decision."""

    __tablename__ = "exam_day_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    reopening_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_reopening.id", ondelete="CASCADE"), nullable=True
    )
    recipient_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="CASCADE")
    )
    task_type: Mapped[str] = mapped_column(String)
    origin_key: Mapped[str] = mapped_column(String)
    exam_protocol_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_protocol_revision.id", ondelete="RESTRICT"), nullable=True
    )
    result_determination_id: Mapped[int | None] = mapped_column(
        ForeignKey("result_determination.id", ondelete="RESTRICT"), nullable=True
    )
    details_json: Mapped[str] = mapped_column(String, server_default=sql_text("'{}'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "exam_day_task_origin", "recipient_member_id", "task_type", "origin_key", unique=True
        ),
        Index("exam_day_task_day_status", "exam_day_id", "status"),
    )


class ExamDayAuditEvent(Base):
    """Append-only history for closure, reopening, correction, and late reactions."""

    __tablename__ = "exam_day_audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    day_revision: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String)
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    closure_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_closure.id", ondelete="RESTRICT"), nullable=True
    )
    reopening_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_reopening.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    scope_json: Mapped[str] = mapped_column(String, server_default=sql_text("'[]'"))
    created_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("exam_day_audit_history", "exam_day_id", "id"),)


class ExamDayExport(Base):
    """Metadata proving that a closure state was exported without changing it."""

    __tablename__ = "exam_day_export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    closure_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_closure.id", ondelete="RESTRICT"), nullable=True
    )
    export_kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    generated_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    generated_at: Mapped[str] = mapped_column(
        String,
        server_default=sql_text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("exam_day_export_history", "exam_day_id", "generated_at"),)


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


class AbsenceReport(Base):
    """One immutable-in-history report for an assigned committee member."""

    __tablename__ = "absence_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_day_id: Mapped[int] = mapped_column(ForeignKey("exam_day.id", ondelete="CASCADE"))
    exam_day_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("exam_day_assignment.id", ondelete="RESTRICT")
    )
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    reported_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    reported_at: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'reported'"))
    selected_replacement_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("absence_report_day_status", "exam_day_id", "status"),
        Index("absence_report_assignment_active", "exam_day_assignment_id", "status"),
    )


class ReplacementResponse(Base):
    """A member's answer to one replacement request."""

    __tablename__ = "replacement_response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    absence_report_id: Mapped[int] = mapped_column(
        ForeignKey("absence_report.id", ondelete="CASCADE")
    )
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    response: Mapped[str] = mapped_column(String, server_default=sql_text("'pending'"))
    requested_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    urgent: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    responded_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "replacement_response_report_member",
            "absence_report_id",
            "committee_member_id",
            unique=True,
        ),
    )


class AbsenceAuditEvent(Base):
    """Append-only process history; current state never replaces past events."""

    __tablename__ = "absence_audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    absence_report_id: Mapped[int] = mapped_column(
        ForeignKey("absence_report.id", ondelete="CASCADE")
    )
    actor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String)
    from_status: Mapped[str | None] = mapped_column(String, nullable=True)
    to_status: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (Index("absence_audit_report_created", "absence_report_id", "created_at"),)


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


class ExamProtocol(Base):
    """One shared protocol for one exam that actually started."""

    __tablename__ = "exam_protocol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_slot_id: Mapped[int] = mapped_column(
        ForeignKey("exam_slot.id", ondelete="CASCADE"), unique=True
    )
    current_version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    created_by_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    source: Mapped[str] = mapped_column(String, server_default=sql_text("'application'"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamProtocolParticipant(Base):
    """Immutable snapshot of an examiner who actually participated at start."""

    __tablename__ = "exam_protocol_participant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol.id", ondelete="CASCADE")
    )
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "exam_protocol_participant_unique",
            "exam_protocol_id",
            "committee_member_id",
            unique=True,
        ),
    )


class ExamProtocolRevision(Base):
    """Immutable content version; reactions always target exactly one revision."""

    __tablename__ = "exam_protocol_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    declaration: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_state: Mapped[str] = mapped_column(String, server_default=sql_text("'draft'"))
    previous_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_protocol_revision.id", ondelete="RESTRICT"), nullable=True
    )
    correction_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_protocol_correction_request.id", ondelete="RESTRICT"), nullable=True
    )
    changed_by_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_by_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    submitted_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "exam_protocol_revision_unique",
            "exam_protocol_id",
            "version",
            unique=True,
        ),
    )


class ExamProtocolEntry(Base):
    """One structured fact or procedural deviation in a protocol revision."""

    __tablename__ = "exam_protocol_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_revision_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol_revision.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String)
    statement: Mapped[str] = mapped_column(String)
    occurred_from: Mapped[str] = mapped_column(String)
    occurred_to: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (Index("exam_protocol_entry_revision", "exam_protocol_revision_id", "id"),)


class ExamProtocolResponse(Base):
    """One participant confirmation or reservation for one immutable revision."""

    __tablename__ = "exam_protocol_response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_revision_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol_revision.id", ondelete="CASCADE")
    )
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    response: Mapped[str] = mapped_column(String)
    exam_protocol_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_protocol_entry.id", ondelete="RESTRICT"), nullable=True
    )
    statement: Mapped[str | None] = mapped_column(String, nullable=True)
    responded_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "exam_protocol_response_unique",
            "exam_protocol_revision_id",
            "committee_member_id",
            unique=True,
        ),
    )


class ExamProtocolCorrectionRequest(Base):
    """A participant-reported need that management may open as a correction."""

    __tablename__ = "exam_protocol_correction_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol.id", ondelete="CASCADE")
    )
    exam_protocol_revision_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol_revision.id", ondelete="RESTRICT")
    )
    requested_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'pending'"))
    requested_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    opened_by_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    opened_at: Mapped[str | None] = mapped_column(String, nullable=True)
    reopening_reference: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "exam_protocol_correction_protocol_status",
            "exam_protocol_id",
            "status",
        ),
    )


class ExamProtocolRetention(Base):
    """Locally configured retention rule and effective preservation hold."""

    __tablename__ = "exam_protocol_retention"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_protocol_id: Mapped[int] = mapped_column(
        ForeignKey("exam_protocol.id", ondelete="CASCADE"), unique=True
    )
    rule_reference: Mapped[str] = mapped_column(String)
    retain_until: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_hold: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    hold_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class AssessmentModelVersion(Base):
    """Immutable, rule-bound assessment model used by one or more exam rounds."""

    __tablename__ = "assessment_model_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_key: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    ihk: Mapped[str] = mapped_column(String)
    occupation: Mapped[str] = mapped_column(String)
    specialization: Mapped[str | None] = mapped_column(String, nullable=True)
    training_regulation: Mapped[str] = mapped_column(String)
    exam_regulation: Mapped[str] = mapped_column(String)
    ihk_guidelines: Mapped[str] = mapped_column(String)
    valid_from: Mapped[str] = mapped_column(String)
    valid_until: Mapped[str | None] = mapped_column(String, nullable=True)
    official_scale_min: Mapped[str] = mapped_column(String, server_default=sql_text("'0'"))
    official_scale_max: Mapped[str] = mapped_column(String, server_default=sql_text("'100'"))
    rules_json: Mapped[str] = mapped_column(String)
    retention_rule_reference: Mapped[str] = mapped_column(String)
    retention_years: Mapped[int] = mapped_column(Integer, server_default=sql_text("15"))
    created_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("assessment_model_identity", "model_key", "version", unique=True),
        Index(
            "assessment_model_applicability",
            "ihk",
            "occupation",
            "specialization",
            "valid_from",
            "valid_until",
        ),
    )


class ExamRoundAssessmentBinding(Base):
    """Explicit version binding that becomes immutable after the first assessment."""

    __tablename__ = "exam_round_assessment_binding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_round_id: Mapped[int] = mapped_column(
        ForeignKey("exam_round.id", ondelete="CASCADE"), unique=True
    )
    assessment_model_version_id: Mapped[int] = mapped_column(
        ForeignKey("assessment_model_version.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    bound_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    binding_reason: Mapped[str] = mapped_column(String)
    bound_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ExamResult(Base):
    """Candidate result process; current state points only at immutable history."""

    __tablename__ = "exam_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("round_candidate.id", ondelete="CASCADE"), unique=True
    )
    current_state: Mapped[str] = mapped_column(String, server_default=sql_text("'incomplete'"))
    correction_open: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    source: Mapped[str] = mapped_column(String, server_default=sql_text("'application'"))
    legacy_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class IndividualAssessment(Base):
    """One immutable revision of one examiner's criterion-specific assessment."""

    __tablename__ = "individual_assessment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    component_key: Mapped[str] = mapped_column(String)
    criterion_key: Mapped[str] = mapped_column(String)
    assessor_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    revision: Mapped[int] = mapped_column(Integer)
    raw_points: Mapped[str] = mapped_column(String)
    normalized_points: Mapped[str] = mapped_column(String)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    previous_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("individual_assessment.id", ondelete="RESTRICT"), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    submitted_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "individual_assessment_revision",
            "exam_result_id",
            "component_key",
            "criterion_key",
            "assessor_member_id",
            "revision",
            unique=True,
        ),
        Index(
            "individual_assessment_current",
            "exam_result_id",
            "component_key",
            "assessor_member_id",
            "status",
        ),
    )


class AssessmentDisclosure(Base):
    """Controlled opening of previously hidden individual contributions."""

    __tablename__ = "assessment_disclosure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    component_key: Mapped[str] = mapped_column(String)
    disclosed_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    disclosed_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("assessment_disclosure_component", "exam_result_id", "component_key", unique=True),
    )


class CommitteeAssessment(Base):
    """Immutable revision of a properly determined joint component assessment."""

    __tablename__ = "committee_assessment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    component_key: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    points: Mapped[str] = mapped_column(String)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    participant_member_ids_json: Mapped[str] = mapped_column(String)
    vote_json: Mapped[str] = mapped_column(String)
    dissent_json: Mapped[str] = mapped_column(String, server_default=sql_text("'[]'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'current'"))
    previous_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_assessment.id", ondelete="RESTRICT"), nullable=True
    )
    determined_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    determined_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "committee_assessment_revision",
            "exam_result_id",
            "component_key",
            "revision",
            unique=True,
        ),
    )


class ExternalExamResult(Base):
    """Versioned externally determined input with independent confirmation."""

    __tablename__ = "external_exam_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    area_key: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    points: Mapped[str] = mapped_column(String)
    grade: Mapped[str | None] = mapped_column(String, nullable=True)
    professional_status: Mapped[str] = mapped_column(String)
    determining_authority: Mapped[str] = mapped_column(String)
    source_reference: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'unconfirmed'"))
    recorded_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    recorded_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    confirmed_by_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_external_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("external_exam_result.id", ondelete="RESTRICT"), nullable=True
    )
    correction_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "external_exam_result_revision",
            "exam_result_id",
            "area_key",
            "revision",
            unique=True,
        ),
    )


class ResultCalculation(Base):
    """Immutable, reproducible proposal; calculation never means determination."""

    __tablename__ = "result_calculation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    input_fingerprint: Mapped[str] = mapped_column(String)
    total_points: Mapped[str] = mapped_column(String)
    grade: Mapped[str] = mapped_column(String)
    passed: Mapped[int] = mapped_column(Integer)
    calculation_path_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("result_calculation_version", "exam_result_id", "version", unique=True),
        Index("result_calculation_input", "exam_result_id", "input_fingerprint", unique=True),
    )


class ResultDetermination(Base):
    """Immutable committee decision that can only be superseded by a new decision."""

    __tablename__ = "result_determination"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    result_calculation_id: Mapped[int] = mapped_column(
        ForeignKey("result_calculation.id", ondelete="RESTRICT")
    )
    participant_member_ids_json: Mapped[str] = mapped_column(String)
    vote_json: Mapped[str] = mapped_column(String)
    dissent_json: Mapped[str] = mapped_column(String, server_default=sql_text("'[]'"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'current'"))
    previous_determination_id: Mapped[int | None] = mapped_column(
        ForeignKey("result_determination.id", ondelete="RESTRICT"), nullable=True
    )
    correction_id: Mapped[int | None] = mapped_column(
        ForeignKey("result_correction.id", ondelete="RESTRICT"), nullable=True
    )
    determined_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    determined_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("result_determination_revision", "exam_result_id", "revision", unique=True),
    )


class ResultRecordConfirmation(Base):
    """One participant's confirmation of one immutable result record."""

    __tablename__ = "result_record_confirmation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_determination_id: Mapped[int] = mapped_column(
        ForeignKey("result_determination.id", ondelete="CASCADE")
    )
    committee_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    confirmed_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index(
            "result_record_confirmation_member",
            "result_determination_id",
            "committee_member_id",
            unique=True,
        ),
    )


class ResultCorrection(Base):
    """Reasoned correction process; the effective determination remains immutable."""

    __tablename__ = "result_correction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    result_determination_id: Mapped[int] = mapped_column(
        ForeignKey("result_determination.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(String)
    requested_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'open'"))
    reopening_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("result_correction_status", "exam_result_id", "status"),)


class ResultCommunication(Base):
    """Documented communication, separate from official IHK notification."""

    __tablename__ = "result_communication"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    result_determination_id: Mapped[int] = mapped_column(
        ForeignKey("result_determination.id", ondelete="RESTRICT")
    )
    method: Mapped[str] = mapped_column(String)
    responsible_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    communicated_at: Mapped[str] = mapped_column(String)
    external_document_status: Mapped[str | None] = mapped_column(String, nullable=True)
    external_document_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'current'"))
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ResultRetention(Base):
    """Effective retention start, minimum end, and preservation hold."""

    __tablename__ = "result_retention"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(
        ForeignKey("exam_result.id", ondelete="CASCADE"), unique=True
    )
    rule_reference: Mapped[str] = mapped_column(String)
    period_start: Mapped[str | None] = mapped_column(String, nullable=True)
    retain_until: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_hold: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    hold_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class ResultExport(Base):
    """Trace of generated draft or determined exports and their later obsolescence."""

    __tablename__ = "result_export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_result_id: Mapped[int] = mapped_column(ForeignKey("exam_result.id", ondelete="CASCADE"))
    result_determination_id: Mapped[int | None] = mapped_column(
        ForeignKey("result_determination.id", ondelete="RESTRICT"), nullable=True
    )
    export_kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    generated_by_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="RESTRICT")
    )
    generated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


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
    superseded_at: Mapped[str | None] = mapped_column(String, nullable=True)
    superseded_by_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("confirmed_plan_revision.id", ondelete="SET NULL"), nullable=True
    )
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
    claim_token: Mapped[str | None] = mapped_column(String, nullable=True)
    claimed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    claim_expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))


class CalendarFeed(Base):
    """Opaque personal feed credential; only its digest is persisted."""

    __tablename__ = "calendar_feed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("calendar_feed_person", "person_id", unique=True),)


class CalendarEvent(Base):
    """Dataminimized, versioned snapshot exposed through ICS."""

    __tablename__ = "calendar_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_event_id: Mapped[str] = mapped_column(String, unique=True)
    exam_half_year_id: Mapped[int] = mapped_column(ForeignKey("exam_half_year.id"))
    exam_round_id: Mapped[int] = mapped_column(ForeignKey("exam_round.id"))
    exam_day_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day.id", ondelete="SET NULL"), nullable=True
    )
    exam_day_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_day_assignment.id", ondelete="SET NULL"), nullable=True
    )
    recipient_member_id: Mapped[int] = mapped_column(
        ForeignKey("committee_member.id", ondelete="CASCADE")
    )
    date: Mapped[str] = mapped_column(String)
    starts_at: Mapped[str] = mapped_column(String)
    ends_at: Mapped[str] = mapped_column(String)
    time_zone: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    round_name: Mapped[str] = mapped_column(String)
    secure_reference: Mapped[str] = mapped_column(String)
    source_key: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    status: Mapped[str] = mapped_column(String, server_default=sql_text("'sent'"))
    content_hash: Mapped[str] = mapped_column(String)
    sent_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("calendar_event_source", "source_key"),
        Index("calendar_event_recipient_period", "recipient_member_id", "exam_half_year_id"),
        Index("calendar_event_status", "status"),
    )


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
    fields=(
        "name",
        "occupation",
        "ihk",
        "is_active",
        "bootstrap_state",
        "created_at",
        "updated_at",
    ),
    order_by=("name",),
    writable_fields=("name", "occupation", "ihk"),
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

EXAM_VENUE = Resource(
    model=ExamVenue,
    fields=(
        "scope",
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
        "latitude",
        "longitude",
        "coordinate_status",
        "coordinate_source",
        "is_active",
        "revision",
        "created_at",
        "updated_at",
    ),
    order_by=("-is_active", "name", "id"),
    writable_fields=(
        "scope",
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
        "latitude",
        "longitude",
        "coordinate_status",
        "coordinate_source",
        "is_active",
    ),
)

EXAM_ROOM = Resource(
    model=ExamRoom,
    fields=(
        "venue_id",
        "name",
        "building",
        "wing",
        "floor",
        "room_number",
        "access_notes",
        "capacity",
        "is_active",
        "revision",
        "created_at",
        "updated_at",
    ),
    order_by=("-is_active", "name", "id"),
    writable_fields=(
        "venue_id",
        "name",
        "building",
        "wing",
        "floor",
        "room_number",
        "access_notes",
        "capacity",
        "is_active",
    ),
)

EXAM_VENUE_CONTACT = Resource(
    model=ExamVenueContact,
    fields=(
        "venue_id",
        "label",
        "role",
        "phone",
        "email",
        "availability_notes",
        "is_active",
        "revision",
        "created_at",
        "updated_at",
    ),
    order_by=("-is_active", "label", "id"),
    writable_fields=(
        "venue_id",
        "label",
        "role",
        "phone",
        "email",
        "availability_notes",
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
        "revision",
        "lifecycle_status",
        "legacy_status",
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
    fields=("season", "year", "status", "legacy_status", "created_at", "updated_at"),
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
        "terminal_status",
        "terminal_reason",
        "effective_new_round_id",
        "postponed_until",
        "ihk_decision_reference",
        "terminal_at",
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
        "terminal_status",
        "terminal_reason",
        "effective_new_round_id",
        "postponed_until",
        "ihk_decision_reference",
        "terminal_at",
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
        "default_room_id",
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
        "default_room_id",
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
        "room_id",
        "date",
        "status",
        "revision",
        "closure_status",
        "lunch_break_enabled",
        "created_from_proposal",
        "created_at",
        "updated_at",
    ),
    order_by=("date",),
    writable_fields=(
        "exam_round_id",
        "room_id",
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

ABSENCE_REPORT = Resource(
    model=AbsenceReport,
    fields=(
        "exam_day_id",
        "exam_day_assignment_id",
        "committee_member_id",
        "reported_by_member_id",
        "reported_at",
        "reason",
        "status",
        "selected_replacement_member_id",
        "version",
        "created_at",
        "updated_at",
    ),
    order_by=("-reported_at", "-id"),
    writable_fields=(),
)

REPLACEMENT_RESPONSE = Resource(
    model=ReplacementResponse,
    fields=(
        "absence_report_id",
        "committee_member_id",
        "response",
        "requested_at",
        "expires_at",
        "urgent",
        "responded_at",
        "created_at",
        "updated_at",
    ),
    order_by=("requested_at", "id"),
    writable_fields=(),
)

ABSENCE_AUDIT_EVENT = Resource(
    model=AbsenceAuditEvent,
    fields=(
        "absence_report_id",
        "actor_member_id",
        "event_type",
        "from_status",
        "to_status",
        "details",
        "created_at",
    ),
    order_by=("created_at", "id"),
    writable_fields=(),
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
