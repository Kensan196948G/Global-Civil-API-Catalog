"""Phase A DB layer tests (epic #46).

These tests require a real PostgreSQL database (Neon development branch)
via CATALOG_DATABASE_URL and the optional db dependencies. In CI neither
is present, so the whole module skips — local verification against the
Neon dev branch is the required evidence before merge (see PR body).
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

if not os.environ.get("CATALOG_DATABASE_URL"):
    pytest.skip("CATALOG_DATABASE_URL not set", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from scripts.catalog_utils import load_catalog  # noqa: E402
from web.api_v1 import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_metadata_counts_match_json(client) -> None:
    body = client.get("/api/v1/metadata").json()
    assert body["record_count"] == len(load_catalog())
    assert body["verification_count"] > 0
    assert body["source"] == "postgresql"


def test_health_endpoint_reports_db_ok(client) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_list_entries_returns_all_records(client) -> None:
    body = client.get("/api/v1/entries", params={"limit": 500}).json()
    assert body["total"] == len(load_catalog())
    ids = {item["id"] for item in body["items"]}
    assert "OPENAQ-API-001" in ids


def test_list_entries_filter_by_category(client) -> None:
    body = client.get("/api/v1/entries", params={"category": "国際環境"}).json()
    assert body["total"] >= 1
    assert all(item["category"] == "国際環境" for item in body["items"])


def test_list_entries_keyword_search(client) -> None:
    body = client.get("/api/v1/entries", params={"keyword": "OpenAQ"}).json()
    assert any(item["id"] == "OPENAQ-API-001" for item in body["items"])


def test_get_entry_round_trip_fields(client) -> None:
    json_record = next(r for r in load_catalog() if r["id"] == "OPENAQ-API-001")
    body = client.get("/api/v1/entries/OPENAQ-API-001").json()
    for field in ("name", "provider", "official_url", "api_key_required", "tags"):
        assert body[field] == json_record[field]


def test_get_entry_404(client) -> None:
    assert client.get("/api/v1/entries/NO-SUCH-ID").status_code == 404


def test_verifications_filter(client) -> None:
    body = client.get("/api/v1/verifications", params={"api_id": "USGS-EARTHQUAKE-001"}).json()
    assert body["items"]
    assert all(item["api_id"] == "USGS-EARTHQUAKE-001" for item in body["items"])
