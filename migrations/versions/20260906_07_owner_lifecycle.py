"""owner/steward/reviewer/support_contact + lifecycle_status (epic #48)

Revision ID: 20260906_07
Revises: 20260814_06
Create Date: 2026-09-06

Additive only: four nullable text columns (owner/steward/reviewer/
support_contact) and a lifecycle_status column with a NOT NULL + server
default so every pre-existing row is backfilled as 'active' with no
application-visible change (design doc §5, docs/api-lifecycle.md).

``lifecycle_status`` tracks the lifecycle of the *API definition itself*
(draft/active/deprecated/retired) — distinct from ``entry_workflow.state``
(epic #47's value-change approval process, unaffected by this migration).
'retired' is the dedicated 提供終了/利用終了 status requested in issue #44
(previously conflated with connection_status='除外').
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260906_07"
down_revision = "20260814_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_entries", sa.Column("owner", sa.Text()))
    op.add_column("catalog_entries", sa.Column("steward", sa.Text()))
    op.add_column("catalog_entries", sa.Column("reviewer", sa.Text()))
    op.add_column("catalog_entries", sa.Column("support_contact", sa.Text()))
    op.add_column(
        "catalog_entries",
        sa.Column(
            "lifecycle_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column("catalog_entries", sa.Column("lifecycle_updated_at", sa.DateTime(timezone=True)))
    op.execute(
        "ALTER TABLE catalog_entries ADD CONSTRAINT ck_catalog_entries_lifecycle_status "
        "CHECK (lifecycle_status IN ('draft','active','deprecated','retired'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE catalog_entries DROP CONSTRAINT ck_catalog_entries_lifecycle_status")
    op.drop_column("catalog_entries", "lifecycle_updated_at")
    op.drop_column("catalog_entries", "lifecycle_status")
    op.drop_column("catalog_entries", "support_contact")
    op.drop_column("catalog_entries", "reviewer")
    op.drop_column("catalog_entries", "steward")
    op.drop_column("catalog_entries", "owner")
