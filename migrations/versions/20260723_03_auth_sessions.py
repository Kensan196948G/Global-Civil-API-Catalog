"""auth_requests + sessions tables and catalog_entries.deleted_at (Phase B)

Revision ID: 20260723_03
Revises: 20260723_02
Create Date: 2026-07-23

Additive only: two new tables for the OIDC login flow (design §3.1) and the
logical-delete column backing FR-012 (design §2.2/§4.2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "20260723_03"
down_revision = "20260723_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_requests",
        sa.Column("state", sa.Text(), primary_key=True),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_sub", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("roles", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "catalog_entries",
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("catalog_entries", "deleted_at")
    op.drop_table("sessions")
    op.drop_table("auth_requests")
