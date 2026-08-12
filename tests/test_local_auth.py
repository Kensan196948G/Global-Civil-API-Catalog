"""Local username/password auth tests (auth mode ``local``).

Like the other DB-backed suites these need CATALOG_DATABASE_URL and skip
entirely in CI. They exercise the full FastAPI stack (TestClient) against
the real ``local_users`` table: login, lockout, /auth/me and logout.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")
pytest.importorskip("authlib")

if not os.environ.get("CATALOG_DATABASE_URL"):
    pytest.skip("CATALOG_DATABASE_URL not set", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from db.models import AuditLog, LocalUser, UserSession  # noqa: E402
from db.session import make_session_factory  # noqa: E402
from web.api_v1 import app  # noqa: E402
from web.auth import (  # noqa: E402
    MAX_FAILED_LOGINS,
    ROLE_EDITOR,
    SESSION_COOKIE,
    hash_password,
    revoke_user_sessions,
    verify_password,
)
from web.ratelimit import RateLimiter  # noqa: E402

# Test-only credential (not a real secret).
PASSWORD = "correct-horse-battery-st4ple"


@pytest.fixture(autouse=True)
def local_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CATALOG_AUTH_MODE", "local")
    import web.api_v1

    # All TestClient requests share one client IP; disable the login limiter
    # for the suite (the 429 behaviour is covered by its own test).
    monkeypatch.setattr(web.api_v1, "login_limiter", RateLimiter(limit=10**6, window_seconds=1))


@pytest.fixture(scope="module")
def db():
    factory = make_session_factory()
    session = factory()
    yield session
    session.execute(delete(UserSession).where(UserSession.user_sub.like("local:test-local-%")))
    session.execute(delete(AuditLog).where(AuditLog.actor.like("local:test-local-%")))
    session.execute(delete(LocalUser).where(LocalUser.username.like("test-local-%")))
    session.commit()
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def put_user(
    db, username: str, *, role: str = ROLE_EDITOR, password: str = PASSWORD, active: bool = True
) -> None:
    db.execute(delete(UserSession).where(UserSession.user_sub == f"local:{username}"))
    db.execute(delete(LocalUser).where(LocalUser.username == username))
    db.add(
        LocalUser(
            username=username,
            password_hash=hash_password(password),
            display_name="Test Local",
            role=role,
            is_active=active,
        )
    )
    db.commit()


def test_password_hash_roundtrip():
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("scrypt$")
    assert verify_password(PASSWORD, encoded)
    assert not verify_password("wrong-password-123", encoded)
    assert not verify_password(PASSWORD, "garbage")


def test_login_success_sets_session(db, client):
    put_user(db, "test-local-ok")
    response = client.post("/auth/login", json={"username": "Test-Local-OK", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["roles"] == [ROLE_EDITOR]
    assert SESSION_COOKIE in response.cookies
    me = client.get("/auth/me", cookies={SESSION_COOKIE: response.cookies[SESSION_COOKIE]})
    assert me.status_code == 200
    assert me.json()["sub"] == "local:test-local-ok"


def test_login_wrong_password_401(db, client):
    put_user(db, "test-local-wrong")
    response = client.post(
        "/auth/login", json={"username": "test-local-wrong", "password": "not-the-password"}
    )
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_login_unknown_user_401(client):
    response = client.post(
        "/auth/login", json={"username": "test-local-ghost", "password": PASSWORD}
    )
    assert response.status_code == 401


def test_lockout_after_max_failures(db, client):
    put_user(db, "test-local-lock")
    for _ in range(MAX_FAILED_LOGINS):
        response = client.post(
            "/auth/login", json={"username": "test-local-lock", "password": "bad-password-1"}
        )
        assert response.status_code == 401
    # Even the correct password is rejected while the lockout window holds.
    response = client.post(
        "/auth/login", json={"username": "test-local-lock", "password": PASSWORD}
    )
    assert response.status_code == 423
    db.expire_all()
    user = db.get(LocalUser, "test-local-lock")
    assert user.locked_until is not None


def test_inactive_account_401(db, client):
    put_user(db, "test-local-off", active=False)
    response = client.post("/auth/login", json={"username": "test-local-off", "password": PASSWORD})
    # 401 (not 403): the response must not reveal that the name exists.
    assert response.status_code == 401


def test_get_login_redirects_to_ui(client):
    response = client.get("/auth/login")
    assert response.status_code == 302
    assert response.headers["location"] == "/?login=1"


def test_logout_local_redirects_home(db, client):
    put_user(db, "test-local-bye")
    login = client.post("/auth/login", json={"username": "test-local-bye", "password": PASSWORD})
    cookie = login.cookies[SESSION_COOKIE]
    logout = client.get("/auth/logout", cookies={SESSION_COOKIE: cookie})
    assert logout.status_code == 302
    assert logout.headers["location"] == "/"
    me = client.get("/auth/me", cookies={SESSION_COOKIE: cookie})
    assert me.status_code == 401


def test_local_login_disabled_in_oidc_mode(monkeypatch: pytest.MonkeyPatch, client):
    monkeypatch.setenv("CATALOG_AUTH_MODE", "oidc")
    monkeypatch.setenv("ENTRA_TENANT_ID", "test-tenant-0000")
    response = client.post("/auth/login", json={"username": "test-local-ok", "password": PASSWORD})
    assert response.status_code == 404


def test_login_rate_limit_returns_429(
    db, client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import web.api_v1

    put_user(db, "test-local-rate")
    monkeypatch.setattr(web.api_v1, "login_limiter", RateLimiter(limit=1, window_seconds=300))
    body = {"username": "test-local-rate", "password": PASSWORD}

    assert client.post("/auth/login", json=body).status_code == 200
    assert client.post("/auth/login", json=body).status_code == 429


def test_revoke_user_sessions_invalidates_existing_logins(db, client) -> None:
    put_user(db, "test-local-revoke")
    login = client.post("/auth/login", json={"username": "test-local-revoke", "password": PASSWORD})
    cookie = login.cookies[SESSION_COOKIE]
    assert client.get("/auth/me", cookies={SESSION_COOKIE: cookie}).status_code == 200

    revoked = revoke_user_sessions(db, "local:test-local-revoke")

    assert revoked >= 1
    assert client.get("/auth/me", cookies={SESSION_COOKIE: cookie}).status_code == 401
