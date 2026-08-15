"""Create the minimal pending-return schema.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

return_mode = sa.Enum("managed", "public", name="return_mode")
visibility = sa.Enum("hidden", "visible", name="visibility")
delivery_method = sa.Enum("managed_invite", "public_link", name="delivery_method")
pause_reason = sa.Enum("blocked", "unavailable", name="pause_reason")


def upgrade() -> None:
    """Create operational rows, preferences, and unlinkable aggregate counters."""

    op.create_table(
        "break_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", return_mode, nullable=False),
        sa.Column("visibility", visibility, nullable=False),
        sa.Column("user_id_enc", sa.LargeBinary(), nullable=False),
        sa.Column("user_lookup_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("chat_id_enc", sa.LargeBinary(), nullable=False),
        sa.Column("chat_lookup_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("public_locator_enc", sa.LargeBinary(), nullable=True),
        sa.Column("return_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("delivery_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_method", delivery_method, nullable=True),
        sa.Column("delivery_paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pause_reason", pause_reason, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "mode <> 'public' OR public_locator_enc IS NOT NULL", name="ck_public_locator_required"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_lookup_hash", "chat_lookup_hash", name="uq_break_user_chat"),
    )
    op.create_index("ix_break_user_lookup", "break_records", ["user_lookup_hash"])
    op.create_index("ix_break_chat_lookup", "break_records", ["chat_lookup_hash"])
    op.create_index("ix_break_records_return_at", "break_records", ["return_at"])
    op.create_index(
        "ix_break_due_pending",
        "break_records",
        ["return_at"],
        postgresql_where=sa.text("delivery_sent = false AND delivery_paused = false"),
    )
    op.create_table(
        "user_preferences",
        sa.Column("user_lookup_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("user_id_enc", sa.LargeBinary(), nullable=False),
        sa.Column("language_code", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("user_lookup_hash"),
    )
    op.create_table(
        "aggregate_counters",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop all application state and enum types."""

    op.drop_table("aggregate_counters")
    op.drop_table("user_preferences")
    op.drop_index("ix_break_due_pending", table_name="break_records")
    op.drop_index("ix_break_records_return_at", table_name="break_records")
    op.drop_index("ix_break_chat_lookup", table_name="break_records")
    op.drop_index("ix_break_user_lookup", table_name="break_records")
    op.drop_table("break_records")
    bind = op.get_bind()
    pause_reason.drop(bind, checkfirst=True)
    delivery_method.drop(bind, checkfirst=True)
    visibility.drop(bind, checkfirst=True)
    return_mode.drop(bind, checkfirst=True)
