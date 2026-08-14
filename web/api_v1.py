"""Catalog API v1 (FastAPI) — Phase A read layer (epic #46) + Phase B
authenticated write layer (epic #45) + Phase C audit/versioning/approval
workflow (epic #47, design §4).

Reads are public but only expose ``published`` entries; staff (Editor/
Verifier/Approver/Admin sessions) also see drafts. Writes require an Entra
ID login session with the appropriate app role (design §2.2 / §3.2):

    POST/PATCH   Catalog.Editor or Catalog.Admin (change reason required)
    DELETE       Catalog.Admin only (logical delete + audit, FR-012)
    transitions  submit=Editor / review_ok=Verifier / approve=Approver
                 / send_back=Verifier·Approver (Admin can do all)
    restore      Catalog.Admin only (from a stored version, audited)

Every mutation writes an append-only audit_log row and a version snapshot.

Run locally:
    CATALOG_DATABASE_URL=... ENTRA_TENANT_ID=... ENTRA_CLIENT_ID=... \
    ENTRA_CLIENT_SECRET=... uvicorn web.api_v1:app --port 49232
"""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import Date, func, or_, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.audit import (  # noqa: E402
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_OPENAPI_IMPORT,
    ACTION_RESTORE,
    ACTION_TRANSITION,
    ACTION_TRY_IT,
    ACTION_UPDATE,
    ACTION_WEBHOOK_SUBSCRIBE,
    ACTION_WEBHOOK_TEST,
    ACTION_WEBHOOK_UNSUBSCRIBE,
    ACTION_WEBHOOK_UPDATE,
    entry_snapshot_dict,
    field_diff,
    record_audit,
    snapshot_entry,
)
from db.models import (  # noqa: E402
    WEBHOOK_EVENTS,
    AuditLog,
    CatalogEntry,
    CatalogEntryVersion,
    EntryWorkflow,
    UserSession,
    VerificationResult,
    WebhookSubscription,
)
from db.session import make_session_factory  # noqa: E402
from scripts.openapi_import import build_candidates  # noqa: E402
from scripts.url_guard import URLPolicyError, fetch_public_url, validate_public_url  # noqa: E402
from web.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VERIFIER,
    SESSION_COOKIE,
    build_router,
    current_session,
    purge_expired_sessions,
    require_role,
)
from web.ratelimit import RateLimiter  # noqa: E402
from web.webhooks import deliver, dispatch_webhooks  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Housekeeping on startup: purge expired login sessions."""
    try:
        factory = make_session_factory()
        with factory() as session:
            purge_expired_sessions(session)
    except Exception as exc:  # noqa: BLE001 - startup must not take the API down.
        print(f"warn: session purge skipped ({type(exc).__name__})", flush=True)
    yield


app = FastAPI(title="Global Civil API Catalog API", version="1.3.0", lifespan=lifespan)

# --- rate limiting ----------------------------------------------------------
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 300  # 10 attempts / 5 minutes per client IP
WRITE_LIMIT = 60
WRITE_WINDOW_SECONDS = 60  # 60 mutations / minute per session (or IP)

login_limiter = RateLimiter(LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
write_limiter = RateLimiter(WRITE_LIMIT, WRITE_WINDOW_SECONDS)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Login is limited per client IP; mutations per session (fallback IP)."""
    path = request.url.path
    if request.method == "POST" and path == "/auth/login":
        if not login_limiter.allow(_client_ip(request)):
            return JSONResponse(
                status_code=429, content={"detail": "rate limit exceeded; retry later"}
            )
    elif request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/v1/"):
        key = request.cookies.get(SESSION_COOKIE) or _client_ip(request)
        if not write_limiter.allow(key):
            return JSONResponse(
                status_code=429, content={"detail": "rate limit exceeded; retry later"}
            )
    return await call_next(request)


