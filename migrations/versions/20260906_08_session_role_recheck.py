"""sessions.last_role_check_at — periodic role re-validation (Issue #61)

Revision ID: 20260906_08
Revises: 20260906_07
Create Date: 2026-09-06

Renumbered/rechained at merge time: PR #95 (epic #48, owner/steward/
lifecycle_status) independently created a migration also numbered
``20260906_07`` off the same ``20260814_06`` head and merged to main
first. This file was renamed and its ``down_revision`` retargeted to
``20260906_07`` (the owner/lifecycle migration) so Alembic has a single
linear head instead of two migrations claiming the same revision ID.

Additive only: one new NOT NULL column with a server-side default, so
existing rows are backfilled to ``now()`` at migration time and no
existing session becomes invalid. Application code (``web/auth.py``,
``current_session`` / ``_revalidate_local_session``) uses this column to
re-read role/active-state from ``local_users`` for stale local-auth
sessions instead of trusting the cached ``sessions.roles`` value for the
full SESSION_TTL window (design gap flagged by Codex review on PR #60).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260906_08"
down_revision = "20260906_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "last_role_check_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_role_check_at")
