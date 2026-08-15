"""SQLAlchemy persistence schema containing only pending operational data."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from rejoinlater.domain import DeliveryMethod, PauseReason, ReturnMode, Visibility


class Base(DeclarativeBase):
    """Declarative base for the minimal operational schema."""


class BreakRecord(Base):
    """One not-yet-finished return; completed rows are permanently deleted."""

    __tablename__ = "break_records"
    __table_args__ = (
        UniqueConstraint("user_lookup_hash", "chat_lookup_hash", name="uq_break_user_chat"),
        CheckConstraint(
            "mode <> 'public' OR public_locator_enc IS NOT NULL",
            name="ck_public_locator_required",
        ),
        Index("ix_break_user_lookup", "user_lookup_hash"),
        Index("ix_break_chat_lookup", "chat_lookup_hash"),
        Index(
            "ix_break_due_pending",
            "return_at",
            postgresql_where=text("delivery_sent = false AND delivery_paused = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mode: Mapped[ReturnMode] = mapped_column(
        Enum(
            ReturnMode,
            name="return_mode",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(
            Visibility,
            name="visibility",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    user_id_enc: Mapped[bytes] = mapped_column(LargeBinary)
    user_lookup_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    chat_id_enc: Mapped[bytes] = mapped_column(LargeBinary)
    chat_lookup_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    public_locator_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    return_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivery_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    delivery_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_method: Mapped[DeliveryMethod | None] = mapped_column(
        Enum(
            DeliveryMethod,
            name="delivery_method",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    delivery_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    pause_reason: Mapped[PauseReason | None] = mapped_column(
        Enum(
            PauseReason,
            name="pause_reason",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPreference(Base):
    """Minimal private-chat activation and locale state."""

    __tablename__ = "user_preferences"

    user_lookup_hash: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id_enc: Mapped[bytes] = mapped_column(LargeBinary)
    language_code: Mapped[str] = mapped_column(String(2), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AggregateCounter(Base):
    """Unlinkable all-time counter with no identifiers or operation timestamps."""

    __tablename__ = "aggregate_counters"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)
