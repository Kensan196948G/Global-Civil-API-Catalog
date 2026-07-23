"""audit_log + catalog_entry_versions + entry_workflow (Phase C, epic #47)

Revision ID: 20260723_04
Revises: 20260723_03
Create Date: 2026-07-23

Additive only. Existing catalog entries are backfilled as ``published`` so
the public read behaviour does not change at rollout; entries created via
the API after this migration start in ``draft`` and stay hidden from
unauthenticated reads until approved (design §4.2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "20260723_04"
down_revision = "20260723_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("seq", sa.Integer(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("actor_roles", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("record_id", sa.Text()),
        sa.Column("diff", JSONB()),
        sa.Column("reason", sa.Text()),
        sa.Column("request_id", sa.Text()),
    )
    op.create_index("ix_audit_log_record_id_at", "audit_log", ["record_id", "at"])

    op.create_table(
        "catalog_entry_versions",
        sa.Column("record_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
    )

    op.create_table(
        "entry_workflow",
        sa.Column(
            "record_id",
            sa.Text(),
            sa.ForeignKey("catalog_entries.id"),
            primary_key=True,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "state IN ('draft','in_review','pending_approval','published','rejected')",
            name="ck_entry_workflow_state",
        ),
    )
    # Grandfather every pre-existing entry as published (JSON files were the
    # reviewed system of record until now).
    op.execute(
        "INSERT INTO entry_workflow (record_id, state) SELECT id, 'published' FROM catalog_entries"
    )


def downgrade() -> None:
    op.drop_table("entry_workflow")
    op.drop_table("catalog_entry_versions")
    op.drop_index("ix_audit_log_record_id_at", table_name="audit_log")
    op.drop_table("audit_log")
