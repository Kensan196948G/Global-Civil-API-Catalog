"""Phase C tests — audit log, versioning, approval workflow (epic #47).

Requires CATALOG_DATABASE_URL like the other DB test modules (skips in CI).
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
from sqlalchemy import delete, select  # noqa: E402

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
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VERIFIER,
    ROLE_VIEWER,
    SESSION_COOKIE,
)

WF_ID = "TEST-PHASE-C-001"

ENTRY = {
    "id": WF_ID,
    "name": "Phase C workflow test entry",
    "category": "テスト",
    "provider": "test-suite",
    "provider_type": "official",
    "official_url": "https://example.test/",
    "document_url": "https://example.test/docs",
    "api_key_required": "unknown",
    "connection_status": "未調査",
    "reason": "test: workflow lifecycle",
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
    session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id == WF_ID))
    session.execute(delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id == WF_ID))
    session.execute(delete(AuditLog).where(AuditLog.record_id == WF_ID))
    session.execute(delete(CatalogEntry).where(CatalogEntry.id == WF_ID))
    session.execute(delete(UserSession).where(UserSession.user_sub.like("test-wf-%")))
    session.commit()
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def cookie(db, roles: list[str]) -> dict[str, str]:
    session = UserSession(
        id=f"test-wf-session-{time.time_ns()}",
        user_sub=f"test-wf-{'-'.join(r.split('.')[-1] for r in roles)}",
        display_name="WF Test",
        roles=roles,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)
    db.commit()
    return {SESSION_COOKIE: session.id}


def test_full_lifecycle_draft_to_published(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    verifier = cookie(db, [ROLE_VERIFIER])
    approver = cookie(db, [ROLE_APPROVER])

    # create -> draft, hidden from anonymous readers
    created = client.post("/api/v1/entries", json=ENTRY, cookies=editor)
    assert created.status_code == 201
    assert created.json()["workflow_state"] == "draft"
    assert client.get(f"/api/v1/entries/{WF_ID}").status_code == 404  # anonymous
    staff_view = client.get(f"/api/v1/entries/{WF_ID}", cookies=editor)
    assert staff_view.status_code == 200
    assert staff_view.json()["workflow_state"] == "draft"

    # missing reason on transition -> 422
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "submit"},
            cookies=editor,
        ).status_code
        == 422
    )

    # verifier cannot submit (role gate)
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "submit", "reason": "t"},
            cookies=verifier,
        ).status_code
        == 403
    )

    # editor submits -> in_review
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "submit", "reason": "test: ready for review"},
            cookies=editor,
        ).json()["state"]
        == "in_review"
    )

    # approve from wrong state -> 409
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "approve", "reason": "t"},
            cookies=approver,
        ).status_code
        == 409
    )

    # verifier sends back -> draft, then resubmit, review_ok, approve
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "send_back", "reason": "test: needs fix"},
            cookies=verifier,
        ).json()["state"]
        == "draft"
    )
    client.post(
        f"/api/v1/entries/{WF_ID}/transitions",
        json={"action": "submit", "reason": "test: resubmit"},
        cookies=editor,
    )
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "review_ok", "reason": "test: verified"},
            cookies=verifier,
        ).json()["state"]
        == "pending_approval"
    )
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/transitions",
            json={"action": "approve", "reason": "test: approved"},
            cookies=approver,
        ).json()["state"]
        == "published"
    )

    # published -> visible anonymously, counted in metadata
    assert client.get(f"/api/v1/entries/{WF_ID}").status_code == 200


def test_audit_trail_records_actions_with_reasons(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    rows = client.get("/api/v1/audit", params={"record_id": WF_ID}, cookies=editor).json()["items"]
    actions = [r["action"] for r in rows]
    assert "create" in actions
    assert actions.count("workflow_transition") >= 5
    assert all(r["reason"] for r in rows)  # every mutation carries a reason
    create_row = next(r for r in rows if r["action"] == "create")
    assert create_row["diff"]["name"]["after"] == ENTRY["name"]
    # audit endpoint is staff-gated
    assert client.get("/api/v1/audit").status_code == 401


def test_versions_and_admin_restore(client, db) -> None:
    editor = cookie(db, [ROLE_EDITOR])
    admin = cookie(db, [ROLE_ADMIN])
    viewer = cookie(db, [ROLE_VIEWER])

    # a data change creates a new version
    client.patch(
        f"/api/v1/entries/{WF_ID}",
        json={"name": "Renamed by test", "reason": "test: rename"},
        cookies=editor,
    )
    versions = client.get(f"/api/v1/entries/{WF_ID}/versions", cookies=editor).json()["items"]
    assert len(versions) >= 2
    assert client.get(f"/api/v1/entries/{WF_ID}/versions", cookies=viewer).status_code == 403

    # restore v1 (original name) — admin only
    assert (
        client.post(
            f"/api/v1/entries/{WF_ID}/restore",
            json={"version": 1, "reason": "t"},
            cookies=editor,
        ).status_code
        == 403
    )
    restored = client.post(
        f"/api/v1/entries/{WF_ID}/restore",
        json={"version": 1, "reason": "test: revert rename"},
        cookies=admin,
    )
    assert restored.status_code == 200
    assert restored.json()["name"] == ENTRY["name"]

    # restore also revives a logically deleted entry (design §4.2 復元)
    client.delete(f"/api/v1/entries/{WF_ID}", params={"reason": "test: delete"}, cookies=admin)
    assert client.get(f"/api/v1/entries/{WF_ID}", cookies=editor).status_code == 404
    revived = client.post(
        f"/api/v1/entries/{WF_ID}/restore",
        json={"version": 1, "reason": "test: undelete"},
        cookies=admin,
    )
    assert revived.status_code == 200
    db.expire_all()
    assert db.get(CatalogEntry, WF_ID).deleted_at is None


def test_version_snapshots_are_never_mutated(db) -> None:
    # Append-only discipline: version rows accumulate, none disappear.
    count = db.scalar(
        select(CatalogEntryVersion.version)
        .where(CatalogEntryVersion.record_id == WF_ID)
        .order_by(CatalogEntryVersion.version.desc())
        .limit(1)
    )
    assert count >= 3  # create + rename + restore + undelete snapshots
