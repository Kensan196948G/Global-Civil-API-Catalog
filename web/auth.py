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
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.audit import ACTION_LOGIN, ACTION_LOGIN_FAILED, ACTION_LOGOUT, record_audit
from db.models import AuthRequest, UserSession

SESSION_COOKIE = "catalog_session"
# Binds the pending login to the browser that started it (login-CSRF
# defence): the callback only accepts a state that this browser initiated.
AUTH_REQ_COOKIE = "catalog_auth_req"
SESSION_TTL = timedelta(hours=8)
AUTH_REQUEST_TTL = timedelta(minutes=10)
CLOCK_SKEW_SECONDS = 300  # design §3.3

ROLE_ADMIN = "Catalog.Admin"
ROLE_EDITOR = "Catalog.Editor"
ROLE_VERIFIER = "Catalog.Verifier"
ROLE_APPROVER = "Catalog.Approver"
ROLE_VIEWER = "Catalog.Viewer"


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


def current_session(request: Request, db: Session) -> UserSession | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    session = db.get(UserSession, session_id)
    if session is None or session.expires_at < _now():
        return None
    return session


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


def build_router(get_db) -> APIRouter:
    """Create the /auth router bound to the given DB session dependency."""
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.get("/login", name="auth_login")
    def login(db: Session = Depends(get_db)) -> Response:
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
            record_audit(
                db,
                actor="anonymous",
                actor_roles=[],
                action=ACTION_LOGIN_FAILED,
                reason=str(exc)[:500],
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
