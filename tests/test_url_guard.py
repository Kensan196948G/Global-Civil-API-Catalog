"""SSRF guard tests (external evaluation 2026-07-23, P0 finding)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_verification import build_result
from scripts.url_guard import validate_public_url

_ITEM = {
    "id": "TEST-SSRF-001",
    "api_key_required": "not_required",
    "sample_endpoint": "http://127.0.0.1:8080/internal",
}


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "javascript:alert(1)",
        "http://127.0.0.1/",
        "http://127.1.2.3:8080/x",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.0.185:49231/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://0.0.0.0/",
        "http://user:pass@example.com/",
        "http:///missing-host",
    ],
)
def test_blocked_urls(url: str) -> None:
    assert validate_public_url(url, resolve=False) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openaq.org/",
        "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson",
        "http://example.com:8443/data.json",
        "https://8.8.8.8/",  # public IP literal is fine
    ],
)
def test_allowed_urls_without_resolution(url: str) -> None:
    assert validate_public_url(url, resolve=False) is None


def test_hostname_resolving_to_private_ip_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.url_guard.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.9.8.7", 0))],
    )
    reason = validate_public_url("https://internal.example.com/", resolve=True)
    assert reason is not None and "10.9.8.7" in reason


def test_hostname_resolving_publicly_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.url_guard.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert validate_public_url("https://example.com/", resolve=True) is None


def test_build_result_blocks_private_endpoint_before_any_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    def _must_not_be_called(url, timeout):  # pragma: no cover - guard assertion
        raise AssertionError("request_url must not run for blocked endpoints")

    monkeypatch.setattr("scripts.run_verification.request_url", _must_not_be_called)

    result = build_result(_ITEM, live=True, timeout=5)

    assert result["result"] == "failure"
    assert "blocked by URL policy" in result["error_message"]
    assert "SSRF guard" in result["note"]
