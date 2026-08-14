"""Seed the MVP demo database with fictional data (opt-in, local-only).

Creates/updates:
  - 8 demo catalog entries (``DEMO-*``, all values fictional)
  - 10 demo verification results (success/warning/failure/skipped)
  - workflow states per ``data/demo/workflow_states.json``
  - 5 local demo users (Admin/Editor/Verifier/Approver/Viewer)
  - sample audit rows and entry versions for one demo record
  - one local webhook subscription pointing at the demo echo server

Safety: refuses to run unless ``CATALOG_DEMO_SEED=1`` AND the target is not
production (no Neon host, no production base URL).  Demo users share the
password ``DemoPassw0rd!2026`` — demo only, never reuse in production.

Usage:
    CATALOG_DATABASE_URL=... CATALOG_DEMO_SEED=1 \\
      CATALOG_BASE_URL=http://127.0.0.1:49331 python scripts/seed_demo_data.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from db.audit import (  # noqa: E402
    ACTION_CREATE,
    ACTION_TRANSITION,
    ACTION_UPDATE,
    record_audit,
    snapshot_entry,
)
from db.models import (  # noqa: E402
    AuditLog,
    CatalogEntry,
    CatalogEntryVersion,
    EntryWorkflow,
    LocalUser,
    VerificationResult,
    WebhookSubscription,
)
from db.session import make_engine, make_session_factory  # noqa: E402
from scripts.catalog_utils import load_json  # noqa: E402
from web.auth import hash_password  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data" / "demo"

DEMO_PASSWORD = "DemoPassw0rd!2026"
DEMO_USERS = (
    ("demo-admin", "Catalog.Admin", "デモ管理者（架空）"),
    ("demo-editor", "Catalog.Editor", "デモ編集者（架空）"),
    ("demo-verifier", "Catalog.Verifier", "デモ検証者（架空）"),
    ("demo-approver", "Catalog.Approver", "デモ承認者（架空）"),
    ("demo-viewer", "Catalog.Viewer", "デモ閲覧者（架空）"),
)
DEMO_WEBHOOK_ID = "wh_demo_echo"
DEMO_WEBHOOK_URL = "http://127.0.0.1:49339/webhook-echo"
DEMO_WEBHOOK_SECRET = "demo-webhook-secret-2026"
DEMO_WEBHOOK_EVENTS = ["entry.created", "entry.updated", "entry.workflow_transition"]


def _guard() -> None:
    if os.environ.get("CATALOG_DEMO_SEED", "") != "1":
        print(
            "CATALOG_DEMO_SEED=1 is required (demo seed is opt-in).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if os.environ.get("CATALOG_ENV", "").strip().lower() == "production":
        print("Refusing: CATALOG_ENV=production.", file=sys.stderr)
        raise SystemExit(2)
    url = os.environ.get("CATALOG_DATABASE_URL", "").lower()
    if "neon" in url or ".neon.tech" in url:
        print("Refusing: demo seed must not target a Neon database.", file=sys.stderr)
        raise SystemExit(2)
    base = os.environ.get("CATALOG_BASE_URL", "").lower()
    if "api.mirai-dx-platform.com" in base:
        print("Refusing: production base URL detected.", file=sys.stderr)
        raise SystemExit(2)


def _normalize_row(model, record: dict) -> dict:
    """Project a JSON record onto every model column (homogeneous rows)."""
    row: dict = {}
    for column in model.__table__.columns:
        if column.name in ("created_at", "updated_at"):
            continue
        value = record.get(column.name)
        if column.name in ("data_formats", "tags") and value is None:
            value = []
        row[column.name] = value
    return row


def _entry_row(record: dict) -> dict:
    row = _normalize_row(CatalogEntry, record)
    if isinstance(row.get("last_checked_at"), str):
        row["last_checked_at"] = date.fromisoformat(row["last_checked_at"])
    return row


def _result_row(record: dict) -> dict:
    row = _normalize_row(VerificationResult, record)
    if isinstance(row.get("verified_at"), str):
        row["verified_at"] = datetime.fromisoformat(row["verified_at"].replace("Z", "+00:00"))
    return row


def _upsert(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    statement = insert(model).values(rows)
    columns = {key: statement.excluded[key] for key in rows[0] if key != "id"}
    if "updated_at" in model.__table__.columns:
        columns["updated_at"] = func.now()
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[model.__table__.primary_key.columns.keys()[0]],
            set_=columns,
        )
    )


def main() -> int:
    _guard()
    entries = load_json(DEMO_DIR / "api_catalog.json")
    results = load_json(DEMO_DIR / "verification_results.json")
    workflow_states = load_json(DEMO_DIR / "workflow_states.json")

    engine = make_engine()
    factory = make_session_factory(engine)
    with factory() as session:
        _upsert(session, CatalogEntry, [_entry_row(record) for record in entries])
        _upsert(session, VerificationResult, [_result_row(record) for record in results])
        workflow_rows = [
            {"record_id": record_id, "state": state, "updated_at": func.now()}
            for record_id, state in workflow_states.items()
        ]
        _upsert(session, EntryWorkflow, workflow_rows)

        # Demo users (upsert keeps the same demo password deterministic).
        user_rows = []
        for username, role, display_name in DEMO_USERS:
            user_rows.append(
                {
                    "username": username,
                    "password_hash": hash_password(DEMO_PASSWORD),
                    "display_name": display_name,
                    "role": role,
                    "is_active": True,
                    "failed_attempts": 0,
                    "locked_until": None,
                }
            )
        _upsert(session, LocalUser, user_rows)

        # Demo webhook subscription (echo server on 49339).
        _upsert(
            session,
            WebhookSubscription,
            [
                {
                    "id": DEMO_WEBHOOK_ID,
                    "name": "デモ用ローカル通知（架空）",
                    "url": DEMO_WEBHOOK_URL,
                    "events": DEMO_WEBHOOK_EVENTS,
                    "secret": DEMO_WEBHOOK_SECRET,
                    "is_active": True,
                    "created_by": "demo-seed",
                    "last_delivery_at": None,
                    "last_delivery_status": None,
                    "failure_count": 0,
                }
            ],
        )

        # Sample audit trail + versions for the flagship demo record.
        session.execute(
            delete(AuditLog).where(
                AuditLog.actor == "demo-seed",
                AuditLog.record_id.like("DEMO-%"),
            )
        )
        session.execute(
            delete(CatalogEntryVersion).where(
                CatalogEntryVersion.created_by == "demo-seed",
                CatalogEntryVersion.record_id.like("DEMO-%"),
            )
        )
        entry = session.get(CatalogEntry, "DEMO-RIVER-LEVEL-001")
        if entry is not None:
            snapshot_entry(session, entry, "demo-seed")
            record_audit(
                session,
                actor="demo-seed",
                actor_roles=["Catalog.Admin"],
                action=ACTION_CREATE,
                record_id=entry.id,
                diff={"id": {"before": None, "after": entry.id}},
                reason="demo: fictional record creation",
            )
            record_audit(
                session,
                actor="demo-seed",
                actor_roles=["Catalog.Admin"],
                action=ACTION_UPDATE,
                record_id=entry.id,
                diff={"connection_status": {"before": "調査中", "after": "本格利用候補"}},
                reason="demo: fictional status update",
            )
            record_audit(
                session,
                actor="demo-seed",
                actor_roles=["Catalog.Admin"],
                action=ACTION_TRANSITION,
                record_id=entry.id,
                diff={"state": {"before": "draft", "after": "published"}},
                reason="demo: fictional approval",
            )
        session.commit()

    print(
        f"Demo data seeded: {len(entries)} entries, {len(results)} verification results, "
        f"{len(DEMO_USERS)} users, 1 webhook."
    )
    print("Demo accounts (fictional, password: DemoPassw0rd!2026):")
    for username, role, _ in DEMO_USERS:
        print(f"  - {username} ({role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
