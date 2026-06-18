from web.server import DESIGN_HTML_PATH, latest_verification


def test_latest_verification_prefers_newer_record() -> None:
    results = [
        {"api_id": "A", "verified_at": "2026-01-01T00:00:00+09:00", "result": "failure"},
        {"api_id": "A", "verified_at": "2026-06-18T00:00:00+09:00", "result": "success"},
    ]

    assert latest_verification(results)["A"]["result"] == "success"


def test_claude_design_html_is_available() -> None:
    assert DESIGN_HTML_PATH.exists()
    text = DESIGN_HTML_PATH.read_text(encoding="utf-8")
    assert "Global Civil API Catalog" in text
    assert "__bundler/manifest" in text