@app.middleware("http")
async def csrf_origin_check(request, call_next):
    """Defence-in-depth CSRF guard for state-changing requests: when the
    browser sends an Origin header it must match our own origin. SameSite=Lax
    already blocks cross-site cookie sends in modern browsers; this closes
    the gap for legacy/edge cases (adversarial review, PR #60)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            allowed = os.environ.get("CATALOG_BASE_URL", "http://localhost:49232").rstrip("/")
            if origin.rstrip("/") != allowed:
                return JSONResponse(
                    status_code=403, content={"detail": "cross-origin write rejected"}
                )
    return await call_next(request)


_session_factory = None


def get_session():
    global _session_factory
    if _session_factory is None:
        _session_factory = make_session_factory()
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


app.include_router(build_router(get_session))

require_editor = require_role(get_session, ROLE_EDITOR, ROLE_ADMIN)
require_admin = require_role(get_session, ROLE_ADMIN)
require_staff = require_role(get_session, ROLE_EDITOR, ROLE_VERIFIER, ROLE_APPROVER, ROLE_ADMIN)

_STAFF_ROLES = {ROLE_EDITOR, ROLE_VERIFIER, ROLE_APPROVER, ROLE_ADMIN}


def _staff_session(request: Request, db: Session) -> UserSession | None:
    """Session with any staff role; anonymous/viewer-only returns None."""
    session = current_session(request, db)
    if session is None or not set(session.roles) & _STAFF_ROLES:
        return None
    return session


def entry_to_dict(entry: CatalogEntry, workflow_state: str | None = None) -> dict[str, Any]:
    payload = {
        c.name: getattr(entry, c.name)
        for c in CatalogEntry.__table__.columns
        if c.name not in ("created_at", "updated_at", "deleted_at")
    }
    if workflow_state is not None:
        payload["workflow_state"] = workflow_state
    return payload


def _workflow_state(session: Session, record_id: str) -> str:
    row = session.get(EntryWorkflow, record_id)
    # Entries predating the workflow tables are grandfathered as published.
    return row.state if row is not None else "published"


# --- read (public) ---------------------------------------------------------


@app.get("/api/v1/entries")
def list_entries(
    request: Request,
    category: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    api_key_required: str | None = None,
    keyword: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(CatalogEntry, EntryWorkflow.state)
        .outerjoin(EntryWorkflow, EntryWorkflow.record_id == CatalogEntry.id)
        .where(CatalogEntry.deleted_at.is_(None))
    )
    if _staff_session(request, session) is None:
        # Anonymous / viewer: published entries only (design §4.2).
        stmt = stmt.where(func.coalesce(EntryWorkflow.state, "published") == "published")
    if category:
        stmt = stmt.where(CatalogEntry.category == category)
    if provider:
        stmt = stmt.where(CatalogEntry.provider == provider)
    if status:
        stmt = stmt.where(CatalogEntry.connection_status == status)
    if api_key_required:
        stmt = stmt.where(CatalogEntry.api_key_required == api_key_required)
    if keyword:
        tokens = [token for token in keyword.replace(",", " ").split() if token]
        for token in tokens:
            pattern = f"%{token}%"
            stmt = stmt.where(
                or_(
                    CatalogEntry.id.ilike(pattern),
                    CatalogEntry.name.ilike(pattern),
                    CatalogEntry.sub_category.ilike(pattern),
                    CatalogEntry.provider.ilike(pattern),
                    CatalogEntry.region.ilike(pattern),
                    CatalogEntry.official_url.ilike(pattern),
                    CatalogEntry.document_url.ilike(pattern),
                    CatalogEntry.usage_summary.ilike(pattern),
                    CatalogEntry.usage_notes.ilike(pattern),
                    CatalogEntry.risk_note.ilike(pattern),
                    func.array_to_string(CatalogEntry.tags, " ").ilike(pattern),
                    func.array_to_string(CatalogEntry.data_formats, " ").ilike(pattern),
                )
            )
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(stmt.order_by(CatalogEntry.id).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [entry_to_dict(e, state or "published") for e, state in rows],
    }


@app.get("/api/v1/entries/{entry_id}")
def get_entry(
    request: Request, entry_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    state = _workflow_state(session, entry_id)
    if state != "published" and _staff_session(request, session) is None:
        # Unpublished entries are indistinguishable from missing ones.
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    return entry_to_dict(entry, state)


@app.get("/api/v1/verifications")
def list_verifications(
    api_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(VerificationResult).order_by(VerificationResult.verified_at.desc())
    if api_id:
        stmt = stmt.where(VerificationResult.api_id == api_id)
    rows = session.scalars(stmt.limit(limit)).all()
    return {
        "items": [
            {c.name: getattr(r, c.name) for c in VerificationResult.__table__.columns} for r in rows
        ]
    }


@app.get("/api/v1/metadata")
def metadata(session: Session = Depends(get_session)) -> dict[str, Any]:
    # Counts are derived live from the database — never stored — so the
    # record_count drift class of bugs (PR #37) cannot recur here.
    return {
        "record_count": session.scalar(
            select(func.count())
            .select_from(CatalogEntry)
            .outerjoin(EntryWorkflow, EntryWorkflow.record_id == CatalogEntry.id)
            .where(CatalogEntry.deleted_at.is_(None))
            .where(func.coalesce(EntryWorkflow.state, "published") == "published")
        ),
        "verification_count": session.scalar(select(func.count()).select_from(VerificationResult)),
        "source": "postgresql",
    }


@app.get("/api/v1/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    """DB-aware health probe for load balancers and monitoring runbooks."""
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - health must report, not raise.
        database = "unavailable"
    return {"status": "ok", "database": database}


MAX_TRY_BYTES = 64 * 1024


class TryItRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000, pattern=r"^https?://")
    timeout: int = Field(default=10, ge=3, le=30)


@app.post("/api/v1/try-it")
def try_it(
    payload: TryItRequest,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Editor-only safe execution of a public endpoint (issue #66 backend).

    The URL passes the same validate-resolve-pin SSRF guard as the weekly
    verifier, responses are capped, and every call is audit-logged.
    """
    blocked = validate_public_url(payload.url, resolve=True)
    if blocked is not None:
        raise HTTPException(status_code=422, detail=f"blocked by URL policy ({blocked})")
    try:
        status, body, final_url = fetch_public_url(
            payload.url,
            timeout=payload.timeout,
            max_bytes=MAX_TRY_BYTES,
            user_agent="Global-Civil-API-Catalog/0.1 try-it",
        )
    except URLPolicyError as exc:
        raise HTTPException(status_code=422, detail=f"blocked by URL policy ({exc})") from exc
    except Exception as exc:  # noqa: BLE001 - surface a stable 502 for CLI/UI.
        raise HTTPException(
            status_code=502, detail=f"request failed: {type(exc).__name__}"
        ) from exc
    preview = body[:4096].decode("utf-8", errors="replace")
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_TRY_IT,
        diff={
            "url": payload.url,
            "http_status": status,
            "response_size_bytes": len(body),
        },
        reason="try-it console",
    )
    session.commit()
    return {
        "status": status,
        "final_url": final_url,
        "response_size_bytes": len(body),
        "truncated": len(body) >= MAX_TRY_BYTES,
        "preview": preview,
    }


