from scripts.catalog_utils import (
    latest_verification_by_api,
    load_catalog,
    load_verification_results,
    priority_rank,
    priority_score,
    trust_rank,
    trust_score,
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
