"""Owner/steward/reviewer/support_contact + API-definition lifecycle tests
(epic #48). Mirrors the fixture/cookie patterns in test_workflow_audit.py.

Requires CATALOG_DATABASE_URL like the other DB test modules (skips in CI
when it is not set — the real DB run is required evidence before merge).
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("authlib")

if not os.environ.get("CATALOG_DATABASE_URL"):
    pytest.skip("CATALOG_DATABASE_URL not set", allow_module_level=True)

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, update  # noqa: E402

from db.models import (  # noqa: E402
    AuditLog,
    CatalogEntry,
    CatalogEntryVersion,
    EntryWorkflow,
    UserSession,
)
from db.session import make_session_factory  # noqa: E402
from web.api_v1 import app  # noqa: E402
from web.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    SESSION_COOKIE,
)

LC_ID = "TEST-LIFECYCLE-001"
GAP_ID = "TEST-LIFECYCLE-GAP-001"

BASE_ENTRY = {
    "name": "Lifecycle test entry",
    "category": "テスト",
    "provider": "test-suite",
    "provider_type": "official",
    "official_url": "https://example.test/",
    "document_url": "https://example.test/docs",
    "api_key_required": "unknown",
    "connection_status": "未調査",
}


@pytest.fixture(autouse=True)
def entra_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "test-tenant-0000")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "test-client-0000")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret-not-real")


@pytest.fixture(scope="module")
def db():
    factory = make_session_factory()
    session = factory()
    yield session
    for record_id in (LC_ID, GAP_ID):
        session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id == record_id))
        session.execute(
            delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id == record_id)
        )
        session.execute(delete(AuditLog).where(AuditLog.record_id == record_id))
        session.execute(delete(CatalogEntry).where(CatalogEntry.id == record_id))
    session.execute(delete(UserSession).where(UserSession.user_sub.like("test-lc-%")))
    session.commit()
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def cookie(db, roles: list[str]) -> dict[str, str]:
    session = UserSession(
        id=f"test-lc-session-{time.time_ns()}",
        user_sub=f"test-lc-{'-'.join(r.split('.')[-1] for r in roles)}",
        display_name="Lifecycle Test",
        roles=roles,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)
    db.commit()
    return {SESSION_COOKIE: session.id}


def test_create_defaults_to_active_and_accepts_stewardship_fields(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    payload = {
        **BASE_ENTRY,
        "id": LC_ID,
        "owner": "Data Platform Team",
        "steward": "Jane Steward",
        "reason": "test: create with stewardship fields",
    }
    created = client.post("/api/v1/entries", json=payload, cookies=editor)
    assert created.status_code == 201
    body = created.json()
    assert body["lifecycle_status"] == "active"
    assert body["lifecycle_updated_at"] is None
    assert body["owner"] == "Data Platform Team"
    assert body["steward"] == "Jane Steward"
    assert body["reviewer"] is None
    assert body["support_contact"] is None

    # GET (staff) round-trips the same fields.
    fetched = client.get(f"/api/v1/entries/{LC_ID}", cookies=editor).json()
    assert fetched["owner"] == "Data Platform Team"
    assert fetched["lifecycle_status"] == "active"


def test_patch_updates_stewardship_fields(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    patched = client.patch(
        f"/api/v1/entries/{LC_ID}",
        json={
            "reviewer": "Rick Reviewer",
            "support_contact": "support@example.test",
            "reason": "test: add reviewer/support contact",
        },
        cookies=editor,
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["reviewer"] == "Rick Reviewer"
    assert body["support_contact"] == "support@example.test"
    assert body["owner"] == "Data Platform Team"  # untouched field preserved


def test_lifecycle_transition_valid_path_and_audit(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    viewer = cookie(db, [ROLE_VIEWER])

    # viewer cannot transition lifecycle (require_editor gate)
    assert (
        client.post(
            f"/api/v1/entries/{LC_ID}/lifecycle",
            json={"lifecycle_status": "deprecated", "reason": "t"},
            cookies=viewer,
        ).status_code
        == 403
    )

    # missing reason -> 422
    assert (
        client.post(
            f"/api/v1/entries/{LC_ID}/lifecycle",
            json={"lifecycle_status": "deprecated"},
            cookies=editor,
        ).status_code
        == 422
    )

    # active -> deprecated (valid)
    deprecated = client.post(
        f"/api/v1/entries/{LC_ID}/lifecycle",
        json={"lifecycle_status": "deprecated", "reason": "test: superseded by v2"},
        cookies=editor,
    )
    assert deprecated.status_code == 200
    assert deprecated.json()["lifecycle_status"] == "deprecated"
    assert deprecated.json()["lifecycle_updated_at"] is not None

    # deprecated -> active (not an allowed transition) -> 400
    invalid = client.post(
        f"/api/v1/entries/{LC_ID}/lifecycle",
        json={"lifecycle_status": "active", "reason": "test: invalid reactivation"},
        cookies=editor,
    )
    assert invalid.status_code == 400

    # deprecated -> retired (valid, terminal)
    retired = client.post(
        f"/api/v1/entries/{LC_ID}/lifecycle",
        json={"lifecycle_status": "retired", "reason": "test: fully retired"},
        cookies=editor,
    )
    assert retired.status_code == 200
    assert retired.json()["lifecycle_status"] == "retired"

    # retired is terminal: any further transition is rejected
    terminal = client.post(
        f"/api/v1/entries/{LC_ID}/lifecycle",
        json={"lifecycle_status": "deprecated", "reason": "test: cannot leave retired"},
        cookies=editor,
    )
    assert terminal.status_code == 400

    # audit trail records lifecycle_transition distinct from workflow_transition
    rows = client.get("/api/v1/audit", params={"record_id": LC_ID}, cookies=editor).json()["items"]
    actions = [r["action"] for r in rows]
    assert actions.count("lifecycle_transition") == 2  # active->deprecated, deprecated->retired
    lifecycle_rows = [r for r in rows if r["action"] == "lifecycle_transition"]
    assert lifecycle_rows[0]["diff"]["lifecycle_status"]["after"] == "retired"
    assert all(r["reason"] for r in lifecycle_rows)


def test_stewardship_gaps_endpoint(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    admin = cookie(db, [ROLE_ADMIN])

    # a second entry with no owner/steward set (created without those fields)
    created = client.post(
        "/api/v1/entries",
        json={**BASE_ENTRY, "id": GAP_ID, "reason": "test: gap detection fixture"},
        cookies=editor,
    )
    assert created.status_code == 201

    gaps = client.get("/api/v1/entries/stewardship-gaps", cookies=admin).json()
    missing_ids = {item["id"] for item in gaps["missing_owner_steward"]}
    assert GAP_ID in missing_ids
    assert LC_ID not in missing_ids  # LC_ID has owner+steward set

    # move GAP_ID to 'deprecated' then backdate it beyond the staleness
    # threshold to exercise the positive detection path.
    deprecated = client.post(
        f"/api/v1/entries/{GAP_ID}/lifecycle",
        json={"lifecycle_status": "deprecated", "reason": "test: stale detection fixture"},
        cookies=editor,
    )
    assert deprecated.status_code == 200
    factory = make_session_factory()
    with factory() as session:
        session.execute(
            update(CatalogEntry)
            .where(CatalogEntry.id == GAP_ID)
            .values(lifecycle_updated_at=datetime.now(timezone.utc) - timedelta(days=120))
        )
        # also backdate LC_ID (currently 'retired', not 'deprecated') to
        # confirm status filtering — old-but-wrong-status must be excluded.
        session.execute(
            update(CatalogEntry)
            .where(CatalogEntry.id == LC_ID)
            .values(lifecycle_updated_at=datetime.now(timezone.utc) - timedelta(days=120))
        )
        session.commit()

    gaps_after = client.get("/api/v1/entries/stewardship-gaps", cookies=admin).json()
    assert gaps_after["stale_deprecated_threshold_days"] == 90
    stale_ids = {item["id"] for item in gaps_after["stale_deprecated"]}
    assert GAP_ID in stale_ids
    # LC_ID is 'retired' (not 'deprecated'), so it must NOT appear even
    # though it is equally old — status must match, not just recency.
    assert LC_ID not in stale_ids
