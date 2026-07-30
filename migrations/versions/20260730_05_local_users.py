"""local_users table — username/password login (auth mode ``local``)

Revision ID: 20260730_05
Revises: 20260723_04
Create Date: 2026-07-30

Additive only: one new table. Passwords are stored as scrypt hashes
(stdlib, per-user salt); the OIDC tables from 20260723_03 stay untouched
so both auth modes can coexist behind CATALOG_AUTH_MODE.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_05"
down_revision = "20260723_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_users",
        sa.Column("username", sa.Text(), primary_key=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('Catalog.Admin', 'Catalog.Editor', 'Catalog.Verifier',"
            " 'Catalog.Approver', 'Catalog.Viewer')",
            name="ck_local_users_role",
        ),
    )


def downgrade() -> None:
    op.drop_table("local_users")
