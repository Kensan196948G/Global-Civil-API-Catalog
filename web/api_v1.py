"""Catalog API v1 (FastAPI) — Phase A read layer (epic #46) + Phase B
authenticated write layer (epic #45, Issue #59).

Reads are public. Writes require an Entra ID login session with the
appropriate app role (design §2.2 / §3.2):

    POST/PATCH  Catalog.Editor or Catalog.Admin
    DELETE      Catalog.Admin only (logical delete, FR-012)

Run locally:
    CATALOG_DATABASE_URL=... ENTRA_TENANT_ID=... ENTRA_CLIENT_ID=... \
    ENTRA_CLIENT_SECRET=... uvicorn web.api_v1:app --port 49232
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, HTTPException, Query, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.models import CatalogEntry, UserSession, VerificationResult  # noqa: E402
from db.session import make_session_factory  # noqa: E402
from web.auth import ROLE_ADMIN, ROLE_EDITOR, build_router, require_role  # noqa: E402

app = FastAPI(title="Global Civil API Catalog API", version="1.1.0")

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


def entry_to_dict(entry: CatalogEntry) -> dict[str, Any]:
    return {
        c.name: getattr(entry, c.name)
        for c in CatalogEntry.__table__.columns
        if c.name not in ("created_at", "updated_at", "deleted_at")
    }


# --- read (public) ---------------------------------------------------------


@app.get("/api/v1/entries")
def list_entries(
    category: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    api_key_required: str | None = None,
    keyword: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(CatalogEntry).where(CatalogEntry.deleted_at.is_(None))
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
    rows = session.scalars(stmt.order_by(CatalogEntry.id).limit(limit).offset(offset)).all()
    return {"total": total, "items": [entry_to_dict(e) for e in rows]}


@app.get("/api/v1/entries/{entry_id}")
def get_entry(entry_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    return entry_to_dict(entry)


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
            select(func.count()).select_from(CatalogEntry).where(CatalogEntry.deleted_at.is_(None))
        ),
        "verification_count": session.scalar(select(func.count()).select_from(VerificationResult)),
        "source": "postgresql",
    }


# --- write (authenticated, Phase B) ----------------------------------------

API_KEY_VALUES = ("required", "not_required", "unknown")
TRUST_RANKS = ("A", "B", "C", "D", "E")


class EntryCreate(BaseModel):
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
    """Partial update (FR-011); all fields optional, id immutable."""

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
    entry = CatalogEntry(**payload.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry_to_dict(entry)


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
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="no fields to update")
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.updated_at = func.now()
    session.commit()
    session.refresh(entry)
    return entry_to_dict(entry)


@app.delete(
    "/api/v1/entries/{entry_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
)
def delete_entry(
    entry_id: str,
    actor: UserSession = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    """FR-012: admin-only logical delete; the row and its history remain."""
    entry = session.get(CatalogEntry, entry_id)
    if entry is None or entry.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
    entry.deleted_at = func.now()
    session.commit()
