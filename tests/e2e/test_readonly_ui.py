"""Read-only browser E2E over the fictional demo dataset."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_dashboard_shows_demo_counts(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.wait_for_selector("#catalogCount:not(:has-text('-'))")
    assert page.locator("#catalogCount").inner_text() == "8"
    assert page.locator("#candidateCount").inner_text() == "1"
    assert page.locator("#implementedCount").inner_text() == "2"
    assert page.locator("#categoryList .barTrack").count() > 0


@pytest.mark.e2e
def test_catalog_search_filter_and_compare(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.wait_for_selector("#catalogCount:not(:has-text('-'))")
    page.click('[data-view="catalog"]')
    page.wait_for_selector("#catalogRows tr")
    assert page.locator("#catalogRows tr").count() == 8

    page.fill("#searchInput", "河川")
    page.wait_for_function(
        "document.querySelectorAll('#catalogRows tr').length === 1"
    )
    assert "DEMO-RIVER-LEVEL-001" in page.locator("#catalogRows").inner_text()

    page.fill("#searchInput", "flood, デモ")
    page.wait_for_function(
        "document.querySelectorAll('#catalogRows tr').length === 1"
    )

    page.fill("#searchInput", "")
    page.wait_for_function(
        "document.querySelectorAll('#catalogRows tr').length === 8"
    )
    compare_boxes = page.locator("input.compareCheck")
    compare_boxes.nth(0).check()
    compare_boxes.nth(1).check()
    assert page.locator("#compareButton").is_enabled()
    page.click("#compareButton")
    page.wait_for_selector("#compareDialog[open] table.compareTable")
    assert page.locator("#compareDialog .compareTable thead th").count() == 3
    page.click("#compareClose")


@pytest.mark.e2e
def test_exports_and_print_report_link(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.click('[data-view="exports"]')
    page.wait_for_selector("#exportList .exportCard, #exportList a")
    assert page.locator("#printReportButton").get_attribute("href") == (
        "/exports/API台帳_帳票.html"
    )
    assert "API台帳_帳票.html" in page.locator("#exportList").inner_text()


@pytest.mark.e2e
def test_live_map_and_theme(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.wait_for_selector("#catalogCount:not(:has-text('-'))")
    page.click('[data-view="map"]')
    page.wait_for_selector("#map .leaflet-container")
    assert page.locator("#baseMapList .baseMapItem, #baseMapList label").count() > 0

    page.click("#themeToggle")
    assert page.get_attribute("html", "data-theme") == "dark"


@pytest.mark.e2e
def test_accessibility_quick_wins(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    assert page.locator("a.skipLink").get_attribute("href") == "#mainContent"
    assert page.locator("main#mainContent").count() == 1
