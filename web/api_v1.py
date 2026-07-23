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

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.audit import (  # noqa: E402
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_RESTORE,
    ACTION_TRANSITION,
    ACTION_UPDATE,
    entry_snapshot_dict,
    field_diff,
    record_audit,
    snapshot_entry,
)
from db.models import (  # noqa: E402
    AuditLog,
    CatalogEntry,
    CatalogEntryVersion,
    EntryWorkflow,
    UserSession,
    VerificationResult,
)
from db.session import make_session_factory  # noqa: E402
from scripts.url_guard import validate_public_url  # noqa: E402
from web.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_APPROVER,
    ROLE_EDITOR,
    ROLE_VERIFIER,
    build_router,
    current_session,
    require_role,
)

app = FastAPI(title="Global Civil API Catalog API", version="1.2.0")


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
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                CatalogEntry.name.ilike(pattern),
                CatalogEntry.provider.ilike(pattern),
                CatalogEntry.usage_summary.ilike(pattern),
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


@app.post("/api/v1/entries", status_code=201)
def create_entry(
    payload: EntryCreate,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
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
    session.commit()
    session.refresh(entry)
    return entry_to_dict(entry, "draft")


@app.patch("/api/v1/entries/{entry_id}")
def update_entry(
    entry_id: str,
    payload: EntryPatch,
    actor: UserSession = Depends(require_editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
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
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    entry.deleted_at = func.now()
    record_audit(
        session,
        actor=actor.user_sub,
        actor_roles=actor.roles,
        action=ACTION_DELETE,
        record_id=entry.id,
        diff={"deleted": {"before": False, "after": True}},
        reason=reason,
    )
    session.commit()


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
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    rule = _TRANSITIONS[payload.action]
    if not set(actor.roles) & rule["roles"]:
        raise HTTPException(status_code=403, detail=f"role cannot perform '{payload.action}'")
    workflow = session.get(EntryWorkflow, entry_id)
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
    deleted entry (design §4.2 復元)."""
    entry = session.get(CatalogEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    stored = session.get(CatalogEntryVersion, (entry_id, payload.version))
    if stored is None:
        raise HTTPException(status_code=404, detail="version not found")
    before = entry_snapshot_dict(entry)
    for field, value in stored.snapshot.items():
        if field in _RESTORE_EXCLUDED or field not in CatalogEntry.__table__.columns:
            continue
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
