"""Accessibility (a11y) checks over the fictional demo dataset.

Uses a locally vendored copy of axe-core (``web/static/vendor/axe-core``,
vendored the same way Leaflet is under ``web/static/vendor/leaflet``) instead
of fetching it from a CDN at test time, so these checks stay hermetic and do
not depend on outbound network access from the CI runner.

The WebUI serves a strict CSP (``script-src 'self'``; see
``web/server.py``'s ``_CSP``), which rejects the inline ``<script>`` that
``Page.add_script_tag(path=...)`` would normally inject. axe-core is
therefore loaded via ``add_script_tag(url=...)``, a same-origin request the
static file server answers directly from
``web/static/vendor/axe-core/axe.min.js`` (no CDN involved, no CSP
relaxation needed).

Only the unauthenticated, backend-independent surface is checked here
(same ``static_server_url`` fixture as ``test_readonly_ui.py``, no api_v1 or
Postgres required): the dashboard (top page), the catalog list view, and the
login dialog. ``critical``/``serious`` axe violations fail the test;
``moderate``/``minor`` findings are ignored to keep this check focused on
concrete a11y regressions rather than style nits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

AXE_VENDOR_PATH = (
    Path(__file__).resolve().parents[2] / "web" / "static" / "vendor" / "axe-core" / "axe.min.js"
)
AXE_URL_PATH = "/vendor/axe-core/axe.min.js"

_BLOCKING_IMPACTS = {"serious", "critical"}


def _run_axe(page: Any) -> dict:
    """Inject the vendored axe-core build (same-origin) and run a full audit."""
    assert AXE_VENDOR_PATH.exists(), f"axe-core not vendored at {AXE_VENDOR_PATH}"
    page.add_script_tag(url=AXE_URL_PATH)
    page.wait_for_function("() => typeof window.axe !== 'undefined'")
    return page.evaluate("async () => await window.axe.run()")


def _assert_no_blocking_violations(results: dict, context: str) -> None:
    violations = [
        violation
        for violation in results.get("violations", [])
        if violation.get("impact") in _BLOCKING_IMPACTS
    ]
    if not violations:
        return
    details = "\n".join(
        f"- [{violation.get('impact')}] {violation.get('id')}: {violation.get('help')} "
        f"({violation.get('helpUrl')}) — {len(violation.get('nodes', []))} node(s)"
        for violation in violations
    )
    raise AssertionError(
        f"axe-core found {len(violations)} critical/serious violation(s) on {context}:\n{details}"
    )


@pytest.mark.e2e
def test_dashboard_top_page_has_no_serious_a11y_violations(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.wait_for_selector("#catalogCount:not(:has-text('-'))")
    results = _run_axe(page)
    _assert_no_blocking_violations(results, "dashboard (top page, unauthenticated)")


@pytest.mark.e2e
def test_catalog_list_view_has_no_serious_a11y_violations(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    page.wait_for_selector("#catalogCount:not(:has-text('-'))")
    page.click('[data-view="catalog"]')
    page.wait_for_selector("#catalogRows tr")
    results = _run_axe(page)
    _assert_no_blocking_violations(results, "catalog list view")


@pytest.mark.e2e
def test_login_dialog_has_no_serious_a11y_violations(app_page, static_server_url) -> None:
    page = app_page
    page.goto(static_server_url)
    # No api_v1 backend is running for this fixture, so /auth/me always
    # fails and the UI treats the visitor as anonymous (see app.js
    # loadUser()/renderAuthArea()), exposing the login button.
    page.wait_for_selector("#loginButton:not([hidden])")
    page.click("#loginButton")
    page.wait_for_selector("#loginDialog[open]")
    results = _run_axe(page)
    _assert_no_blocking_violations(results, "login dialog")
