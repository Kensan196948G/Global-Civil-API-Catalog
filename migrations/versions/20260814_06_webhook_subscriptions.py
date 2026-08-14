"""webhook_subscriptions + connection_status check constraint

Revision ID: 20260814_06
Revises: 20260730_05
Create Date: 2026-08-14

Additive table for outbound event subscriptions (MVP notifications:
workflow transitions / entry lifecycle → HTTP webhook).  Also adds the
missing CHECK constraint for ``connection_status`` so the database
enforces the same 9-value vocabulary as the JSON validator
(scripts/catalog_utils.py, requirements §11).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "20260814_06"
down_revision = "20260730_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("events", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("secret", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        sa.Column("last_delivery_at", sa.DateTime(timezone=True)),
        sa.Column("last_delivery_status", sa.Text()),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(
        "ALTER TABLE catalog_entries ADD CONSTRAINT ck_catalog_entries_connection_status "
        "CHECK (connection_status IN "
        "('未調査','調査中','接続候補','接続検証済','実装接続済','本格利用候補','保留','除外','利用終了'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_entries DROP CONSTRAINT ck_catalog_entries_connection_status"
    )
    op.drop_table("webhook_subscriptions")
