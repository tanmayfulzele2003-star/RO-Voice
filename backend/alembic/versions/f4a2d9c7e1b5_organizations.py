"""organizations (multi-company), user roles, invites, scoped settings

Every profile, customer, call, phone number and campaign now belongs to an
organization. Existing data moves into a "Default organization", and existing
admins become its owners and platform admins, so an upgraded install behaves
as before.

Revision ID: f4a2d9c7e1b5
Revises: e2b8c4d1a9f3
Create Date: 2026-10-03 12:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4a2d9c7e1b5'
down_revision: Union[str, Sequence[str], None] = 'e2b8c4d1a9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPED_TABLES = ("business_profiles", "customers", "phone_numbers", "campaigns", "calls", "admin_users")
# Setup progress was global; it now belongs to a company.
_ORG_FLAGS = ("setup_profile", "setup_completed")


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_concurrent_calls", sa.Integer()),
        _created_at(),
    )

    conn = op.get_bind()
    has_data = any(
        conn.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar()
        for table in _SCOPED_TABLES
    )
    default_org = uuid.uuid4()
    if has_data:
        conn.execute(
            sa.text("INSERT INTO organizations (id, name) VALUES (:id, 'Default organization')"),
            {"id": default_org},
        )

    for table in _SCOPED_TABLES:
        op.add_column(
            table,
            sa.Column(
                "org_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            ),
        )
        if has_data:
            conn.execute(sa.text(f"UPDATE {table} SET org_id = :id"), {"id": default_org})
        op.alter_column(table, "org_id", nullable=False)
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    op.add_column("admin_users", sa.Column("role", sa.Text(), nullable=False, server_default="owner"))
    op.alter_column("admin_users", "role", server_default=None)
    op.add_column(
        "admin_users",
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "admin_users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    # Whoever ran the install so far keeps running it.
    conn.execute(sa.text("UPDATE admin_users SET is_platform_admin = true"))

    # One default profile per company instead of one overall.
    op.drop_index("uq_business_profiles_one_default", table_name="business_profiles")
    op.create_index(
        "uq_business_profiles_one_default",
        "business_profiles",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # Settings get a scope: "platform" or an organization id.
    op.add_column(
        "app_settings", sa.Column("scope", sa.Text(), nullable=False, server_default="platform")
    )
    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.create_primary_key("app_settings_pkey", "app_settings", ["scope", "key"])
    if has_data:
        conn.execute(
            sa.text("UPDATE app_settings SET scope = :scope WHERE key = ANY(:keys)"),
            {"scope": str(default_org), "keys": list(_ORG_FLAGS)},
        )

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True)),
        _created_at(),
    )
    op.create_index("ix_invites_org_id", "invites", ["org_id"])


def downgrade() -> None:
    """Downgrade schema. Collapses back to a single company: keeps every row,
    drops which company it belonged to."""
    op.drop_index("ix_invites_org_id", table_name="invites")
    op.drop_table("invites")

    conn = op.get_bind()
    # Org-scoped settings back to the single global scope; keep one per key.
    conn.execute(
        sa.text(
            "DELETE FROM app_settings a USING app_settings b "
            "WHERE a.key = b.key AND a.scope <> 'platform' AND b.scope = 'platform'"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM app_settings a USING app_settings b "
            "WHERE a.key = b.key AND a.scope > b.scope"
        )
    )
    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.drop_column("app_settings", "scope")
    op.create_primary_key("app_settings_pkey", "app_settings", ["key"])

    op.drop_index("uq_business_profiles_one_default", table_name="business_profiles")
    # Only one default may survive the single-company index.
    conn.execute(
        sa.text(
            "UPDATE business_profiles SET is_default = false WHERE is_default AND id NOT IN "
            "(SELECT id FROM business_profiles WHERE is_default ORDER BY created_at LIMIT 1)"
        )
    )
    op.create_index(
        "uq_business_profiles_one_default",
        "business_profiles",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    for column in ("is_active", "is_platform_admin", "role"):
        op.drop_column("admin_users", column)
    for table in _SCOPED_TABLES:
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
    op.drop_table("organizations")
