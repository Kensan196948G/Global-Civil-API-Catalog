"""Unit tests for scripts/health_check.py (no network required)."""

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


def test_main_fails_when_web_down(monkeypatch) -> None:
    def _probe(base, path, timeout=10):
        return None, {"error": "ConnectionRefusedError"}

    monkeypatch.setattr(health_check, "probe", _probe)
    assert health_check.main(["http://127.0.0.1:49231"]) == 1
