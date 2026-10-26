"""Persistence schema owned by Application's durable follow-up workflow."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models import Base


class AbsenceConsequenceCutover(Base):
    """Persist the last legacy audit excluded from automatic replay."""

    __tablename__ = "absence_consequence_cutover"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_watermark: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(String)

    __table_args__ = (CheckConstraint("id = 1"),)


class AbsenceConsequenceSource(Base):
    """Immutable, minimized source for one committed absence follow-up."""

    __tablename__ = "absence_consequence_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_id: Mapped[str] = mapped_column(String, unique=True)
    audit_event_id: Mapped[int] = mapped_column(
        ForeignKey("absence_audit_event.id", ondelete="RESTRICT"), unique=True
    )
    absence_report_id: Mapped[int] = mapped_column(
        ForeignKey("absence_report.id", ondelete="RESTRICT")
    )
    report_version: Mapped[int] = mapped_column(Integer)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("exam_day_assignment.id", ondelete="RESTRICT")
    )
    assignment_revision: Mapped[int] = mapped_column(Integer)
    source_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)

    __table_args__ = (
        CheckConstraint("report_version >= 0"),
        CheckConstraint("assignment_revision >= 1"),
        CheckConstraint("json_valid(source_json)"),
        Index("absence_consequence_source_report", "absence_report_id", "report_version"),
    )


class PlanConsequenceBatch(Base):
    """Application-owned processing state for one immutable source origin."""

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
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        Index("plan_consequence_batch_origin", "origin_type", "origin_key", unique=True),
    )


class PlanConsequence(Base):
    """Application-owned processing state for one recipient-specific follow-up."""

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
    created_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(String, server_default=sql_text("CURRENT_TIMESTAMP"))

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
