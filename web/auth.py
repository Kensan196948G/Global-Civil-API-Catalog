"""Entra ID OIDC (Authorization Code + PKCE) login and role-based access
control — Phase B of epic #45 (design §3, Issue #59).

Configuration comes exclusively from environment variables (§19 — no
secrets in the repo):

    ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET
    CATALOG_BASE_URL   public base URL for redirects (default http://localhost:49232)

The browser only ever holds an opaque session ID; ID/access tokens are
used during the callback and then discarded (server-side sessions,
design §3.1). App roles are read from the ID token ``roles`` claim.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.audit import ACTION_LOGIN, ACTION_LOGIN_FAILED, ACTION_LOGOUT, record_audit
from db.models import AuthRequest, LocalUser, UserSession

SESSION_COOKIE = "catalog_session"
# Binds the pending login to the browser that started it (login-CSRF
# defence): the callback only accepts a state that this browser initiated.
AUTH_REQ_COOKIE = "catalog_auth_req"
SESSION_TTL = timedelta(hours=8)
AUTH_REQUEST_TTL = timedelta(minutes=10)
CLOCK_SKEW_SECONDS = 300  # design §3.3

# How often a *local* (username/password) session re-reads role/active
# state from ``local_users`` instead of trusting the roles cached on the
# session at login time (issue #61 — Codex review on PR #60). 1h bounds
# the worst-case staleness window for a revoked or demoted local account
# to a small fraction of SESSION_TTL, without adding a DB round trip to
# every single request.
#
# OIDC (Entra ID) sessions are NOT re-checked here: doing so without a
# stored refresh token would mean a full silent re-authentication against
# the tenant on a background timer, which needs its own token storage,
# rotation and revocation handling (offline_access scope) — a materially
# larger change than this fix. The admin revoke API below (POST
# /api/v1/admin/sessions/revoke) is the interim mitigation for OIDC
# role-change events; a future issue can add Entra-side re-validation
# (e.g. a group-change webhook or short-lived silent re-auth) on top of
# it without touching this local-mode logic.
LOCAL_ROLE_RECHECK_INTERVAL = timedelta(hours=1)

ROLE_ADMIN = "Catalog.Admin"
ROLE_EDITOR = "Catalog.Editor"
ROLE_VERIFIER = "Catalog.Verifier"
ROLE_APPROVER = "Catalog.Approver"
ROLE_VIEWER = "Catalog.Viewer"
ALL_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VERIFIER, ROLE_APPROVER, ROLE_VIEWER)

# --- local username/password mode -------------------------------------------
# scrypt (stdlib) keeps the dependency surface unchanged; parameters follow
# the OWASP password-storage cheat sheet baseline for scrypt.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
MIN_PASSWORD_LENGTH = 12
MAX_FAILED_LOGINS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)

# ``CATALOG_ENV`` values in which the demo auth bypass may be armed. This is an
# allow-list on purpose: an unset or unrecognised environment must never
# disable authentication (see auth_bypass_enabled).
AUTH_BYPASS_ENVS = frozenset({"development", "demo"})


def auth_mode() -> str:
    """``local`` (username/password) or ``oidc`` (Entra ID).

    Explicit CATALOG_AUTH_MODE wins; otherwise the presence of the Entra
    tenant decides, so an api.env without ENTRA_* falls back to local.
    """
    mode = os.environ.get("CATALOG_AUTH_MODE", "").strip().lower()
    if mode in ("local", "oidc"):
        return mode
    return "oidc" if os.environ.get("ENTRA_TENANT_ID") else "local"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    encoded_salt = base64.b64encode(salt).decode()
    encoded_digest = base64.b64encode(digest).decode()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encoded_salt}${encoded_digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, encoded_salt, encoded_digest = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(encoded_salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=_SCRYPT_DKLEN,
        )
        return hmac.compare_digest(digest, base64.b64decode(encoded_digest))
    except (ValueError, TypeError):
        return False


# Verified against when the username does not exist, so the response time
# does not reveal which usernames are registered.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


class LocalLoginBody(BaseModel):
    username: str
    password: str


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise HTTPException(status_code=503, detail=f"auth not configured ({name} unset)")
    return value


def _authority() -> str:
    return f"https://login.microsoftonline.com/{_env('ENTRA_TENANT_ID')}"


def _base_url() -> str:
    return os.environ.get("CATALOG_BASE_URL", "http://localhost:49232").rstrip("/")


def _redirect_uri() -> str:
    return f"{_base_url()}/auth/callback"


def _cookie_secure() -> bool:
    # __Host- prefixed cookies require HTTPS; local development runs on
    # http://localhost, so the Secure attribute follows the base URL scheme
    # (documented deviation from design §3.1, revisit at production cutover).
    return _base_url().startswith("https://")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange the authorization code for tokens. Isolated for testability."""
    response = httpx.post(
        f"{_authority()}/oauth2/v2.0/token",
        data={
            "client_id": _env("ENTRA_CLIENT_ID"),
            "client_secret": _env("ENTRA_CLIENT_SECRET"),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "code_verifier": code_verifier,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _fetch_jwks() -> dict:
    """Fetch the tenant JWKS. Isolated for testability."""
    response = httpx.get(f"{_authority()}/discovery/v2.0/keys", timeout=15)
    response.raise_for_status()
    return response.json()


# Entra ID signs ID tokens with RS256 only; pinning the algorithm here
# forecloses algorithm-confusion attacks (e.g. HS256 with a public key).
_JWT = JsonWebToken(["RS256"])


def validate_id_token(id_token: str, nonce: str, jwks: dict) -> dict:
    """Validate signature and claims (alg/iss/aud/exp/iat/nonce, design §3.3)."""
    claims = _JWT.decode(
        id_token,
        JsonWebKey.import_key_set(jwks),
        claims_options={
            "iss": {"essential": True, "value": f"{_authority()}/v2.0"},
            "aud": {"essential": True, "value": _env("ENTRA_CLIENT_ID")},
            "exp": {"essential": True},
            "iat": {"essential": True},
        },
    )
    claims.validate(leeway=CLOCK_SKEW_SECONDS)
    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=401, detail="nonce mismatch")
    return dict(claims)


def _local_username(user_sub: str) -> str | None:
    """``local:<username>`` -> ``<username>``; ``None`` for OIDC subs."""
    prefix = "local:"
    if not user_sub.startswith(prefix):
        return None
    return user_sub[len(prefix) :]


def _revalidate_local_session(db: Session, session: UserSession) -> UserSession | None:
    """Re-read role/active-state for a stale *local* session (issue #61).

    Returns the (possibly updated) session, or ``None`` if it must be
    treated as logged out (account deactivated or deleted since login).
    OIDC sessions are returned unchanged — see ``LOCAL_ROLE_RECHECK_INTERVAL``.
    """
    username = _local_username(session.user_sub)
    if username is None:
        return session
    now = _now()
    if now - session.last_role_check_at < LOCAL_ROLE_RECHECK_INTERVAL:
        return session
    user = db.get(LocalUser, username)
    if user is None or not user.is_active:
        db.execute(delete(UserSession).where(UserSession.id == session.id))
        db.commit()
        return None
    if list(session.roles) != [user.role]:
        session.roles = [user.role]
    session.last_role_check_at = now
    db.commit()
    return session


def auth_bypass_enabled() -> bool:
    """MVP 公開デモ用のログイン認証バイパスが有効かどうか。

    ``CATALOG_AUTH_BYPASS=true`` に加えて、``CATALOG_ENV`` が
    :data:`AUTH_BYPASS_ENVS` に**明示的に**含まれる場合のみ有効にする。

    安全側（fail-closed）の許可リスト方式であることが重要。以前は
    「``CATALOG_ENV`` が ``production`` でなければ有効」という拒否リスト
    方式だったため、``CATALOG_ENV`` が未設定・別名（``prod`` / ``stg``）・
    大文字小文字違い・末尾空白のいずれでもバイパスが成立してしまった。
    認証を無効化するスイッチの既定は「無効」でなければならない。
    """
    if os.environ.get("CATALOG_AUTH_BYPASS", "").strip().lower() != "true":
        return False
    return os.environ.get("CATALOG_ENV", "").strip().lower() in AUTH_BYPASS_ENVS


def _bypass_session() -> UserSession:
    """バイパス時に使う、DB へ保存しない一時セッション。

    付与ロールは CATALOG_AUTH_BYPASS_ROLES（カンマ区切り）で指定でき、
    未指定なら閲覧のみの Catalog.Viewer とする。未知のロール名は無視する。
    ``last_role_check_at`` は DB へ保存されないため未設定のままでよい
    （issue #61 の再照合ロジックは DB 上のセッションにのみ適用される）。
    """
    raw = os.environ.get("CATALOG_AUTH_BYPASS_ROLES", "")
    roles = [r.strip() for r in raw.split(",") if r.strip() in ALL_ROLES]
    return UserSession(
        id="mvp-demo-bypass",
        user_sub=os.environ.get("CATALOG_AUTH_BYPASS_SUB", "demo@example.invalid"),
        display_name=os.environ.get("CATALOG_AUTH_BYPASS_NAME", "デモ利用者"),
        roles=roles or [ROLE_VIEWER],
        expires_at=_now() + SESSION_TTL,
    )


def current_session(request: Request, db: Session) -> UserSession | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        # MVP 公開デモ: ログインしていなくても閲覧できるようにする
        return _bypass_session() if auth_bypass_enabled() else None
    session = db.get(UserSession, session_id)
    if session is None or session.expires_at < _now():
        return _bypass_session() if auth_bypass_enabled() else None
    return _revalidate_local_session(db, session)


def require_role(get_db, *allowed: str):
    """FastAPI dependency: 401 when unauthenticated, 403 when the session
    lacks every allowed role (401/403 split per design §3.3)."""

    def _dependency(request: Request, db: Session = Depends(get_db)) -> UserSession:
        session = current_session(request, db)
        if session is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if not set(session.roles) & set(allowed):
            raise HTTPException(status_code=403, detail="insufficient role")
        return session

    return _dependency


def purge_expired_sessions(db: Session) -> int:
    """Housekeeping helper; returns the number of removed sessions."""
    result = db.execute(delete(UserSession).where(UserSession.expires_at < _now()))
    db.commit()
    return result.rowcount or 0


def revoke_user_sessions(db: Session, user_sub: str) -> int:
    """Immediately invalidate every session of a user (role-change / disable)."""
    result = db.execute(delete(UserSession).where(UserSession.user_sub == user_sub))
    db.commit()
    return result.rowcount or 0


def build_router(get_db) -> APIRouter:
    """Create the /auth router bound to the given DB session dependency."""
    router = APIRouter(prefix="/auth", tags=["auth"])

    def _audit_login_failed(db: Session, actor: str, reason: str) -> None:
        record_audit(
            db,
            actor=actor[:200],
            actor_roles=[],
            action=ACTION_LOGIN_FAILED,
            reason=reason[:200],
        )
        db.commit()

    @router.post("/login", name="auth_login_local")
    def login_local(
        payload: LocalLoginBody, response: Response, db: Session = Depends(get_db)
    ) -> dict:
        if auth_mode() != "local":
            raise HTTPException(status_code=404, detail="local login is disabled")
        username = payload.username.strip().lower()
        if not username:
            raise HTTPException(status_code=401, detail="invalid username or password")
        user = db.get(LocalUser, username)
        if user is None:
            verify_password(payload.password, _DUMMY_HASH)  # equalize timing
            _audit_login_failed(db, f"local:{username}", "unknown user")
            raise HTTPException(status_code=401, detail="invalid username or password")
        now = _now()
        if user.locked_until is not None and user.locked_until > now:
            _audit_login_failed(db, f"local:{username}", "account locked")
            raise HTTPException(status_code=423, detail="account is temporarily locked")
        if not user.is_active:
            verify_password(payload.password, _DUMMY_HASH)  # equalize timing
            # 401 (not 403): responses must not reveal that the name exists.
            _audit_login_failed(db, f"local:{username}", "inactive account")
            raise HTTPException(status_code=401, detail="invalid username or password")
        if not verify_password(payload.password, user.password_hash):
            user.failed_attempts += 1
            reason = "wrong password"
            if user.failed_attempts >= MAX_FAILED_LOGINS:
                user.locked_until = now + LOCKOUT_WINDOW
                user.failed_attempts = 0
                reason = "wrong password; account locked"
            _audit_login_failed(db, f"local:{username}", reason)
            raise HTTPException(status_code=401, detail="invalid username or password")
        user.failed_attempts = 0
        user.locked_until = None
        session = UserSession(
            id=secrets.token_urlsafe(32),
            user_sub=f"local:{username}",
            display_name=user.display_name or username,
            roles=[user.role],
            expires_at=now + SESSION_TTL,
        )
        db.add(session)
        record_audit(
            db,
            actor=session.user_sub,
            actor_roles=session.roles,
            action=ACTION_LOGIN,
        )
        db.commit()
        response.set_cookie(
            SESSION_COOKIE,
            session.id,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
            path="/",
        )
        return {"name": session.display_name, "roles": session.roles}

    @router.get("/login", name="auth_login")
    def login(db: Session = Depends(get_db)) -> Response:
        if auth_mode() == "local":
            # The static UI opens its login dialog when ?login=1 is present;
            # this keeps old bookmarks and the no-JS anchor working.
            return Response(status_code=302, headers={"Location": "/?login=1"})
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        # Purge abandoned login attempts, then persist this one.
        db.execute(delete(AuthRequest).where(AuthRequest.created_at < _now() - AUTH_REQUEST_TTL))
        db.add(AuthRequest(state=state, nonce=nonce, code_verifier=code_verifier))
        db.commit()
        params = {
            "client_id": _env("ENTRA_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": _redirect_uri(),
            "response_mode": "query",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = f"{_authority()}/oauth2/v2.0/authorize?{urlencode(params)}"
        response = Response(status_code=302, headers={"Location": url})
        # SameSite=Lax still sends this on the top-level GET redirect back
        # from Entra ID, but not on attacker-initiated cross-site subrequests.
        response.set_cookie(
            AUTH_REQ_COOKIE,
            state,
            max_age=int(AUTH_REQUEST_TTL.total_seconds()),
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
            path="/auth",
        )
        return response

    @router.get("/callback", name="auth_callback")
    def callback(
        request: Request, code: str, state: str, db: Session = Depends(get_db)
    ) -> Response:
        # Login-CSRF defence: the state must belong to THIS browser, not
        # merely exist in the DB (an attacker can mint a valid state by
        # starting their own login and replaying it here).
        browser_state = request.cookies.get(AUTH_REQ_COOKIE, "")
        if not secrets.compare_digest(browser_state, state):
            raise HTTPException(status_code=401, detail="login was not initiated by this browser")
        pending = db.get(AuthRequest, state)
        if pending is None or pending.created_at < _now() - AUTH_REQUEST_TTL:
            raise HTTPException(status_code=401, detail="unknown or expired state")
        db.delete(pending)  # single-use
        try:
            tokens = _exchange_code(code, pending.code_verifier)
            claims = validate_id_token(tokens.get("id_token", ""), pending.nonce, _fetch_jwks())
        except Exception as exc:
            # Observability for auth failures (design §3.3, issue #61).
            # Only our own HTTPException details are safe to persist; raw
            # exception text from token parsing can embed token material or
            # PII claims, so anything else is reduced to the class name.
            detail = exc.detail if isinstance(exc, HTTPException) else type(exc).__name__
            record_audit(
                db,
                actor="anonymous",
                actor_roles=[],
                action=ACTION_LOGIN_FAILED,
                reason=str(detail)[:200],
            )
            db.commit()
            raise
        session = UserSession(
            id=secrets.token_urlsafe(32),
            user_sub=str(claims["sub"]),
            display_name=str(claims.get("name") or claims.get("preferred_username") or ""),
            roles=list(claims.get("roles") or []),
            expires_at=_now() + SESSION_TTL,
        )
        db.add(session)
        record_audit(
            db,
            actor=session.user_sub,
            actor_roles=session.roles,
            action=ACTION_LOGIN,
        )
        db.commit()
        response = Response(status_code=302, headers={"Location": "/"})
        response.set_cookie(
            SESSION_COOKIE,
            session.id,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
            path="/",
        )
        response.delete_cookie(AUTH_REQ_COOKIE, path="/auth")
        return response

    @router.get("/logout", name="auth_logout")
    def logout(request: Request, db: Session = Depends(get_db)) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            session = db.get(UserSession, session_id)
            if session is not None:
                record_audit(
                    db,
                    actor=session.user_sub,
                    actor_roles=session.roles,
                    action=ACTION_LOGOUT,
                )
            db.execute(delete(UserSession).where(UserSession.id == session_id))
            db.commit()
        if auth_mode() == "local":
            logout_url = "/"
        else:
            logout_url = f"{_authority()}/oauth2/v2.0/logout?" + urlencode(
                {"post_logout_redirect_uri": _base_url()}
            )
        response = Response(status_code=302, headers={"Location": logout_url})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @router.get("/me", name="auth_me")
    def me(request: Request, db: Session = Depends(get_db)) -> dict:
        session = current_session(request, db)
        if session is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        return {
            "sub": session.user_sub,
            "name": session.display_name,
            "roles": session.roles,
        }

    return router
