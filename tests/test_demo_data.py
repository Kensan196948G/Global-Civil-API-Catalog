"""MVP demo dataset checks: fictional, valid, and boundary-covering."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.catalog_utils import validate_catalog, validate_verification_results

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data" / "demo"


def _load(name: str):
    with (DEMO_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_demo_catalog_and_verification_are_valid() -> None:
    catalog = _load("api_catalog.json")
    results = _load("verification_results.json")
    errors = validate_catalog(catalog) + validate_verification_results(results, catalog)
    assert errors == []


def test_demo_workflow_states_reference_existing_entries() -> None:
    catalog = _load("api_catalog.json")
    states = _load("workflow_states.json")
    assert set(states) == {item["id"] for item in catalog}
    assert set(states.values()) <= {
        "draft",
        "in_review",
        "pending_approval",
        "published",
        "rejected",
    }


def test_demo_covers_boundary_statuses_and_results() -> None:
    catalog = _load("api_catalog.json")
    results = _load("verification_results.json")
    statuses = {item["connection_status"] for item in catalog}
    result_kinds = {row["result"] for row in results}
    # Normal + boundary + anomaly cases must be present so the MVP can be
    # demonstrated without empty screens.
    assert {
        "本格利用候補",
        "接続検証済",
        "実装接続済",
        "接続候補",
        "調査中",
        "保留",
        "利用終了",
    } <= statuses
    assert {"success", "warning", "failure", "skipped"} <= result_kinds


def test_demo_entries_are_clearly_fictional() -> None:
    catalog = _load("api_catalog.json")
    assert len(catalog) >= 8
    for item in catalog:
        assert item["catalog_mode"] == "demo"
        assert item["id"].startswith("DEMO-")
        combined = " ".join(
            [
                item["name"],
                item["provider"],
                item.get("usage_summary", ""),
                item.get("usage_notes", ""),
            ]
        )
        assert "デモ" in combined or "demo" in combined.lower() or "fictional" in combined.lower()
        # No real personal/company data: example.test is the reserved domain.
        assert item["official_url"].startswith("https://example.test/")
        assert item["document_url"].startswith("https://example.test/")


def test_demo_sample_files_exist() -> None:
    results = _load("verification_results.json")
    for row in results:
        assert (ROOT / row["sample_request_path"]).exists()
        assert (ROOT / row["sample_response_path"]).exists()


def test_demo_stack_scripts_exist() -> None:
    assert (ROOT / "scripts" / "run_demo_stack.sh").exists()
    assert (ROOT / "scripts" / "demo_webhook_echo.py").exists()
    assert (ROOT / "scripts" / "seed_demo_data.py").exists()