# --- write (authenticated, Phase B) ----------------------------------------

API_KEY_VALUES = ("required", "not_required", "unknown")
TRUST_RANKS = ("A", "B", "C", "D", "E")

# URL fields the verifier or UI will later dereference. Saved values must
# pass the SSRF guard (IP-literal/scheme checks; templates with {} are
# format-checked only — the verifier skips them, and re-validates with DNS
# resolution at fetch time as the second layer).
_GUARDED_URL_FIELDS = (
    "official_url",
    "document_url",
    "endpoint_template",
    "sample_endpoint",
)


def _reject_unsafe_urls(changes: dict[str, Any]) -> None:
    for field in _GUARDED_URL_FIELDS:
        value = changes.get(field)
        if not value or "{" in value:
            continue
        reason = validate_public_url(value, resolve=False)
        if reason is not None:
            raise HTTPException(
                status_code=422, detail=f"{field}: blocked by URL policy ({reason})"
            )


class EntryCreate(BaseModel):
    # Change reason is mandatory for every mutation (design §4.1, epic #47).
    reason: str = Field(min_length=1, max_length=1000)
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    sub_category: str | None = None
    provider: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    region: str | None = None
    official_url: str = Field(pattern=r"^https?://")
    document_url: str = Field(pattern=r"^https?://")
    endpoint_template: str | None = None
    sample_endpoint: str | None = None
    data_formats: list[str] = []
    api_key_required: str = Field(pattern=f"^({'|'.join(API_KEY_VALUES)})$")
    auth_type: str | None = None
    license_note: str | None = None
    commercial_use: str | None = None
    update_frequency: str | None = None
    connection_status: str = Field(min_length=1)
    trust_rank: str | None = Field(default=None, pattern=f"^[{''.join(TRUST_RANKS)}]$")
    connection_priority: int | None = None
    business_fit_score: int | None = None
    integration_score: int | None = None
    tags: list[str] = []
    usage_summary: str | None = None
    usage_notes: str | None = None
    risk_note: str | None = None


