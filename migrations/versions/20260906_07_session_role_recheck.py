"""sessions.last_role_check_at — periodic role re-validation (Issue #61)

Revision ID: 20260906_07
Revises: 20260814_06
Create Date: 2026-09-06

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

revision = "20260906_07"
down_revision = "20260814_06"
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
