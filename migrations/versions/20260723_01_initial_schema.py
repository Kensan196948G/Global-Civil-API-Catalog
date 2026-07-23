"""initial schema: catalog_entries + verification_results (design §2.1)

Revision ID: 20260723_01
Revises:
Create Date: 2026-07-23

The PostGIS extension must already exist on the target database
(enabled at project provisioning; ``CREATE EXTENSION`` needs owner
rights and is an infrastructure step, not a schema migration).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "20260723_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_entries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("sub_category", sa.Text()),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("region", sa.Text()),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("document_url", sa.Text(), nullable=False),
        sa.Column("endpoint_template", sa.Text()),
        sa.Column("sample_endpoint", sa.Text()),
        sa.Column("data_formats", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("api_key_required", sa.Text(), nullable=False),
        sa.Column("auth_type", sa.Text()),
        sa.Column("license_note", sa.Text()),
        sa.Column("commercial_use", sa.Text()),
        sa.Column("update_frequency", sa.Text()),
        sa.Column("connection_status", sa.Text(), nullable=False),
        sa.Column("trust_rank", sa.Text()),
        sa.Column("connection_priority", sa.Integer()),
        sa.Column("business_fit_score", sa.Integer()),
        sa.Column("integration_score", sa.Integer()),
        sa.Column("score_breakdown", JSONB()),
        sa.Column("tags", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("usage_summary", sa.Text()),
        sa.Column("usage_notes", sa.Text()),
        sa.Column("risk_note", sa.Text()),
        sa.Column("last_checked_at", sa.Date()),
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
            "api_key_required IN ('required','not_required','unknown')",
            name="ck_catalog_entries_api_key_required",
        ),
        sa.CheckConstraint(
            "trust_rank IN ('A','B','C','D','E')",
            name="ck_catalog_entries_trust_rank",
        ),
    )
    # PostGIS geometry column (design AD-1). Added via raw DDL so the ORM
    # does not need a GeoAlchemy2 dependency until the column is used.
    op.execute("ALTER TABLE catalog_entries ADD COLUMN geom geometry(Geometry, 4326)")

    op.create_table(
        "verification_results",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "api_id",
            sa.Text(),
            sa.ForeignKey("catalog_entries.id"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("response_size_bytes", sa.Integer()),
        sa.Column("record_count", sa.Integer()),
        sa.Column(
            "sample_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "result IN ('success','failure','warning','skipped')",
            name="ck_verification_results_result",
        ),
    )
    op.create_index(
        "ix_verification_results_api_id_verified_at",
        "verification_results",
        ["api_id", "verified_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_verification_results_api_id_verified_at", table_name="verification_results")
    op.drop_table("verification_results")
    op.drop_table("catalog_entries")
