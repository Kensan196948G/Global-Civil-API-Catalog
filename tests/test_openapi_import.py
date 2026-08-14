"""Pure parser tests for OpenAPI -> draft candidates (issue #65)."""

from __future__ import annotations

from scripts.openapi_import import build_candidates

SAMPLE_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Demo River API",
        "version": "1.0.0",
        "description": "Fictional river water level API.",
        "license": {"name": "CC BY 4.0 (fictional)"},
    },
    "servers": [{"url": "https://example.test/river"}],
    "components": {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-Key"}}
    },
    "security": [{"ApiKeyAuth": []}],
    "paths": {
        "/stations": {
            "get": {
                "summary": "List stations",
                "tags": ["river"],
                "description": "Returns fictional stations.",
            }
        },
        "/stations/{station_id}": {
            "get": {
                "summary": "Get one station",
                "tags": ["river", "detail"],
            }
        },
    },
}


def test_build_candidates_generates_draft_records() -> None:
    candidates, errors = build_candidates(SAMPLE_SPEC)
    assert errors == []
    assert len(candidates) == 2
    first = candidates[0]
    assert first["id"].startswith("OPENAPI-")
    assert first["name"].startswith("Demo River API")
    assert first["category"] == "河川"
    assert first["api_key_required"] == "required"
    assert first["auth_type"] == "api_key"
    assert first["endpoint_template"] == "https://example.test/river/stations"
    assert first["connection_status"] == "調査中"
    assert first["trust_rank"] == "C"
    assert first["data_formats"] == ["JSON"]
    # Path with braces keeps the template but no concrete sample endpoint.
    second = candidates[1]
    assert second["sample_endpoint"] is None
    assert "{station_id}" in second["endpoint_template"]


def test_build_candidates_is_capped() -> None:
    spec = dict(SAMPLE_SPEC)
    paths = {f"/p{i}": {"get": {"summary": f"op {i}"}} for i in range(30)}
    spec["paths"] = paths
    candidates, _ = build_candidates(spec, max_candidates=5)
    assert len(candidates) == 5


def test_build_candidates_guesses_category_from_summary() -> None:
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Fake Weather", "version": "1"},
        "paths": {"/forecast": {"get": {"summary": "Weather forecast"}}},
    }
    candidates, _ = build_candidates(spec)
    assert candidates[0]["category"] == "気象"
    assert candidates[0]["api_key_required"] == "not_required"
