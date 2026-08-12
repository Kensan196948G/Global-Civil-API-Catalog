from scripts.catalog_utils import (
    latest_verification_by_api,
    load_catalog,
    load_verification_results,
    priority_rank,
    priority_score,
    trust_rank,
    trust_score,
)
from scripts.score_catalog import (
    business_fit_breakdown,
    integration_breakdown,
    trust_breakdown,
)


def test_trust_score_and_rank_for_gsi_tile() -> None:
    catalog = {item["id"]: item for item in load_catalog()}
    verification_by_api = latest_verification_by_api(load_verification_results())

    score = trust_score(catalog["GSI-TILE-STD-001"], verification_by_api)

    assert score >= 90
    assert trust_rank(score) == "A"


def test_priority_rank_for_production_candidate() -> None:
    catalog = {item["id"]: item for item in load_catalog()}
    verification_by_api = latest_verification_by_api(load_verification_results())
    item = catalog["JMA-FORECAST-001"]

    score = priority_score(item, trust_score(item, verification_by_api))

    assert priority_rank(score) >= 4


def test_integration_breakdown_prefers_no_key_and_concrete_endpoint() -> None:
    item = {
        "api_key_required": "not_required",
        "auth_type": "none",
        "data_formats": ["JSON"],
        "sample_endpoint": "https://example.test/data.json",
        "document_url": "https://example.test/docs",
        "endpoint_template": "",
    }
    score, factors = integration_breakdown(item, verified=True)

    assert score >= 80
    assert any("APIキー(not_required)" in factor for factor in factors)
    assert any("実接続検証" in factor for factor in factors)


def test_business_fit_breakdown_rewards_official_provider() -> None:
    item = {
        "provider_type": "government",
        "commercial_use": "allowed",
        "update_frequency": "随時",
        "target_projects": ["PJ-A", "PJ-B", "PJ-C"],
        "connection_status": "本格利用候補",
    }
    score, factors = business_fit_breakdown(item)

    assert score == 100
    assert any("提供元種別(government)" in factor for factor in factors)


def test_trust_breakdown_ranks_a_for_full_evidence() -> None:
    item = {
        "provider_type": "government",
        "document_url": "https://example.test/docs",
        "license_note": "出典表記が必要",
        "commercial_use": "allowed",
        "update_frequency": "随時",
        "data_formats": ["JSON"],
    }
    score, rank, factors = trust_breakdown(item, verified=True)

    assert score == 100
    assert rank == "A"
