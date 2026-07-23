"""GIST spatial index on catalog_entries.geom (CodeRabbit follow-up, PR #57)

Revision ID: 20260723_02
Revises: 20260723_01
Create Date: 2026-07-23

The column is all-NULL today, so the index is cheap to build now and
ready before spatial data arrives in Phase D (epic #48).
"""

from __future__ import annotations

from alembic import op

revision = "20260723_02"
down_revision = "20260723_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_catalog_entries_geom ON catalog_entries USING gist (geom)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_catalog_entries_geom")
