"""initial schema

Revision ID: eba9c025085d
Revises:
Create Date: 2026-09-27 23:25:32.907548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eba9c025085d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column("twilio_call_sid", sa.Text(), nullable=True, unique=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_calls_customer_id", "calls", ["customer_id"])
    op.create_index("ix_calls_status", "calls", ["status"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id"),
            nullable=False,
        ),
        sa.Column("speaker", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversation_messages_call_id", "conversation_messages", ["call_id"]
    )

    op.create_table(
        "requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("requirement", sa.Text(), nullable=True),
        sa.Column("ro_capacity", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("budget", sa.Text(), nullable=True),
        sa.Column("timeline", sa.Text(), nullable=True),
        sa.Column("additional_requirements", sa.Text(), nullable=True),
    )

    op.create_table(
        "call_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("customer_intent", sa.Text(), nullable=True),
        sa.Column("key_requirements", postgresql.JSONB(), nullable=True),
        sa.Column("important_points", postgresql.JSONB(), nullable=True),
        sa.Column("follow_up", sa.Boolean(), nullable=True),
        sa.Column("lead_status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("call_summaries")
    op.drop_table("requirements")
    op.drop_index("ix_conversation_messages_call_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_calls_status", table_name="calls")
    op.drop_index("ix_calls_customer_id", table_name="calls")
    op.drop_table("calls")
    op.drop_table("customers")
