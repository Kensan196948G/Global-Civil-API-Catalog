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
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

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
