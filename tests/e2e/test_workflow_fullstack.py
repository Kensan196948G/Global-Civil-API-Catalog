"""Full-stack browser E2E: login → create → review → approve → audit CSV.

Requires a running demo stack (web + api + Postgres + webhook echo) and the
``E2E_FULLSTACK_URL`` environment variable (set by the e2e-fullstack CI job
or by ``scripts/run_demo_stack.sh`` + manual export).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.e2e
def test_login_create_transition_approve_and_audit(app_page) -> None:
    page = app_page
    base_url = os.environ.get("E2E_FULLSTACK_URL", "")
    if not base_url:
        pytest.skip("E2E_FULLSTACK_URL not set")

    page.goto(base_url)
    page.click("#loginButton")
    page.wait_for_selector("#loginDialog[open]")
    page.fill("#loginUsername", "demo-admin")
    page.fill("#loginPassword", "DemoPassw0rd!2026")
    page.click("#loginSubmit")
    page.wait_for_selector("#userBox:not([hidden])")
    assert "デモ管理者" in page.locator("#userName").inner_text()

    page.click("#navManage")
    page.wait_for_selector("#tasksPanel:not([hidden])")
    assert page.locator("#taskCount").inner_text() != "0件"

    # Create a demo entry (draft).
    entry_id = "DEMO-E2E-001"
    page.click("#newEntryButton")
    page.fill("#entryForm [name=id]", entry_id)
    page.fill("#entryForm [name=name]", "E2E デモエントリ（架空）")
    page.fill("#entryForm [name=category]", "テスト")
    page.fill("#entryForm [name=provider]", "E2Eデモ提供者（架空）")
    page.fill("#entryForm [name=provider_type]", "official")
    page.fill("#entryForm [name=official_url]", "https://example.test/e2e")
    page.fill("#entryForm [name=document_url]", "https://example.test/e2e/docs")
    page.select_option("#entryForm [name=api_key_required]", "not_required")
    page.select_option("#entryForm [name=connection_status]", "未調査")
    page.fill("#entryForm [name=reason]", "E2Eデモ用の登録（架空）")
    page.click("#entryFormSubmit")
    page.wait_for_selector("#manageNotice:not([hidden])")
    assert "登録しました" in page.locator("#manageNotice").inner_text()

    # Review flow: submit → review_ok → approve (Admin can drive all states).
    row = page.locator(f"#manageRows tr:has-text('{entry_id}')")
    row.locator('button[data-act="transition"][data-action="submit"]').click()
    page.fill("#reasonInput", "E2E: レビュー依頼（デモ）")
    page.click("#reasonConfirm")
    page.wait_for_selector("#manageNotice:not([hidden])")

    row = page.locator(f"#manageRows tr:has-text('{entry_id}')")
    row.locator('button[data-act="transition"][data-action="review_ok"]').click()
    page.fill("#reasonInput", "E2E: レビューOK（デモ）")
    page.click("#reasonConfirm")
    page.wait_for_selector("#manageNotice:not([hidden])")

    row = page.locator(f"#manageRows tr:has-text('{entry_id}')")
    row.locator('button[data-act="transition"][data-action="approve"]').click()
    page.fill("#reasonInput", "E2E: 承認・公開（デモ）")
    page.click("#reasonConfirm")
    page.wait_for_selector("#manageNotice:not([hidden])")
    assert "公開中" in page.locator("#manageNotice").inner_text()

    # Webhook echo should have recorded the workflow transition events.
    log_path = ROOT / "data" / "demo" / "webhook_deliveries.jsonl"
    if log_path.exists():
        events = [
            json.loads(line).get("event")
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if entry_id in line
        ]
        assert "entry.workflow_transition" in events

    # Audit CSV download.
    with page.expect_download() as download_info:
        page.click("#auditCsvLink")
    download = download_info.value
    assert download.suggested_filename == "catalog_audit_log.csv"
