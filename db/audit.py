"""Audit and versioning plumbing (Phase C, epic #47 — design §4).

Every mutating operation goes through :func:`record_audit` (append-only)
and :func:`snapshot_entry` (immutable pre-change copy). Application code
never updates or deletes rows in these tables; the DB-role enforcement is
part of the production cutover (issue #47).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import AuditLog, CatalogEntry, CatalogEntryVersion

# Action vocabulary kept flat so the audit log stays greppable.
ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_RESTORE = "restore"
ACTION_TRANSITION = "workflow_transition"
ACTION_LOGIN = "login"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOGOUT = "logout"


def entry_snapshot_dict(entry: CatalogEntry) -> dict[str, Any]:
    """JSON-safe full snapshot of an entry row (audit/version payload)."""
    payload: dict[str, Any] = {}
    for column in CatalogEntry.__table__.columns:
        value = getattr(entry, column.name)
        payload[column.name] = value if _json_safe(value) else str(value)
    return payload


def _json_safe(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, list, dict))


def record_audit(
    session: Session,
    *,
    actor: str,
    actor_roles: list[str],
    action: str,
    record_id: str | None = None,
    diff: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            actor_roles=actor_roles,
            action=action,
            record_id=record_id,
            diff=diff,
            reason=reason,
            request_id=request_id,
        )
    )


def snapshot_entry(session: Session, entry: CatalogEntry, actor: str) -> int:
    """Store the current state of ``entry`` as the next version; returns it."""
    current = session.scalar(
        select(func.coalesce(func.max(CatalogEntryVersion.version), 0)).where(
            CatalogEntryVersion.record_id == entry.id
        )
    )
    version = int(current or 0) + 1
    session.add(
        CatalogEntryVersion(
            record_id=entry.id,
            version=version,
            snapshot=entry_snapshot_dict(entry),
            created_by=actor,
        )
    )
    return version


def field_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Per-field {field: {before, after}} for changed keys only."""
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = {"before": before.get(key), "after": after.get(key)}
    return changed
