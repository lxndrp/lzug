"""Persistence schema owned by Application's durable follow-up workflow."""

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from backend.persistence.models import Base


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
