"""MVP: role-aware tasks, webhook subscriptions, audit CSV export.

DB-backed (skips without CATALOG_DATABASE_URL, like the Phase B/C suites).
Webhook deliveries run against a local echo server so no external network
is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("authlib")

if not os.environ.get("CATALOG_DATABASE_URL"):
    pytest.skip("CATALOG_DATABASE_URL not set", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from db.models import (  # noqa: E402
    AuditLog,
    CatalogEntry,
    CatalogEntryVersion,
    EntryWorkflow,
    UserSession,
    WebhookSubscription,
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

TEST_IDS = ("TEST-TASK-001", "TEST-TASK-002", "TEST-TASK-003", "TEST-WH-ENTRY-001")
IMPORTED_IDS: list[str] = []
_IMPORT_PREFIX = "OPENAPI-" + hashlib.sha1(b"E2E Test OpenAPI Import").hexdigest()[:4].upper()


class EchoHandler(BaseHTTPRequestHandler):
    deliveries: list[dict] = []

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib.
        pass

    def do_POST(self) -> None:  # noqa: N802 - stdlib.
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.deliveries.append(
            {
                "path": self.path,
                "event": self.headers.get("X-Catalog-Webhook-Event", ""),
                "delivery_id": self.headers.get("X-Catalog-Delivery", ""),
                "signature": self.headers.get("X-Catalog-Signature", ""),
                "body": body.decode("utf-8"),
            }
        )
        payload = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture(scope="module")
def echo_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{server.server_port}/webhook-echo"
    server.shutdown()


@pytest.fixture(autouse=True)
def entra_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", "test-tenant-0000")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "test-client-0000")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret-not-real")


@pytest.fixture(scope="module")
def db():
    factory = make_session_factory()
    session = factory()
    # Fresh state even when re-running against a shared local DB.
    session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id.in_(TEST_IDS)))
    session.execute(delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id.in_(TEST_IDS)))
    session.execute(delete(AuditLog).where(AuditLog.record_id.in_(TEST_IDS)))
    session.execute(delete(CatalogEntry).where(CatalogEntry.id.in_(TEST_IDS)))
    session.execute(delete(WebhookSubscription).where(WebhookSubscription.id.like("test-wh-%")))
    session.execute(delete(AuditLog).where(AuditLog.record_id.like("test-wh-%")))
    session.execute(delete(UserSession).where(UserSession.user_sub.like("test-wh-%")))
    for record_id in IMPORTED_IDS:
        session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id == record_id))
        session.execute(
            delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id == record_id)
        )
        session.execute(delete(AuditLog).where(AuditLog.record_id == record_id))
        session.execute(delete(CatalogEntry).where(CatalogEntry.id == record_id))
    session.execute(
        delete(EntryWorkflow).where(EntryWorkflow.record_id.like(f"{_IMPORT_PREFIX}-%"))
    )
    session.execute(
        delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id.like(f"{_IMPORT_PREFIX}-%"))
    )
    session.execute(delete(AuditLog).where(AuditLog.record_id.like(f"{_IMPORT_PREFIX}-%")))
    session.execute(delete(CatalogEntry).where(CatalogEntry.id.like(f"{_IMPORT_PREFIX}-%")))
    session.commit()
    yield session
    session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id.in_(TEST_IDS)))
    session.execute(delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id.in_(TEST_IDS)))
    session.execute(delete(AuditLog).where(AuditLog.record_id.in_(TEST_IDS)))
    session.execute(delete(CatalogEntry).where(CatalogEntry.id.in_(TEST_IDS)))
    session.execute(delete(WebhookSubscription).where(WebhookSubscription.id.like("test-wh-%")))
    session.execute(delete(AuditLog).where(AuditLog.record_id.like("test-wh-%")))
    session.execute(delete(UserSession).where(UserSession.user_sub.like("test-wh-%")))
    for record_id in IMPORTED_IDS:
        session.execute(delete(EntryWorkflow).where(EntryWorkflow.record_id == record_id))
        session.execute(
            delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id == record_id)
        )
        session.execute(delete(AuditLog).where(AuditLog.record_id == record_id))
        session.execute(delete(CatalogEntry).where(CatalogEntry.id == record_id))
    session.execute(
        delete(EntryWorkflow).where(EntryWorkflow.record_id.like(f"{_IMPORT_PREFIX}-%"))
    )
    session.execute(
        delete(CatalogEntryVersion).where(CatalogEntryVersion.record_id.like(f"{_IMPORT_PREFIX}-%"))
    )
    session.execute(delete(AuditLog).where(AuditLog.record_id.like(f"{_IMPORT_PREFIX}-%")))
    session.execute(delete(CatalogEntry).where(CatalogEntry.id.like(f"{_IMPORT_PREFIX}-%")))
    session.commit()
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def cookie(db, roles: list[str]) -> dict[str, str]:
    session = UserSession(
        id=f"test-wh-session-{time.time_ns()}",
        user_sub=f"test-wh-{'-'.join(r.split('.')[-1] for r in roles)}",
        display_name="WH Test",
        roles=roles,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)
    db.commit()
    return {SESSION_COOKIE: session.id}


def make_entry(db, record_id: str, state: str) -> None:
    entry = CatalogEntry(
        id=record_id,
        name=f"Task entry {record_id}",
        category="テスト",
        provider="test-suite",
        provider_type="official",
        official_url="https://example.test/",
        document_url="https://example.test/docs",
        api_key_required="unknown",
        connection_status="調査中",
    )
    db.add(entry)
    db.add(EntryWorkflow(record_id=record_id, state=state))
    db.commit()


def test_tasks_are_role_filtered(client, db) -> None:
    make_entry(db, "TEST-TASK-001", "in_review")
    make_entry(db, "TEST-TASK-002", "pending_approval")
    make_entry(db, "TEST-TASK-003", "rejected")

    assert client.get("/api/v1/tasks").status_code == 401
    viewer = client.get("/api/v1/tasks", cookies=cookie(db, [ROLE_VIEWER]))
    assert viewer.status_code == 403

    editor = client.get("/api/v1/tasks", cookies=cookie(db, [ROLE_EDITOR])).json()
    editor_ids = [t["record_id"] for t in editor["tasks"]]
    assert "TEST-TASK-003" in editor_ids
    assert "TEST-TASK-001" not in editor_ids
    assert "TEST-TASK-002" not in editor_ids
    assert editor["counts"]["fix"] >= 1

    verifier = client.get("/api/v1/tasks", cookies=cookie(db, [ROLE_VERIFIER])).json()
    verifier_ids = [t["record_id"] for t in verifier["tasks"]]
    assert "TEST-TASK-001" in verifier_ids
    assert "TEST-TASK-002" not in verifier_ids
    assert verifier["counts"]["review"] >= 1

    approver = client.get("/api/v1/tasks", cookies=cookie(db, [ROLE_APPROVER])).json()
    approver_ids = [t["record_id"] for t in approver["tasks"]]
    assert "TEST-TASK-002" in approver_ids
    assert "TEST-TASK-001" not in approver_ids
    assert approver["counts"]["approval"] >= 1

    admin = client.get("/api/v1/tasks", cookies=cookie(db, [ROLE_ADMIN])).json()
    admin_ids = [t["record_id"] for t in admin["tasks"]]
    assert {"TEST-TASK-001", "TEST-TASK-002", "TEST-TASK-003"} <= set(admin_ids)


def test_webhook_crud_and_test_delivery(client, db, echo_server) -> None:
    admin = cookie(db, [ROLE_ADMIN])
    payload = {
        "name": "test webhook",
        "url": echo_server,
        "events": ["entry.workflow_transition"],
        "secret": "test-signing-secret",
        "reason": "test: create webhook",
    }
    created = client.post("/api/v1/webhooks", json=payload, cookies=admin)
    assert created.status_code == 201
    body = created.json()
    webhook_id = body["id"]
    assert body["secret"] == "test-signing-secret"

    listed = client.get("/api/v1/webhooks", cookies=admin).json()
    assert listed["items"][0]["id"] == webhook_id
    assert "secret" not in listed["items"][0]

    tested = client.post(f"/api/v1/webhooks/{webhook_id}/test", cookies=admin)
    assert tested.status_code == 200
    assert tested.json()["status"] == "HTTP 200"
    assert EchoHandler.deliveries[-1]["event"] == "test"

    patched = client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"reason": "test: pause", "is_active": False},
        cookies=admin,
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    deleted = client.delete(
        f"/api/v1/webhooks/{webhook_id}?reason=test%20cleanup",
        cookies=admin,
    )
    assert deleted.status_code == 204
    remaining = client.get("/api/v1/webhooks", cookies=admin).json()["items"]
    assert webhook_id not in [item["id"] for item in remaining]


def test_webhook_dispatch_on_transition(client, db, echo_server) -> None:
    admin = cookie(db, [ROLE_ADMIN])
    created = client.post(
        "/api/v1/webhooks",
        json={
            "name": "transition hook",
            "url": echo_server,
            "events": ["entry.workflow_transition"],
            "secret": "sign-secret",
            "reason": "test: create",
        },
        cookies=admin,
    )
    webhook_id = created.json()["id"]
    before = len(EchoHandler.deliveries)

    entry_payload = {
        "id": "TEST-WH-ENTRY-001",
        "name": "Webhook transition entry",
        "category": "テスト",
        "provider": "test-suite",
        "provider_type": "official",
        "official_url": "https://example.test/",
        "document_url": "https://example.test/docs",
        "api_key_required": "unknown",
        "connection_status": "未調査",
        "reason": "test: create entry",
    }
    assert client.post("/api/v1/entries", json=entry_payload, cookies=admin).status_code == 201
    transition = client.post(
        "/api/v1/entries/TEST-WH-ENTRY-001/transitions",
        json={"action": "submit", "reason": "test: submit"},
        cookies=admin,
    )
    assert transition.status_code == 200

    deliveries = EchoHandler.deliveries[before:]
    assert any(delivery["event"] == "entry.workflow_transition" for delivery in deliveries)
    transition_delivery = next(
        delivery for delivery in deliveries if delivery["event"] == "entry.workflow_transition"
    )
    assert transition_delivery["signature"].startswith("sha256=")
    assert json.loads(transition_delivery["body"])["data"]["to"] == "in_review"

    # Delivery bookkeeping persisted on the subscription.
    hook = db.get(WebhookSubscription, webhook_id)
    assert hook is not None
    assert hook.last_delivery_status == "HTTP 200"
    assert hook.failure_count == 0


def test_webhook_rejects_private_ip(client, db) -> None:
    response = client.post(
        "/api/v1/webhooks",
        json={
            "name": "ssrf",
            "url": "http://169.254.169.254/latest/meta-data",
            "events": ["entry.created"],
            "reason": "test",
        },
        cookies=cookie(db, [ROLE_ADMIN]),
    )
    assert response.status_code == 422
    assert "blocked by URL policy" in response.json()["detail"]


def test_audit_csv_export(client, db) -> None:
    admin = cookie(db, [ROLE_ADMIN])
    response = client.get("/api/v1/audit/export.csv", cookies=admin)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.splitlines()
    assert lines[0] == "seq,at,actor,actor_roles,action,record_id,reason,diff"
    assert any("webhook_subscribe" in line for line in lines)


def test_openapi_import_creates_drafts_and_skips_duplicates(client, db) -> None:
    admin = cookie(db, [ROLE_ADMIN])
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "E2E Test OpenAPI Import", "version": "1.0.0"},
        "servers": [{"url": "https://example.test/e2e-openapi"}],
        "paths": {
            "/items": {"get": {"summary": "List items", "tags": ["地図"]}},
            "/items/{id}": {"get": {"summary": "Get item"}},
        },
    }
    first = client.post(
        "/api/v1/import/openapi",
        json={
            "name": "e2e import",
            "spec": spec,
            "reason": "test: openapi import",
            "max_candidates": 10,
        },
        cookies=admin,
    )
    assert first.status_code == 201
    body = first.json()
    assert len(body["created"]) == 2
    assert body["skipped_duplicates"] == []
    for item in body["created"]:
        assert item["workflow_state"] == "draft"
        IMPORTED_IDS.append(item["id"])

    # Anonymous readers must not see the imported drafts.
    assert client.get(f"/api/v1/entries/{body['created'][0]['id']}").status_code == 404

    # Re-import skips everything as duplicates.
    second = client.post(
        "/api/v1/import/openapi",
        json={
            "name": "e2e import again",
            "spec": spec,
            "reason": "test: duplicate import",
        },
        cookies=admin,
    )
    assert second.status_code == 201
    assert second.json()["created"] == []
    assert len(second.json()["skipped_duplicates"]) == 2
