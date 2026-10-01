"""business profiles, call events, call outcome/channel, customer purpose/product

Revision ID: c41f7d2e9b10
Revises: a62a6e7d3668
Create Date: 2026-10-01 05:00:00.000000

"""
import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from audiocall.profiles import DEFAULT_RO_PROFILE

# revision identifiers, used by Alembic.
revision: str = 'c41f7d2e9b10'
down_revision: Union[str, Sequence[str], None] = 'a62a6e7d3668'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "business_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("products", sa.Text()),
        sa.Column("call_objective", sa.Text(), nullable=False),
        sa.Column("greeting", sa.Text()),
        sa.Column("language", sa.Text()),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # At most one default profile.
    op.create_index(
        "uq_business_profiles_one_default",
        "business_profiles",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    profiles = sa.table(
        "business_profiles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.Text()),
        sa.column("agent_name", sa.Text()),
        sa.column("industry", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("products", sa.Text()),
        sa.column("call_objective", sa.Text()),
        sa.column("greeting", sa.Text()),
        sa.column("language", sa.Text()),
        sa.column("fields", postgresql.JSONB()),
        sa.column("is_default", sa.Boolean()),
    )
    default_id = uuid.uuid4()
    op.bulk_insert(profiles, [{"id": default_id, "is_default": True, **DEFAULT_RO_PROFILE}])

    op.add_column("customers", sa.Column("purpose", sa.Text()))
    op.add_column("customers", sa.Column("product", sa.Text()))
    op.add_column(
        "customers",
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_profiles.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_customers_profile_id", "customers", ["profile_id"])

    op.add_column(
        "calls",
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_profiles.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_calls_profile_id", "calls", ["profile_id"])
    op.add_column(
        "calls", sa.Column("channel", sa.Text(), nullable=False, server_default="phone")
    )
    op.add_column("calls", sa.Column("outcome", sa.Text()))
    op.create_index("ix_calls_outcome", "calls", ["outcome"])

    op.add_column("requirements", sa.Column("fields", postgresql.JSONB()))
    op.add_column("call_summaries", sa.Column("follow_up_notes", sa.Text()))
    op.add_column("call_summaries", sa.Column("call_outcome", sa.Text()))

    op.create_table(
        "call_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_call_events_call_id", "call_events", ["call_id"])

    # ── Backfill existing data ───────────────────────────────────────────────
    op.execute(
        sa.text("UPDATE calls SET profile_id = :pid").bindparams(
            sa.bindparam("pid", default_id, type_=postgresql.UUID(as_uuid=True))
        )
    )
    op.execute(
        """
        UPDATE requirements SET fields = jsonb_strip_nulls(jsonb_build_object(
            'customer_name', customer_name, 'company_name', company_name,
            'requirement', requirement, 'ro_capacity', ro_capacity,
            'location', location, 'budget', budget, 'timeline', timeline,
            'additional_requirements', additional_requirements))
        """
    )
    op.execute(
        """
        UPDATE calls c SET outcome = CASE
            WHEN s.lead_status = 'interested' THEN 'qualified'
            WHEN s.lead_status = 'not_interested' THEN 'not_interested'
            WHEN s.lead_status = 'uncertain' THEN 'callback'
            WHEN c.status = 'no_answer' THEN 'no_answer'
            WHEN c.status = 'failed' THEN 'failed'
            WHEN c.error_reason = 'customer_silent' THEN 'no_conversation'
            WHEN c.status IN ('completed', 'disconnected') THEN 'incomplete'
            ELSE NULL END
        FROM calls c2 LEFT JOIN call_summaries s ON s.call_id = c2.id
        WHERE c.id = c2.id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_call_events_call_id", table_name="call_events")
    op.drop_table("call_events")
    op.drop_column("call_summaries", "call_outcome")
    op.drop_column("call_summaries", "follow_up_notes")
    op.drop_column("requirements", "fields")
    op.drop_index("ix_calls_outcome", table_name="calls")
    op.drop_column("calls", "outcome")
    op.drop_column("calls", "channel")
    op.drop_index("ix_calls_profile_id", table_name="calls")
    op.drop_column("calls", "profile_id")
    op.drop_index("ix_customers_profile_id", table_name="customers")
    op.drop_column("customers", "profile_id")
    op.drop_column("customers", "product")
    op.drop_column("customers", "purpose")
    op.drop_index("uq_business_profiles_one_default", table_name="business_profiles")
    op.drop_table("business_profiles")
