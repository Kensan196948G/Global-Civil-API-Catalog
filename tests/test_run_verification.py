from pathlib import Path

import pytest

from scripts.run_verification import MAX_SAMPLE_BYTES, build_result, extract_record_count

_ITEM = {
    "id": "TEST-RECORD-COUNT-001",
    "api_key_required": "not_required",
    "sample_endpoint": "https://example.test/records.json",
}


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
