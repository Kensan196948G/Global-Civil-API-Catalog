"""Unit tests for scripts/health_check.py (no network required)."""

import io
import urllib.error

import pytest

import scripts.health_check as health_check


def test_main_ok_when_both_health_checks_pass(monkeypatch) -> None:
    def _probe(base, path, timeout=10):
        if path == "/api/health":
            return 200, {"status": "ok"}
        return 200, {"status": "ok", "database": "ok"}

    monkeypatch.setattr(health_check, "probe", _probe)
    assert health_check.main(["http://127.0.0.1:49231"]) == 0


def test_main_fails_when_database_unavailable(monkeypatch) -> None:
    def _probe(base, path, timeout=10):
        if path == "/api/health":
            return 200, {"status": "ok"}
        return 200, {"status": "ok", "database": "unavailable"}

    monkeypatch.setattr(health_check, "probe", _probe)
    assert health_check.main(["http://127.0.0.1:49231"]) == 1


def test_main_fails_when_api_reports_503_degraded(monkeypatch) -> None:
    """DB 障害時は api_v1 が 503 を返す。その場合も必ず非 0 で終了すること。"""

    def _probe(base, path, timeout=10):
        if path == "/api/health":
            return 200, {"status": "ok"}
        return 503, {"status": "degraded", "database": "unavailable"}

    monkeypatch.setattr(health_check, "probe", _probe)
    assert health_check.main(["http://127.0.0.1:49231"]) == 1


def test_main_fails_when_web_down(monkeypatch) -> None:
    def _probe(base, path, timeout=10):
        return None, {"error": "ConnectionRefusedError"}

    monkeypatch.setattr(health_check, "probe", _probe)
    assert health_check.main(["http://127.0.0.1:49231"]) == 1


def test_probe_surfaces_json_body_of_http_error(monkeypatch) -> None:
    """回帰防止: 503 は「取得失敗」ではなく「判定結果」として本文ごと読む。

    以前は urllib の HTTPError を汎用 except が握りつぶし、ステータスも
    本文も失われていたため、DB 障害とプロセス停止を区別できなかった。
    """
    payload = b'{"status": "degraded", "database": "unavailable"}'

    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://x/api/v1/health",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(payload),
        )

    monkeypatch.setattr(health_check.urllib.request, "urlopen", _raise)
    status, body = health_check.probe("http://x", "/api/v1/health")
    assert status == 503
    assert body["database"] == "unavailable"


def test_probe_tolerates_non_json_error_body(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://x/api/v1/health",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=io.BytesIO(b"<html>bad gateway</html>"),
        )

    monkeypatch.setattr(health_check.urllib.request, "urlopen", _raise)
    status, body = health_check.probe("http://x", "/api/v1/health")
    assert status == 502
    assert "error" in body


@pytest.mark.parametrize("exc", [ConnectionRefusedError("refused"), TimeoutError("timeout")])
def test_probe_classifies_transport_failure(monkeypatch, exc) -> None:
    def _raise(*args, **kwargs):
        raise exc

    monkeypatch.setattr(health_check.urllib.request, "urlopen", _raise)
    status, body = health_check.probe("http://x", "/api/v1/health")
    assert status is None
    assert body["error"] == type(exc).__name__
