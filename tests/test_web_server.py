from pathlib import Path

from web.server import DESIGN_HTML_PATH, ROOT, latest_verification, live_map_payload


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


def test_production_ui_sections_are_available() -> None:
    text = Path(ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="dashboard"' in text
    assert 'id="catalog"' in text
    assert 'id="live-map"' in text
    assert 'id="exports"' in text


def test_live_map_payload_uses_catalog_data() -> None:
    catalog = [
        {
            "id": "A",
            "name": "標準地図",
            "category": "地図",
            "provider": "Provider",
            "region": "JP",
            "endpoint_template": "https://example.test/{z}/{x}/{y}.png",
            "data_formats": ["XYZ Tile", "PNG"],
            "connection_status": "本格利用候補",
            "trust_rank": "A",
            "connection_priority": 5,
            "usage_summary": "summary",
            "sample_endpoint": "https://example.test/1/1/1.png",
            "official_url": "https://example.test",
            "license_note": "attribution",
        }
    ]
    results = [{"api_id": "A", "verified_at": "2026-06-18T00:00:00+09:00", "result": "success"}]

    payload = live_map_payload(catalog, results)

    assert payload["features"][0]["id"] == "A"
    assert payload["features"][0]["latest_verification"] == "success"
    assert payload["layers"][0]["tile_url"] == "https://example.test/{z}/{x}/{y}.png"
