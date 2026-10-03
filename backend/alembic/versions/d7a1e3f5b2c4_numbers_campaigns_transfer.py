"""phone number pool, campaigns, call telephony legs, human transfer

Revision ID: d7a1e3f5b2c4
Revises: c41f7d2e9b10
Create Date: 2026-10-03 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7a1e3f5b2c4'
down_revision: Union[str, Sequence[str], None] = 'c41f7d2e9b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("business_profiles", sa.Column("transfer_number", sa.Text()))

    op.create_table(
        "phone_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Text(), nullable=False, unique=True),
        sa.Column("label", sa.Text()),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("inbound_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("outbound_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
    )
    op.create_index("ix_phone_numbers_profile_id", "phone_numbers", ["profile_id"])

    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_profiles.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("max_concurrent", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_delay_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.add_column("calls", sa.Column("from_number", sa.Text()))
    op.add_column("calls", sa.Column("to_number", sa.Text()))
    op.add_column(
        "calls",
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="SET NULL"),
        ),
    )
    op.add_column(
        "calls",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("calls", sa.Column("transferred_to", sa.Text()))
    op.create_index("ix_calls_phone_number_id", "calls", ["phone_number_id"])
    op.create_index("ix_calls_campaign_id", "calls", ["campaign_id"])

    op.create_table(
        "campaign_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="SET NULL"),
        ),
        sa.Column("last_outcome", sa.Text()),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
        sa.UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_contacts_customer"),
    )
    op.create_index(
        "ix_campaign_contacts_campaign_status", "campaign_contacts", ["campaign_id", "status"]
    )
    op.create_index("ix_campaign_contacts_customer_id", "campaign_contacts", ["customer_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_campaign_contacts_customer_id", table_name="campaign_contacts")
    op.drop_index("ix_campaign_contacts_campaign_status", table_name="campaign_contacts")
    op.drop_table("campaign_contacts")

    op.drop_index("ix_calls_campaign_id", table_name="calls")
    op.drop_index("ix_calls_phone_number_id", table_name="calls")
    for column in ("transferred_to", "campaign_id", "phone_number_id", "to_number", "from_number"):
        op.drop_column("calls", column)

    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("ix_phone_numbers_profile_id", table_name="phone_numbers")
    op.drop_table("phone_numbers")
    op.drop_column("business_profiles", "transfer_number")