class EntryPatch(BaseModel):
    """Partial update (FR-011); data fields optional, id immutable,
    change reason mandatory (design §4.1)."""

    reason: str = Field(min_length=1, max_length=1000)
    name: str | None = Field(default=None, min_length=1)
    category: str | None = None
    sub_category: str | None = None
    provider: str | None = None
    provider_type: str | None = None
    region: str | None = None
    official_url: str | None = Field(default=None, pattern=r"^https?://")
    document_url: str | None = Field(default=None, pattern=r"^https?://")
    endpoint_template: str | None = None
    sample_endpoint: str | None = None
    data_formats: list[str] | None = None
    api_key_required: str | None = Field(default=None, pattern=f"^({'|'.join(API_KEY_VALUES)})$")
    auth_type: str | None = None
    license_note: str | None = None
    commercial_use: str | None = None
    update_frequency: str | None = None
    connection_status: str | None = None
    trust_rank: str | None = Field(default=None, pattern=f"^[{''.join(TRUST_RANKS)}]$")
    connection_priority: int | None = None
    business_fit_score: int | None = None
    integration_score: int | None = None
    tags: list[str] | None = None
    usage_summary: str | None = None
    usage_notes: str | None = None
    risk_note: str | None = None


def _create_entry_record(
    session: Session,
    payload: EntryCreate,
    actor: UserSession,
) -> CatalogEntry:
    """Shared create path: validation, draft workflow, snapshot, audit."""
    if session.get(CatalogEntry, payload.id) is not None:
        raise HTTPException(status_code=409, detail=f"entry {payload.id} already exists")
    data = payload.model_dump(exclude={"reason"})
    _reject_unsafe_urls(data)
    entry = CatalogEntry(**data)
    session.add(entry)
    # New API-created entries enter the approval workflow as drafts and are
    # invisible to the public until approved (design §4.2).
    session.add(EntryWorkflow(record_id=entry.id, state="draft"))
    session.flush()
    snapshot_entry(session, entry, actor.user_sub)
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_CREATE,
        record_id=entry.id,
        diff=field_diff({}, entry_snapshot_dict(entry)),
        reason=payload.reason,
    )
    return entry


@app.post("/api/v1/entries", status_code=201)
def create_entry(
    payload: EntryCreate,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    entry = _create_entry_record(session, payload, actor)
    session.commit()
    dispatch_webhooks(
        session,
        "entry.created",
        {
            "record_id": entry.id,
            "name": entry.name,
            "actor": actor.user_sub,
            "reason": payload.reason,
        },
    )
    session.refresh(entry)
    return entry_to_dict(entry, "draft")


class OpenApiImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    spec: dict[str, Any]
    reason: str = Field(min_length=1, max_length=1000)
    max_candidates: int = Field(default=10, ge=1, le=50)


def _find_duplicate(session: Session, candidate: dict[str, Any]) -> str | None:
    if session.get(CatalogEntry, candidate["id"]) is not None:
        return "id"
    same_endpoint = session.scalar(
        select(CatalogEntry)
        .where(
            CatalogEntry.official_url == candidate["official_url"],
            CatalogEntry.endpoint_template == candidate["endpoint_template"],
        )
        .limit(1)
    )
    if same_endpoint is not None:
        return "official_url+endpoint"
    same_name = session.scalar(
        select(CatalogEntry)
        .where(func.lower(CatalogEntry.name) == candidate["name"].lower())
        .limit(1)
    )
    if same_name is not None:
        return "name"
    return None


@app.post("/api/v1/import/openapi", status_code=201)
def import_openapi(
    payload: OpenApiImportRequest,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Import an OpenAPI 3.x document as draft entries (issue #65, MVP)."""
    candidates, errors = build_candidates(payload.spec, max_candidates=payload.max_candidates)
    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_endpoints: set[tuple[str, str]] = set()
    seen_names: set[str] = set()
    for candidate in candidates:
        if candidate["id"] in seen_ids:
            skipped.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "reason": "duplicate within import (id)",
                }
            )
            continue
        endpoint_key = (candidate["official_url"], candidate["endpoint_template"])
        if endpoint_key in seen_endpoints:
            skipped.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "reason": "duplicate within import (endpoint)",
                }
            )
            continue
        normalized_name = candidate["name"].lower()
        if normalized_name in seen_names:
            skipped.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "reason": "duplicate within import (name)",
                }
            )
            continue
        duplicate = _find_duplicate(session, candidate)
        if duplicate is not None:
            skipped.append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "reason": f"duplicate by {duplicate}",
                }
            )
            continue
        seen_ids.add(candidate["id"])
        seen_endpoints.add(endpoint_key)
        seen_names.add(normalized_name)
        create = EntryCreate(
            **{
                **candidate,
                "reason": f"{payload.reason} (OpenAPI import: {payload.name})",
            }
        )
        entry = _create_entry_record(session, create, actor)
        created.append({"id": entry.id, "name": entry.name, "workflow_state": "draft"})
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_OPENAPI_IMPORT,
        diff={
            "source_name": payload.name,
            "created": len(created),
            "skipped_duplicates": len(skipped),
        },
        reason=payload.reason,
    )
    session.commit()
    for item in created:
        dispatch_webhooks(
            session,
            "entry.created",
            {
                "record_id": item["id"],
                "name": item["name"],
                "actor": actor.user_sub,
                "reason": f"{payload.reason} (OpenAPI import)",
            },
        )
    return {"created": created, "skipped_duplicates": skipped, "errors": errors}


