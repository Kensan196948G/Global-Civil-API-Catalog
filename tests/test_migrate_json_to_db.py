"""Unit tests for the JSON -> PostgreSQL row mapping (no DB required)."""

from datetime import date, datetime, timezone

from scripts.migrate_json_to_db import entry_row, result_row


def test_entry_row_converts_date_and_preserves_lists() -> None:
    record = {
        "id": "TEST-001",
        "name": "テスト",
        "last_checked_at": "2026-08-01",
        "data_formats": ["JSON", "GeoJSON"],
        "tags": ["test"],
        "score_breakdown": {"business_fit": {"score": 80}},
    }
    row = entry_row(record)

    assert row["id"] == "TEST-001"
    assert row["last_checked_at"] == date(2026, 8, 1)
    assert row["data_formats"] == ["JSON", "GeoJSON"]
    assert row["tags"] == ["test"]


def test_entry_row_defaults_none_lists_to_empty() -> None:
    record = {"id": "TEST-002", "data_formats": None, "tags": None}
    row = entry_row(record)

    assert row["data_formats"] == []
    assert row["tags"] == []


def test_result_row_converts_datetime_and_defaults_sample_truncated() -> None:
    record = {
        "id": "V-1",
        "api_id": "TEST-001",
        "verified_at": "2026-08-01T12:00:00+00:00",
        "sample_truncated": None,
    }
    row = result_row(record)

    assert row["verified_at"] == datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    assert row["sample_truncated"] is False
