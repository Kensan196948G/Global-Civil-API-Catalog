"""One-shot, idempotent JSON -> PostgreSQL loader (Phase A of epic #46).

Loads data/api_catalog.json and data/verification_results.json into the
catalog_entries / verification_results tables (upsert by primary key), then
verifies a field-by-field round trip. The JSON files remain the system of
record during the dual-run period; this script may be re-run at any time.

Usage:
    CATALOG_DATABASE_URL=... python scripts/migrate_json_to_db.py [--verify-only]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from db.models import CatalogEntry, VerificationResult  # noqa: E402
from db.session import make_engine, make_session_factory  # noqa: E402
from scripts.catalog_utils import (  # noqa: E402
    VERIFICATION_PATH,
    load_catalog,
    load_json,
)

ENTRY_FIELDS = [
    c.name for c in CatalogEntry.__table__.columns if c.name not in ("created_at", "updated_at")
]
RESULT_FIELDS = [c.name for c in VerificationResult.__table__.columns]


def entry_row(record: dict) -> dict:
    row = {}
    for field in ENTRY_FIELDS:
        value = record.get(field)
        if field == "last_checked_at" and isinstance(value, str):
            value = date.fromisoformat(value)
        if field in ("data_formats", "tags") and value is None:
            value = []
        row[field] = value
    return row


def result_row(record: dict) -> dict:
    row = {}
    for field in RESULT_FIELDS:
        value = record.get(field)
        if field == "verified_at" and isinstance(value, str):
            value = datetime.fromisoformat(value)
        if field == "sample_truncated" and value is None:
            value = False
        row[field] = value
    return row


def upsert(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[model.__table__.primary_key.columns.keys()[0]],
        set_={k: stmt.excluded[k] for k in rows[0] if k != "id"},
    )
    session.execute(stmt)


def verify_round_trip(session, entries: list[dict], results: list[dict]) -> list[str]:
    """Compare every loaded JSON field against the stored row."""
    problems: list[str] = []
    db_entries = {e.id: e for e in session.scalars(select(CatalogEntry))}
    for record in entries:
        stored = db_entries.get(record["id"])
        if stored is None:
            problems.append(f"missing entry {record['id']}")
            continue
        for field in ENTRY_FIELDS:
            expected = entry_row(record)[field]
            actual = getattr(stored, field)
            if field == "last_checked_at" and actual is not None:
                actual = actual  # already a date
            if expected != actual:
                problems.append(f"{record['id']}.{field}: json={expected!r} db={actual!r}")
    db_count = session.scalar(select(func.count()).select_from(VerificationResult))
    if db_count != len({r["id"] for r in results}):
        problems.append(f"verification_results count mismatch: json={len(results)} db={db_count}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="skip loading; only run the round-trip comparison",
    )
    args = parser.parse_args()

    entries = load_catalog()
    results = load_json(VERIFICATION_PATH)

    engine = make_engine()
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        if not args.verify_only:
            upsert(session, CatalogEntry, [entry_row(r) for r in entries])
            upsert(session, VerificationResult, [result_row(r) for r in results])
            session.commit()
            print(f"loaded {len(entries)} entries, {len(results)} verification results")
        problems = verify_round_trip(session, entries, results)

    if problems:
        print(f"FAIL: {len(problems)} mismatches")
        for p in problems[:20]:
            print(" -", p)
        return 1
    print(f"round-trip OK: {len(entries)} entries match field-by-field")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