@app.patch("/api/v1/entries/{entry_id}")
def update_entry(
    entry_id: str,
    payload: EntryPatch,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # FOR UPDATE serialises all writers per record (adversarial review:
    # non-atomic version numbering under concurrency).
    entry = session.get(CatalogEntry, entry_id, with_for_update=True)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    state = _workflow_state(session, entry_id)
    if state not in ("draft", "rejected"):
        # State-machine enforcement (adversarial review): published or
        # in-review content cannot be edited in place — reopen it first so
        # every change re-enters the approval flow.
        raise HTTPException(
            status_code=409,
            detail=(
                f"content changes require draft state (current: {state}); "
                "use the 'reopen' transition first"
            ),
        )
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if not changes:
        raise HTTPException(status_code=422, detail="no fields to update")
    _reject_unsafe_urls(changes)
    before = entry_snapshot_dict(entry)
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.updated_at = func.now()
    session.flush()
    session.refresh(entry)
    snapshot_entry(session, entry, actor.user_sub)
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_UPDATE,
        record_id=entry.id,
        diff=field_diff(before, entry_snapshot_dict(entry)),
        reason=payload.reason,
    )
    session.commit()
    dispatch_webhooks(
        session,
        "entry.updated",
        {
            "record_id": entry.id,
            "name": entry.name,
            "changed_fields": sorted(changes),
            "actor": actor.user_sub,
            "reason": payload.reason,
        },
    )
    return entry_to_dict(entry, _workflow_state(session, entry_id))


@app.delete(
    "/api/v1/entries/{entry_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
)
def delete_entry(
    entry_id: str,
    reason: str = Query(min_length=1, max_length=1000),
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    """FR-012: admin-only logical delete; the row and its history remain."""
    entry = session.get(CatalogEntry, entry_id, with_for_update=True)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    entry.deleted_at = func.now()
    # A deleted entry drops back to draft so a later restore always
    # re-enters the approval flow before becoming publicly visible again.
    workflow = session.get(EntryWorkflow, entry_id, with_for_update=True)
    before_state = workflow.state if workflow is not None else "published"
    if workflow is None:
        session.add(EntryWorkflow(record_id=entry_id, state="draft"))
    else:
        workflow.state = "draft"
        workflow.updated_at = func.now()
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_DELETE,
        record_id=entry.id,
        diff={
            "deleted": {"before": False, "after": True},
            "state": {"before": before_state, "after": "draft"},
        },
        reason=reason,
    )
    session.commit()
    dispatch_webhooks(
        session,
        "entry.deleted",
        {
            "record_id": entry.id,
            "name": entry.name,
            "actor": actor.user_sub,
            "reason": reason,
        },
    )


# --- workflow / versions / audit (Phase C) ---------------------------------

