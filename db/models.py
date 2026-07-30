"""SQLAlchemy 2.x models mirroring docs/epic-detailed-design-q4.md §2.1.

The PostGIS ``geom`` column is created by the Alembic migration but is
deliberately not mapped here yet: no current record carries coordinates,
and mapping it would pull in a GeoAlchemy2 dependency before it is needed
(design AD-1 keeps PostGIS enabled at the schema level from day one).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CatalogEntry(Base):
    __tablename__ = "catalog_entries"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    sub_category: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    # NFR: the provider documentation URL is a required catalog field.
    document_url: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint_template: Mapped[str | None] = mapped_column(Text)
    sample_endpoint: Mapped[str | None] = mapped_column(Text)
    data_formats: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    api_key_required: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str | None] = mapped_column(Text)
    license_note: Mapped[str | None] = mapped_column(Text)
    commercial_use: Mapped[str | None] = mapped_column(Text)
    update_frequency: Mapped[str | None] = mapped_column(Text)
    connection_status: Mapped[str] = mapped_column(Text, nullable=False)
    trust_rank: Mapped[str | None] = mapped_column(Text)
    connection_priority: Mapped[int | None] = mapped_column(Integer)
    business_fit_score: Mapped[int | None] = mapped_column(Integer)
    integration_score: Mapped[int | None] = mapped_column(Integer)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    usage_summary: Mapped[str | None] = mapped_column(Text)
    usage_notes: Mapped[str | None] = mapped_column(Text)
    risk_note: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )
    # FR-012: deletion is logical — the row (and its history, epic #47) is kept.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "api_key_required IN ('required','not_required','unknown')",
            name="ck_catalog_entries_api_key_required",
        ),
        CheckConstraint(
            "trust_rank IN ('A','B','C','D','E')",
            name="ck_catalog_entries_trust_rank",
        ),
    )


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    api_id: Mapped[str] = mapped_column(Text, ForeignKey("catalog_entries.id"), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_by: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer)
    record_count: Mapped[int | None] = mapped_column(Integer)
    sample_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "result IN ('success','failure','warning','skipped')",
            name="ck_verification_results_result",
        ),
        Index("ix_verification_results_api_id_verified_at", "api_id", "verified_at"),
    )


class AuditLog(Base):
    """Append-only audit trail (design §4.1, epic #47).

    Application code only ever INSERTs into this table; the DB-role based
    enforcement (AD-6: revoke UPDATE/DELETE from the app role) is applied at
    the production cutover together with the dedicated ``catalog_app`` role
    (tracked in issue #47 — the migration itself stays role-agnostic so it
    can run on any branch).
    """

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    actor_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[str | None] = mapped_column(Text)
    diff: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_audit_log_record_id_at", "record_id", "at"),)


class CatalogEntryVersion(Base):
    """Immutable snapshot of a catalog entry taken before every change."""

    __tablename__ = "catalog_entry_versions"

    record_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)


WORKFLOW_STATES = ("draft", "in_review", "pending_approval", "published", "rejected")


class EntryWorkflow(Base):
    """Editorial state per catalog entry (design §4.2)."""

    __tablename__ = "entry_workflow"

    record_id: Mapped[str] = mapped_column(Text, ForeignKey("catalog_entries.id"), primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('draft','in_review','pending_approval','published','rejected')",
            name="ck_entry_workflow_state",
        ),
    )


class AuthRequest(Base):
    """Pending OIDC authorization request (state/nonce/PKCE verifier).

    Rows are single-use: the callback consumes and deletes them. Stale rows
    (abandoned logins) are purged opportunistically on each new login.
    """

    __tablename__ = "auth_requests"

    state: Mapped[str] = mapped_column(Text, primary_key=True)
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    code_verifier: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class UserSession(Base):
    """Server-side login session (design §3.1): the browser only holds an
    opaque random ID; tokens never reach the client."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_sub: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LocalUser(Base):
    """Local username/password account (auth mode ``local``).

    Passwords are stored as scrypt hashes (stdlib, per-user salt); the
    plaintext never touches the database or logs. ``role`` holds exactly one
    of the five catalog roles — a login session copies it into
    ``sessions.roles`` so ``require_role`` works unchanged for both auth
    modes. Failed-attempt counting backs the temporary lockout policy.
    """

    __tablename__ = "local_users"

    username: Mapped[str] = mapped_column(Text, primary_key=True)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('Catalog.Admin', 'Catalog.Editor', 'Catalog.Verifier',"
            " 'Catalog.Approver', 'Catalog.Viewer')",
            name="ck_local_users_role",
        ),
    )
