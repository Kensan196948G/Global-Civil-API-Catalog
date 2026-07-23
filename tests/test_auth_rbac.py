"""Phase B auth/RBAC tests (epic #45, Issue #59).

Like the Phase A DB tests these need CATALOG_DATABASE_URL (Neon dev
branch); the module skips entirely in CI. Entra ID itself is NOT called:
the login endpoint is tested up to the redirect it issues, and ID-token
validation is exercised with a locally generated RSA key pair. The
interactive Entra login is verified manually (see PR body).
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
from urllib.parse import parse_qs, urlparse  # noqa: E402

from authlib.jose import JsonWebKey, jwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from db.models import AuthRequest, CatalogEntry, UserSession  # noqa: E402
from db.session import make_session_factory  # noqa: E402
from web.api_v1 import app  # noqa: E402
from web.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    SESSION_COOKIE,
    validate_id_token,
)

TENANT = "test-tenant-0000"
CLIENT = "test-client-0000"
TEST_ENTRY_ID = "TEST-PHASE-B-001"


@pytest.fixture(autouse=True)
def entra_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret-not-real")


@pytest.fixture(scope="module")
def db():
    factory = make_session_factory()
    session = factory()
    yield session
    # Clean up everything this module created.
    session.execute(delete(CatalogEntry).where(CatalogEntry.id == TEST_ENTRY_ID))
    session.execute(delete(UserSession).where(UserSession.user_sub.like("test-sub-%")))
    session.execute(delete(AuthRequest))
    session.commit()
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def make_session(db, roles: list[str], *, expired: bool = False) -> str:
    session = UserSession(
        id=f"test-session-{time.time_ns()}",
        user_sub=f"test-sub-{time.time_ns()}",
        display_name="Test User",
        roles=roles,
        expires_at=datetime.now(timezone.utc)
        + (timedelta(hours=-1) if expired else timedelta(hours=1)),
    )
    db.add(session)
    db.commit()
    return session.id


# --- login redirect --------------------------------------------------------


def test_login_redirects_with_pkce_state_nonce(client, db) -> None:
    response = client.get("/auth/login")
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.hostname == "login.microsoftonline.com"
    params = parse_qs(location.query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["client_id"] == [CLIENT]
    assert len(params["state"][0]) >= 32
    assert len(params["nonce"][0]) >= 32
    # The pending request is persisted server-side for the callback, and the
    # state is also bound to this browser via cookie (login-CSRF defence).
    assert db.get(AuthRequest, params["state"][0]) is not None
    assert response.cookies.get("catalog_auth_req") == params["state"][0]


def test_callback_rejects_state_not_bound_to_browser(client, db) -> None:
    # Attacker-minted state: valid in the DB but this browser never started
    # the flow (no catalog_auth_req cookie) -> must fail before any token
    # exchange happens (login-CSRF defence).
    db.add(AuthRequest(state="attacker-state", nonce="n", code_verifier="v"))
    db.commit()
    response = client.get("/auth/callback", params={"code": "any", "state": "attacker-state"})
    assert response.status_code == 401
    # The pending request must remain unconsumed (it was not this browser's).
    assert db.get(AuthRequest, "attacker-state") is not None


# --- ID token validation ---------------------------------------------------


def _signed_token(claims: dict) -> tuple[str, dict]:
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    jwks = {"keys": [key.as_dict(private=False)]}
    token = jwt.encode({"alg": "RS256"}, claims, key)
    return token.decode(), jwks


def _claims(**overrides) -> dict:
    now = int(time.time())
    base = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "exp": now + 600,
        "iat": now,
        "sub": "test-sub-token",
        "nonce": "expected-nonce",
        "roles": [ROLE_EDITOR],
    }
    base.update(overrides)
    return base


def test_validate_id_token_accepts_valid_token() -> None:
    token, jwks = _signed_token(_claims())
    claims = validate_id_token(token, "expected-nonce", jwks)
    assert claims["sub"] == "test-sub-token"
    assert claims["roles"] == [ROLE_EDITOR]


def test_validate_id_token_rejects_nonce_mismatch() -> None:
    token, jwks = _signed_token(_claims())
    with pytest.raises(HTTPException) as exc:
        validate_id_token(token, "different-nonce", jwks)
    assert exc.value.status_code == 401


def test_validate_id_token_rejects_wrong_audience() -> None:
    token, jwks = _signed_token(_claims(aud="another-app"))
    with pytest.raises(Exception):
        validate_id_token(token, "expected-nonce", jwks)


def test_validate_id_token_rejects_non_rs256_algorithm() -> None:
    # Algorithm-confusion defence: HS256 token signed with a shared secret
    # must be rejected outright (only RS256 is allowlisted).
    secret_jwk = {"kty": "oct", "k": "c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0"}
    token = jwt.encode({"alg": "HS256"}, _claims(), JsonWebKey.import_key(secret_jwk))
    with pytest.raises(Exception):
        validate_id_token(token.decode(), "expected-nonce", {"keys": [secret_jwk]})


def test_validate_id_token_rejects_missing_exp() -> None:
    claims = _claims()
    del claims["exp"]
    token, jwks = _signed_token(claims)
    with pytest.raises(Exception):
        validate_id_token(token, "expected-nonce", jwks)


# --- RBAC on write endpoints ----------------------------------------------

NEW_ENTRY = {
    "id": TEST_ENTRY_ID,
    "name": "Phase B RBAC test entry",
    "category": "テスト",
    "provider": "test-suite",
    "provider_type": "official",
    "official_url": "https://example.test/",
    "document_url": "https://example.test/docs",
    "api_key_required": "unknown",
    "connection_status": "未調査",
}


def test_write_requires_authentication(client) -> None:
    assert client.post("/api/v1/entries", json=NEW_ENTRY).status_code == 401


def test_cross_origin_write_rejected(client, db) -> None:
    # Origin-check middleware (defence-in-depth CSRF guard): a write carrying
    # a foreign Origin is rejected even with a valid admin session cookie.
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_ADMIN])}
    response = client.post(
        "/api/v1/entries",
        json=NEW_ENTRY,
        cookies=cookies,
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "cross-origin write rejected"


def test_viewer_cannot_write(client, db) -> None:
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_VIEWER])}
    assert client.post("/api/v1/entries", json=NEW_ENTRY, cookies=cookies).status_code == 403


def test_expired_session_is_unauthenticated(client, db) -> None:
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_ADMIN], expired=True)}
    assert client.post("/api/v1/entries", json=NEW_ENTRY, cookies=cookies).status_code == 401


def test_editor_create_update_and_admin_delete_lifecycle(client, db) -> None:
    editor = {SESSION_COOKIE: make_session(db, [ROLE_EDITOR])}
    admin = {SESSION_COOKIE: make_session(db, [ROLE_ADMIN])}

    created = client.post("/api/v1/entries", json=NEW_ENTRY, cookies=editor)
    assert created.status_code == 201
    assert created.json()["id"] == TEST_ENTRY_ID

    # duplicate id -> 409
    assert client.post("/api/v1/entries", json=NEW_ENTRY, cookies=editor).status_code == 409

    # FR-011 update + FR-012 status change by editor
    patched = client.patch(
        f"/api/v1/entries/{TEST_ENTRY_ID}",
        json={"connection_status": "利用終了"},
        cookies=editor,
    )
    assert patched.status_code == 200
    assert patched.json()["connection_status"] == "利用終了"

    # FR-012 delete: editor forbidden, admin allowed (logical delete)
    assert client.delete(f"/api/v1/entries/{TEST_ENTRY_ID}", cookies=editor).status_code == 403
    assert client.delete(f"/api/v1/entries/{TEST_ENTRY_ID}", cookies=admin).status_code == 204

    # deleted entries vanish from reads but the row remains (logical delete)
    assert client.get(f"/api/v1/entries/{TEST_ENTRY_ID}").status_code == 404
    db.expire_all()
    row = db.get(CatalogEntry, TEST_ENTRY_ID)
    assert row is not None and row.deleted_at is not None


def test_invalid_payload_rejected(client, db) -> None:
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_EDITOR])}
    bad = dict(NEW_ENTRY, id="TEST-BAD-URL", official_url="javascript:alert(1)")
    assert client.post("/api/v1/entries", json=bad, cookies=cookies).status_code == 422


def test_private_endpoint_rejected_by_ssrf_guard(client, db) -> None:
    # Editor tries to point the verifier at the cloud metadata service.
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_EDITOR])}
    bad = dict(
        NEW_ENTRY,
        id="TEST-SSRF-API",
        sample_endpoint="http://169.254.169.254/latest/meta-data/",
    )
    response = client.post("/api/v1/entries", json=bad, cookies=cookies)
    assert response.status_code == 422
    assert "blocked by URL policy" in response.json()["detail"]


def test_me_reports_roles(client, db) -> None:
    cookies = {SESSION_COOKIE: make_session(db, [ROLE_VIEWER])}
    body = client.get("/auth/me", cookies=cookies).json()
    assert body["roles"] == [ROLE_VIEWER]
    assert client.get("/auth/me").status_code == 401