# design §4.2: who may drive which transition, and from which states.
_TRANSITIONS: dict[str, dict[str, Any]] = {
    "submit": {
        "from": {"draft", "rejected"},
        "to": "in_review",
        "roles": {ROLE_EDITOR, ROLE_ADMIN},
    },
    "review_ok": {
        "from": {"in_review"},
        "to": "pending_approval",
        "roles": {ROLE_VERIFIER, ROLE_ADMIN},
    },
    "approve": {
        "from": {"pending_approval"},
        "to": "published",
        "roles": {ROLE_APPROVER, ROLE_ADMIN},
    },
    "send_back": {
        "from": {"in_review", "pending_approval"},
        "to": "draft",
        "roles": {ROLE_VERIFIER, ROLE_APPROVER, ROLE_ADMIN},
    },
    # Published content is immutable in place; editing requires an explicit,
    # audited reopen back to draft (adversarial review, PR #68).
    "reopen": {"from": {"published"}, "to": "draft", "roles": {ROLE_EDITOR, ROLE_ADMIN}},
}


class TransitionRequest(BaseModel):
    action: str = Field(pattern=f"^({'|'.join(_TRANSITIONS)})$")
    reason: str = Field(min_length=1, max_length=1000)


@app.post("/api/v1/entries/{entry_id}/transitions")
def transition_entry(
    entry_id: str,
    payload: TransitionRequest,
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    # Lock order (entry -> workflow) matches the other mutating endpoints so
    # concurrent transitions serialise instead of overwriting each other
    # (adversarial review: non-linearised transitions).
    entry = session.get(CatalogEntry, entry_id, with_for_update=True)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    rule = _TRANSITIONS[payload.action]
    if not set(actor.roles) & rule["roles"]:
        raise HTTPException(status_code=403, detail=f"role cannot perform '{payload.action}'")
    workflow = session.get(EntryWorkflow, entry_id, with_for_update=True)
    if workflow is None:
        workflow = EntryWorkflow(record_id=entry_id, state="published")
        session.add(workflow)
    if workflow.state not in rule["from"]:
        raise HTTPException(
            status_code=409,
            detail=f"cannot '{payload.action}' from state '{workflow.state}'",
        )
    before_state = workflow.state
    workflow.state = rule["to"]
    workflow.updated_at = func.now()
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_TRANSITION,
        record_id=entry_id,
        diff={"state": {"before": before_state, "after": rule["to"]}},
        reason=payload.reason,
    )
    session.commit()
    dispatch_webhooks(
        session,
        "entry.workflow_transition",
        {
            "record_id": entry_id,
            "name": entry.name,
            "from": before_state,
            "to": rule["to"],
            "actor": actor.user_sub,
            "reason": payload.reason,
        },
    )
    return {"record_id": entry_id, "state": rule["to"]}


