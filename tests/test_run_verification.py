import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.catalog_utils import append_verification_history, load_verification_history
from scripts.run_verification import MAX_SAMPLE_BYTES, build_result, extract_record_count

_ITEM = {
    "id": "TEST-RECORD-COUNT-001",
    "api_key_required": "not_required",
    "sample_endpoint": "https://example.test/records.json",
}


@pytest.fixture(autouse=True)
def bypass_ssrf_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests mock request_url and use a non-resolvable .test domain;
    the SSRF guard itself is covered in tests/test_url_guard.py."""
    monkeypatch.setattr("scripts.run_verification.validate_public_url", lambda *a, **k: None)


def test_extract_record_count_json_array() -> None:
    assert extract_record_count(b"[1, 2, 3]") == 3


def test_extract_record_count_geojson_feature_collection() -> None:
    body = b'{"type":"FeatureCollection","features":[{"id":1},{"id":2}]}'
    assert extract_record_count(body) == 2


@pytest.mark.parametrize("key", ["results", "items", "records", "data"])
def test_extract_record_count_wrapped_list_keys(key: str) -> None:
    body = f'{{"{key}":[1, 2, 3, 4]}}'.encode()
    assert extract_record_count(body) == 4


def test_extract_record_count_object_without_list_returns_none() -> None:
    assert extract_record_count(b'{"foo": "bar"}') is None


def test_extract_record_count_non_json_returns_none() -> None:
    assert extract_record_count(b"\x89PNG\r\n\x1a\ncontent") is None


def test_extract_record_count_invalid_utf8_returns_none() -> None:
    assert extract_record_count(b"\xff\xfe\x00\x01") is None


def test_build_result_live_success_sets_record_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (200, b'{"results": [1, 2, 3]}', 42),
    )

    result = build_result(_ITEM, live=True, timeout=10)

    assert result["result"] == "success"
    assert result["record_count"] == 3


def test_build_result_live_failure_leaves_record_count_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (500, b'{"results": [1, 2, 3]}', 42),
    )

    result = build_result(_ITEM, live=True, timeout=10)

    assert result["result"] == "failure"
    assert result["record_count"] is None


def test_build_result_live_401_on_unknown_key_is_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    item = {**_ITEM, "id": "TEST-UNKNOWN-AUTH-001", "api_key_required": "unknown"}
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (401, b"unauthorized", 15),
    )

    result = build_result(item, live=True, timeout=10)

    assert result["result"] == "warning"
    assert result["http_status"] == 401
    assert "authentication required" in result["note"]
    assert "needs confirmation" in result["note"]


def test_build_result_live_401_on_not_required_key_is_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (401, b"unauthorized", 15),
    )

    result = build_result(_ITEM, live=True, timeout=10)

    assert result["result"] == "failure"
    assert result["http_status"] == 401


def test_build_result_truncated_payload_notes_missing_record_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    # A JSON array larger than the sample cap: request_url returns cap + 1
    # bytes, so the captured sample is a truncated (unparseable) document.
    oversized = (b'{"results": [' + b"1," * MAX_SAMPLE_BYTES)[: MAX_SAMPLE_BYTES + 1]
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (200, oversized, 42),
    )

    result = build_result(_ITEM, live=True, timeout=10)

    assert result["result"] == "success"
    assert result["sample_truncated"] is True
    assert result["response_size_bytes"] == MAX_SAMPLE_BYTES
    assert result["record_count"] is None
    assert "record_count unavailable" in result["note"]
    assert len(Path(result["sample_response_path"]).read_bytes()) == MAX_SAMPLE_BYTES


def test_build_result_exact_cap_payload_is_not_flagged_truncated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    # Trailing whitespace is valid JSON, so a payload of exactly
    # MAX_SAMPLE_BYTES stays parseable and must not be flagged as truncated.
    payload = b'{"results": [1, 2, 3]}'
    payload += b" " * (MAX_SAMPLE_BYTES - len(payload))
    monkeypatch.setattr(
        "scripts.run_verification.request_url",
        lambda url, timeout: (200, payload, 42),
    )

    result = build_result(_ITEM, live=True, timeout=10)

    assert result["result"] == "success"
    assert "sample_truncated" not in result
    assert result["record_count"] == 3
    assert "truncated" not in result["note"]


# --- verification history (issue #49) -----------------------------------


def test_load_verification_history_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_verification_history(tmp_path / "does-not-exist.jsonl") == []


def test_append_verification_history_writes_one_line_per_record(tmp_path: Path) -> None:
    history_path = tmp_path / "verification_history.jsonl"
    records = [
        {"api_id": "A-001", "verified_at": "2026-09-01T00:00:00+00:00", "result": "success"},
        {"api_id": "A-002", "verified_at": "2026-09-01T00:00:01+00:00", "result": "failure"},
    ]

    result = append_verification_history(records, path=history_path)

    assert result == records
    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert load_verification_history(history_path) == records


def test_append_verification_history_accumulates_across_calls(tmp_path: Path) -> None:
    history_path = tmp_path / "verification_history.jsonl"
    first = [{"api_id": "A-001", "verified_at": "2026-09-01T00:00:00+00:00", "result": "success"}]
    second = [{"api_id": "A-001", "verified_at": "2026-09-08T00:00:00+00:00", "result": "failure"}]

    append_verification_history(first, path=history_path)
    result = append_verification_history(second, path=history_path)

    assert result == first + second
    assert load_verification_history(history_path) == first + second


def test_append_verification_history_prunes_entries_past_retention_window(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "verification_history.jsonl"
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    old = {
        "api_id": "A-001",
        "verified_at": (now - timedelta(days=100)).isoformat(),
        "result": "success",
    }
    recent = {
        "api_id": "A-001",
        "verified_at": (now - timedelta(days=1)).isoformat(),
        "result": "success",
    }
    history_path.write_text(
        "\n".join(json.dumps(r) for r in (old, recent)) + "\n", encoding="utf-8"
    )

    new_record = {
        "api_id": "A-001",
        "verified_at": now.isoformat(),
        "result": "success",
    }
    result = append_verification_history(
        [new_record], path=history_path, retention_days=90, now=now
    )

    api_ids_and_dates = [(r["api_id"], r["verified_at"]) for r in result]
    assert (old["api_id"], old["verified_at"]) not in api_ids_and_dates
    assert (recent["api_id"], recent["verified_at"]) in api_ids_and_dates
    assert (new_record["api_id"], new_record["verified_at"]) in api_ids_and_dates


def test_append_verification_history_keeps_malformed_verified_at_instead_of_crashing(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "verification_history.jsonl"
    malformed = {"api_id": "A-001", "verified_at": "not-a-date", "result": "success"}
    history_path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")

    result = append_verification_history([], path=history_path)

    assert malformed in result
