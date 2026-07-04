from pathlib import Path

from web.server import (
    DESIGN_HTML_PATH,
    ROOT,
    category_counts,
    filter_catalog,
    latest_verification,
    live_map_payload,
    status_counts,
)


def test_latest_verification_prefers_newer_record() -> None:
    results = [
        {
            "api_id": "A",
            "verified_at": "2026-01-01T00:00:00+09:00",
            "result": "failure",
        },
        {
            "api_id": "A",
            "verified_at": "2026-06-18T00:00:00+09:00",
            "result": "success",
        },
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


def test_live_map_ui_has_base_map_and_opacity_controls() -> None:
    html = Path(ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
    js = Path(ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="baseMapList"' in html
    assert 'id="overlayOpacity"' in html
    # Overlays must not be stacked on the base map by default.
    assert "setBaseMap" in js
    assert "tileLayer.addTo(state.map)" not in js


def test_dashboard_has_fitness_map_and_osm_base_variants() -> None:
    html = Path(ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
    js = Path(ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="fitnessMap"' in html
    assert "renderFitnessMap" in js
    assert "採用ダッシュボード" in js
    # OSM live-connection base map variants from the design bundle.
    for catalog_id in ("OSM-TILE-001", "OSM-HOT", "OSM-CYCLOSM"):
        assert catalog_id in js


def test_ui_has_six_status_palette_and_design_enhancements() -> None:
    html = Path(ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
    css = Path(ROOT / "web" / "static" / "styles.css").read_text(encoding="utf-8")
    js = Path(ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    # Six-status connection palette classes.
    for klass in (
        "statusColor-impl",
        "statusColor-full",
        "statusColor-verified",
        "statusColor-candidate",
        "statusColor-survey",
        "statusColor-hold",
    ):
        assert f".{klass}" in css
        assert klass in js

    # Fitness scatter axis ticks and design-spec coordinate mapping.
    assert "fitnessTick" in js
    assert "fitnessTick" in css
    assert "fitnessMap01" in js

    # Current-layer overlay badge on the live map.
    assert "currentLayerBadge" in js
    assert ".currentLayerBadge" in css

    # Light/dark theme toggle.
    assert 'id="themeToggle"' in html
    assert 'data-theme="dark"' in css
    assert "localStorage" in js

    # Sidebar nav count badges.
    assert 'id="navBadgeCatalog"' in html
    assert ".navBadge" in css
    assert "setNavBadges" in js


def test_catalog_links_are_scheme_validated() -> None:
    js = Path(ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function safeUrl" in js
    # Every dynamic href must go through safeUrl, not bare escapeHtml.
    assert 'href="${escapeHtml(' not in js
    assert 'href="${item.' not in js


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
    results = [
        {"api_id": "A", "verified_at": "2026-06-18T00:00:00+09:00", "result": "success"}
    ]

    payload = live_map_payload(catalog, results)

    assert payload["features"][0]["id"] == "A"
    assert payload["features"][0]["latest_verification"] == "success"
    assert payload["layers"][0]["tile_url"] == "https://example.test/{z}/{x}/{y}.png"


_SAMPLE_CATALOG = [
    {
        "category": "地図",
        "connection_status": "本格利用候補",
        "name": "標準地図",
    },
    {
        "category": "地図",
        "connection_status": "接続検証済",
        "name": "淡色地図",
    },
    {
        "category": "防災",
        "connection_status": "本格利用候補",
        "name": "洪水ハザード",
    },
]


def test_filter_catalog_by_category() -> None:
    result = filter_catalog(_SAMPLE_CATALOG, category="防災")
    assert len(result) == 1
    assert result[0]["name"] == "洪水ハザード"


def test_filter_catalog_by_status() -> None:
    result = filter_catalog(_SAMPLE_CATALOG, status="接続検証済")
    assert len(result) == 1
    assert result[0]["name"] == "淡色地図"


def test_filter_catalog_by_keyword() -> None:
    result = filter_catalog(_SAMPLE_CATALOG, keyword="標準")
    assert len(result) == 1
    assert result[0]["name"] == "標準地図"


def test_filter_catalog_no_match_returns_empty() -> None:
    result = filter_catalog(_SAMPLE_CATALOG, keyword="存在しないキーワード")
    assert result == []


def test_filter_catalog_combined_filters() -> None:
    result = filter_catalog(_SAMPLE_CATALOG, category="地図", status="本格利用候補")
    assert len(result) == 1
    assert result[0]["name"] == "標準地図"


def test_status_counts_aggregates_correctly() -> None:
    catalog = [
        {"connection_status": "本格利用候補"},
        {"connection_status": "本格利用候補"},
        {"connection_status": "接続検証済"},
        {},
    ]
    counts = status_counts(catalog)
    assert counts["本格利用候補"] == 2
    assert counts["接続検証済"] == 1
    assert counts["未設定"] == 1


def test_category_counts_aggregates_correctly() -> None:
    catalog = [
        {"category": "地図"},
        {"category": "地図"},
        {"category": "防災"},
    ]
    counts = category_counts(catalog)
    assert counts["地図"] == 2
    assert counts["防災"] == 1
