"""Recompute all catalog scores from documented, data-driven rubrics.

Replaces the hand-authored business_fit_score / integration_score and derives
trust_rank / connection_priority from the existing catalog_utils formulas, so
every score on the dashboard is reproducible from the catalog fields. A compact
``score_breakdown`` is stored per record so the basis can be shown on screen.

Run: python scripts/score_catalog.py [--write]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    CATALOG_PATH,
    EXPORT_DIR,
    latest_verification_by_api,
    load_catalog,
    load_verification_results,
    priority_rank,
    priority_score,
    trust_rank,
    write_json,
)

EASY_FORMATS = {"JSON", "GeoJSON", "XYZ Tile", "Vector Tile", "REST", "JSON API", "WMS", "WMTS"}
FREQUENT_UPDATES = {
    "随時",
    "リアルタイム",
    "時間",
    "日次等",
    "短周期",
    "短周期/日次",
    "観測周期",
    "定時",
    "年次/随時",
}
STATUS_MATURITY = {
    "本格利用候補": 10,
    "実装接続済": 9,
    "接続検証済": 7,
    "接続候補": 4,
    "調査中": 2,
    "保留": 0,
    "除外": 0,
}


def _clamp(value: int) -> int:
    return max(0, min(100, int(round(value))))


def integration_breakdown(item: dict, verified: bool) -> tuple[int, list[str]]:
    factors: list[str] = []
    score = 0

    key = item.get("api_key_required") or ""
    pts = {"not_required": 30, "unknown": 12, "required": 8}.get(key, 8)
    score += pts
    factors.append(f"APIキー({key}) +{pts}")

    auth = item.get("auth_type") or ""
    pts = {"none": 15, "api_key": 8, "oauth2": 6, "other": 4, "unknown": 6}.get(auth, 4)
    score += pts
    factors.append(f"認証方式({auth}) +{pts}")

    formats = item.get("data_formats") or []
    if any(fmt in EASY_FORMATS for fmt in formats):
        score += 20
        factors.append("扱いやすい形式(JSON/タイル等) +20")
    else:
        score += 10
        factors.append("要変換の形式 +10")

    endpoint = item.get("sample_endpoint")
    template = item.get("endpoint_template") or ""
    if endpoint and "{" not in endpoint:
        score += 15
        factors.append("具体的サンプルエンドポイント +15")
    elif template and "{" not in template:
        score += 12
        factors.append("具体的エンドポイント +12")
    elif template:
        score += 8
        factors.append("エンドポイント雛形 +8")

    if item.get("document_url"):
        score += 10
        factors.append("公式ドキュメントあり +10")

    if verified:
        score += 10
        factors.append("実接続検証 成功 +10")

    return _clamp(score), factors


def business_fit_breakdown(item: dict) -> tuple[int, list[str]]:
    factors: list[str] = []
    score = 0

    provider = item.get("provider_type")
    if provider in {"government", "official", "international"}:
        pts = 30
    elif provider == "foundation":
        pts = 22
    elif provider == "company":
        pts = 12
    else:
        pts = 8
    score += pts
    factors.append(f"提供元種別({provider}) +{pts}")

    commercial = item.get("commercial_use") or ""
    pts = {"allowed": 25, "restricted": 12, "unknown": 8}.get(commercial, 8)
    score += pts
    factors.append(f"商用利用({commercial}) +{pts}")

    freq = item.get("update_frequency") or ""
    if freq in FREQUENT_UPDATES:
        score += 15
        factors.append(f"更新頻度({freq}) +15")
    elif freq:
        score += 10
        factors.append(f"更新頻度({freq}) +10")

    projects = item.get("target_projects") or []
    pts = min(len(projects) * 7, 20)
    if pts:
        score += pts
        factors.append(f"対象案件 {len(projects)}件 +{pts}")

    status = item.get("connection_status") or ""
    pts = STATUS_MATURITY.get(status, 0)
    if pts:
        score += pts
        factors.append(f"接続状態({status}) +{pts}")

    return _clamp(score), factors


def trust_breakdown(item: dict, verified: bool) -> tuple[int, str, list[str]]:
    factors: list[str] = []
    score = 0
    if item.get("provider_type") in {"government", "international", "official", "foundation"}:
        score += 30
        factors.append("公的/国際/公式/財団 提供元 +30")
    if item.get("document_url"):
        score += 20
        factors.append("公式ドキュメントあり +20")
    if item.get("license_note") and item.get("commercial_use") != "unknown":
        score += 20
        factors.append("ライセンス明記 +20")
    if item.get("update_frequency"):
        score += 10
        factors.append("更新頻度あり +10")
    if item.get("data_formats"):
        score += 10
        factors.append("データ形式あり +10")
    if verified:
        score += 10
        factors.append("実接続検証 成功 +10")
    score = min(score, 100)
    return score, trust_rank(score), factors


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute catalog scores from rubrics.")
    parser.add_argument(
        "--write", action="store_true", help="write recomputed scores to the catalog"
    )
    args = parser.parse_args()

    catalog = load_catalog()
    verification = load_verification_results()
    latest = latest_verification_by_api(verification)

    before_fit = sum(i["business_fit_score"] for i in catalog) / len(catalog)
    before_int = sum(i["integration_score"] for i in catalog) / len(catalog)

    for item in catalog:
        verified = latest.get(item["id"], {}).get("result") == "success"

        fit, fit_factors = business_fit_breakdown(item)
        integ, integ_factors = integration_breakdown(item, verified)
        item["business_fit_score"] = fit
        item["integration_score"] = integ

        trust_value, rank, trust_factors = trust_breakdown(item, verified)
        item["trust_rank"] = rank

        prio_value = priority_score(item, trust_value)
        item["connection_priority"] = priority_rank(prio_value)

        projects = item.get("target_projects") or []
        item["score_breakdown"] = {
            "business_fit": {"score": fit, "factors": fit_factors},
            "integration": {"score": integ, "factors": integ_factors},
            "trust": {"score": trust_value, "rank": rank, "factors": trust_factors},
            "priority": {
                "score": round(prio_value, 1),
                "rank": item["connection_priority"],
                "factors": [
                    f"信頼度 {trust_value}×0.30",
                    f"事業適合度 {fit}×0.35",
                    f"連携実装性 {integ}×0.20",
                    f"対象案件 {min(len(projects) * 25, 100)}×0.15",
                ],
            },
        }

    after_fit = sum(i["business_fit_score"] for i in catalog) / len(catalog)
    after_int = sum(i["integration_score"] for i in catalog) / len(catalog)
    print(f"business_fit avg: {before_fit:.0f} -> {after_fit:.0f}")
    print(f"integration avg: {before_int:.0f} -> {after_int:.0f}")
    from collections import Counter

    print("trust_rank:", dict(Counter(i["trust_rank"] for i in catalog)))
    print("connection_priority:", dict(Counter(i["connection_priority"] for i in catalog)))

    if args.write:
        write_json(CATALOG_PATH, catalog)
        write_json(EXPORT_DIR / "api_catalog.json", catalog)
        print("written:", CATALOG_PATH)
    else:
        print("(dry run; pass --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