@app.get("/api/v1/entries/{entry_id}/versions")
def list_versions(
    entry_id: str,
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = session.scalars(
        select(CatalogEntryVersion)
        .where(CatalogEntryVersion.record_id == entry_id)
        .order_by(CatalogEntryVersion.version.desc())
    ).all()
    return {
        "items": [
            {"version": r.version, "created_at": r.created_at, "created_by": r.created_by}
            for r in rows
        ]
    }


@app.get("/api/v1/entries/{entry_id}/versions/{version}")
def get_version(
    entry_id: str,
    version: int,
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = session.get(CatalogEntryVersion, (entry_id, version))
    if row is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {"version": row.version, "created_by": row.created_by, "snapshot": row.snapshot}


class RestoreRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


# Columns that must never be overwritten by a restore.
_RESTORE_EXCLUDED = {"id", "created_at", "updated_at", "deleted_at"}


@app.post("/api/v1/entries/{entry_id}/restore")
def restore_entry(
    entry_id: str,
    payload: RestoreRequest,
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Admin-only restore from a stored version; also revives a logically
    deleted entry (design §4.2 復元). Restored content re-enters the
    approval flow: like PATCH, it is only possible in draft/rejected state
    (deletion always drops the entry back to draft)."""
    entry = session.get(CatalogEntry, entry_id, with_for_update=True)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    state = _workflow_state(session, entry_id)
    if state not in ("draft", "rejected"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"restore requires draft state (current: {state}); "
                "use the 'reopen' transition first"
            ),
        )
    stored = session.get(CatalogEntryVersion, (entry_id, payload.version))
    if stored is None:
        raise HTTPException(status_code=404, detail="version not found")
    before = entry_snapshot_dict(entry)
    for field, value in stored.snapshot.items():
        if field in _RESTORE_EXCLUDED or field not in CatalogEntry.__table__.columns:
            continue
        # Snapshots are JSON, so non-JSON-native column types come back as
        # strings; coerce them before writing (CodeRabbit, PR #68).
        column = CatalogEntry.__table__.columns[field]
        if isinstance(column.type, Date) and isinstance(value, str):
            value = date.fromisoformat(value)
        setattr(entry, field, value)
    entry.deleted_at = None
    entry.updated_at = func.now()
    session.flush()
    session.refresh(entry)
    snapshot_entry(session, entry, actor.user_sub)
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_RESTORE,
        record_id=entry_id,
        diff=field_diff(before, entry_snapshot_dict(entry)),
        reason=payload.reason,
    )
    session.commit()
    dispatch_webhooks(
        session,
        "entry.restored",
        {
            "record_id": entry.id,
            "name": entry.name,
            "version": payload.version,
            "actor": actor.user_sub,
            "reason": payload.reason,
        },
    )
    return entry_to_dict(entry, _workflow_state(session, entry_id))


@app.get("/api/v1/audit")
def list_audit(
    record_id: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(AuditLog).order_by(AuditLog.seq.desc())
    if record_id:
        stmt = stmt.where(AuditLog.record_id == record_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = session.scalars(stmt.limit(limit)).all()
    return {
        "items": [{c.name: getattr(r, c.name) for c in AuditLog.__table__.columns} for r in rows]
    }


# --- in-app tasks / notifications (epic #49 step 2) ------------------------


def _task_groups_for_roles(roles: set[str]) -> list[tuple[str, str]]:
    """(workflow_state, task_type) pairs visible to the session's roles."""
    groups: list[tuple[str, str]] = []
    if roles & {ROLE_VERIFIER, ROLE_ADMIN}:
        groups.append(("in_review", "review"))
    if roles & {ROLE_APPROVER, ROLE_ADMIN}:
        groups.append(("pending_approval", "approval"))
    if roles & {ROLE_EDITOR, ROLE_ADMIN}:
        groups.append(("rejected", "fix"))
    return groups


@app.get("/api/v1/tasks")
def list_tasks(
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Role-aware task queue: entries waiting for this user's role."""
    groups = _task_groups_for_roles(set(actor.roles))
    states = [state for state, _ in groups]
    if not states:
        return {"tasks": [], "counts": {}}
    rows = session.execute(
        select(CatalogEntry, EntryWorkflow)
        .join(EntryWorkflow, EntryWorkflow.record_id == CatalogEntry.id)
        .where(CatalogEntry.deleted_at.is_(None))
        .where(EntryWorkflow.state.in_(states))
        .order_by(EntryWorkflow.updated_at.desc())
    ).all()
    tasks = []
    for entry, workflow in rows:
        tasks.append(
            {
                "record_id": entry.id,
                "name": entry.name,
                "state": workflow.state,
                "updated_at": (
                    workflow.updated_at.isoformat() if workflow.updated_at is not None else None
                ),
                "task_type": next(
                    (kind for state, kind in groups if state == workflow.state),
                    "other",
                ),
            }
        )
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["task_type"]] = counts.get(task["task_type"], 0) + 1
    return {"tasks": tasks, "counts": counts}


@app.get("/api/v1/audit/export.csv")
def export_audit_csv(
    limit: int = Query(5000, ge=1, le=10000),
    actor: UserSession = Depends(require_staff),
    session: Session = Depends(get_session),
) -> Response:
    """Staff CSV export of the audit log (for review/evidence files)."""
    rows = session.scalars(select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit)).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["seq", "at", "actor", "actor_roles", "action", "record_id", "reason", "diff"])
    for row in rows:
        writer.writerow(
            [
                row.seq,
                row.at.isoformat() if row.at is not None else "",
                row.actor,
                ",".join(row.actor_roles or []),
                row.action,
                row.record_id or "",
                row.reason or "",
                json.dumps(row.diff, ensure_ascii=False) if row.diff else "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="catalog_audit_log.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- webhook subscriptions (outbound notifications) -------------------------


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000, pattern=r"^https?://")
    events: list[str] = Field(min_length=1)
    secret: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class WebhookPatch(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    name: str | None = None
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    reset_secret: bool = False


def _webhook_to_dict(
    subscription: WebhookSubscription, include_secret: bool = False
) -> dict[str, Any]:
    payload = {
        c.name: getattr(subscription, c.name)
        for c in WebhookSubscription.__table__.columns
    }
    if payload.get("last_delivery_at") is not None:
        payload["last_delivery_at"] = payload["last_delivery_at"].isoformat()
    if not include_secret:
        payload.pop("secret", None)
    return payload


def _validate_webhook_events(events: list[str]) -> None:
    unknown = [event for event in events if event not in WEBHOOK_EVENTS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown events: {', '.join(unknown)}")


@app.get("/api/v1/webhooks")
def list_webhooks(
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = session.scalars(
        select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
    ).all()
    return {"items": [_webhook_to_dict(row) for row in rows]}


@app.post("/api/v1/webhooks", status_code=201)
def create_webhook(
    payload: WebhookCreate,
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _validate_webhook_events(payload.events)
    reason = validate_public_url(payload.url, resolve=False)
    if reason is not None:
        raise HTTPException(status_code=422, detail=f"url: blocked by URL policy ({reason})")
    subscription = WebhookSubscription(
        id=f"wh_{secrets.token_urlsafe(8)}",
        name=payload.name,
        url=payload.url,
        events=payload.events,
        secret=payload.secret,
        is_active=True,
        created_by=actor.user_sub,
    )
    session.add(subscription)
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_WEBHOOK_SUBSCRIBE,
        record_id=subscription.id,
        diff={"name": payload.name, "url": payload.url, "events": payload.events},
        reason=payload.reason,
    )
    session.commit()
    return _webhook_to_dict(subscription, include_secret=True)


@app.patch("/api/v1/webhooks/{webhook_id}")
def update_webhook(
    webhook_id: str,
    payload: WebhookPatch,
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    subscription = session.get(WebhookSubscription, webhook_id, with_for_update=True)
    if subscription is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    changes: dict[str, Any] = {}
    if payload.name is not None:
        subscription.name = payload.name
        changes["name"] = payload.name
    if payload.url is not None:
        reason = validate_public_url(payload.url, resolve=False)
        if reason is not None:
            raise HTTPException(status_code=422, detail=f"url: blocked by URL policy ({reason})")
        subscription.url = payload.url
        changes["url"] = payload.url
    if payload.events is not None:
        _validate_webhook_events(payload.events)
        subscription.events = payload.events
        changes["events"] = payload.events
    if payload.is_active is not None:
        subscription.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    reset_secret = None
    if payload.reset_secret:
        reset_secret = secrets.token_urlsafe(24)
        subscription.secret = reset_secret
        changes["secret"] = "rotated"
    if not changes:
        raise HTTPException(status_code=422, detail="no fields to update")
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_WEBHOOK_UPDATE,
        record_id=subscription.id,
        diff=changes,
        reason=payload.reason,
    )
    session.commit()
    return _webhook_to_dict(subscription, include_secret=reset_secret is not None)


@app.delete("/api/v1/webhooks/{webhook_id}", status_code=204, response_model=None)
def delete_webhook(
    webhook_id: str,
    reason: str = Query(min_length=1, max_length=1000),
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    subscription = session.get(WebhookSubscription, webhook_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_WEBHOOK_UNSUBSCRIBE,
        record_id=subscription.id,
        diff={"name": subscription.name, "url": subscription.url},
        reason=reason,
    )
    session.delete(subscription)
    session.commit()


@app.post("/api/v1/webhooks/{webhook_id}/test")
def test_webhook(
    webhook_id: str,
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    subscription = session.get(WebhookSubscription, webhook_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    delivery_id, status = deliver(
        subscription,
        "test",
        {"message": f"test delivery for {subscription.name} ({actor.user_sub})"},
    )
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_WEBHOOK_TEST,
        record_id=subscription.id,
        diff={"delivery_id": delivery_id, "status": status},
        reason="webhook test delivery",
    )
    session.commit()
    return {"id": subscription.id, "delivery_id": delivery_id, "status": status}
