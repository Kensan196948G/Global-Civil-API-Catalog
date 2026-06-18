from pathlib import Path

from scripts.catalog_utils import (
    ROOT,
    load_catalog,
    load_catalog_metadata,
    load_verification_results,
    validate_catalog,
    validate_verification_results,
)


def test_catalog_has_required_initial_scope() -> None:
    catalog = load_catalog()
    results = load_verification_results()

    assert len(catalog) >= 50
    assert len(results) >= 10
    assert validate_catalog(catalog) == []
    assert validate_verification_results(results, catalog) == []


def test_release_acceptance_markers_exist() -> None:
    catalog = load_catalog()

    implementation_targets = [
        item for item in catalog if item["connection_status"] in {"実装接続済", "本格利用候補"}
    ]
    production_candidates = [
        item for item in catalog if item["connection_status"] == "本格利用候補"
    ]

    assert len(implementation_targets) >= 5
    assert len(production_candidates) >= 3
    assert all(item.get("adoption_reason") for item in production_candidates)


def test_catalog_is_marked_as_production_import() -> None:
    catalog = load_catalog()
    metadata = load_catalog_metadata()

    assert metadata["catalog_mode"] == "production"
    assert metadata["source"] == "claude-design-bundle"
    assert metadata["record_count"] == len(catalog)
    assert all(item["catalog_mode"] == "production" for item in catalog)
    assert all(item["production_source"] == "claude-design-bundle" for item in catalog)
    assert all(item["usage_summary"] for item in catalog)
    assert all(item["usage_notes"] for item in catalog)


def test_sample_paths_exist_for_verification_results() -> None:
    for result in load_verification_results():
        request_path = ROOT / result["sample_request_path"]
        response_path = ROOT / result["sample_response_path"]
        assert request_path.exists(), request_path
        assert response_path.exists(), response_path
        assert response_path.stat().st_size < 1024 * 1024


def test_no_secret_like_values_are_committed() -> None:
    suspicious_tokens = ["api_key=", "apikey=", "secret=", "token=", "password="]
    searchable_files = list((ROOT / "data").glob("*.json")) + [
        path for path in Path(ROOT / "samples").rglob("*") if path.is_file()
    ]
    for path in searchable_files:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        assert not any(token in text for token in suspicious_tokens), path
