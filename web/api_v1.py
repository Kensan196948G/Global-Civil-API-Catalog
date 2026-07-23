"""Read-only catalog API v1 (FastAPI) — Phase A of epic #46.

Serves catalog data from PostgreSQL. Write endpoints are deliberately
absent: per docs/epic-detailed-design-q4.md they must not be exposed
before the authentication layer (epic #45, Phase B) exists.

Run locally:
    CATALOG_DATABASE_URL=... uvicorn web.api_v1:app --port 49232
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, HTTPException, Query  # noqa: E402
from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db.models import CatalogEntry, VerificationResult  # noqa: E402
from db.session import make_session_factory  # noqa: E402

app = FastAPI(title="Global Civil API Catalog API", version="1.0.0")

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


def entry_to_dict(entry: CatalogEntry) -> dict[str, Any]:
    return {
        c.name: getattr(entry, c.name)
        for c in CatalogEntry.__table__.columns
        if c.name not in ("created_at", "updated_at")
    }


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
    stmt = select(CatalogEntry)
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
    if entry is None:
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
        "record_count": session.scalar(select(func.count()).select_from(CatalogEntry)),
        "verification_count": session.scalar(select(func.count()).select_from(VerificationResult)),
        "source": "postgresql",
    }
