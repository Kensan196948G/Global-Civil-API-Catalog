from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    EXPORT_DIR,
    latest_verification_by_api,
    load_catalog,
    load_catalog_metadata,
    load_verification_results,
    priority_rank,
    priority_score,
    trust_rank,
    trust_score,
    write_csv,
    write_json,
)


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        escaped = [str(cell).replace("\n", " ").replace("|", "/") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def build_catalog_markdown(catalog: list[dict], verification_by_api: dict[str, dict]) -> str:
    rows = []
    for item in catalog:
        latest = verification_by_api.get(item["id"], {})
        rows.append(
            [
                item["id"],
                item["name"],
                item["category"],
                item["provider"],
                ", ".join(item["data_formats"]),
                item["api_key_required"],
                item["trust_rank"],
                str(item["connection_priority"]),
                item["connection_status"],
                latest.get("result", "-"),
                item.get("usage_summary", ""),
            ]
        )
    metadata = load_catalog_metadata()
    intro = (
        "# API台帳\n\n"
        f"- データ状態: {metadata.get('catalog_mode', '-')}\n"
        f"- 取込元: {metadata.get('source', '-')}\n"
        f"- 取込日: {metadata.get('imported_at', '-')}\n"
        f"- 登録件数: {metadata.get('record_count', len(catalog))}件\n\n"
    )
    return intro + md_table(
        [
            "ID",
            "名称",
            "カテゴリ",
            "提供元",
            "形式",
            "APIキー",
            "信頼度",
            "優先度",
            "状態",
            "最新検証",
            "利用説明",
        ],
        rows,
    ) + "\n"


def build_priority_markdown(catalog: list[dict], verification_by_api: dict[str, dict]) -> str:
    scored = []
    for item in catalog:
        score = trust_score(item, verification_by_api)
        total = priority_score(item, score)
        scored.append((total, item, score))

    rows = []
    for total, item, score in sorted(scored, reverse=True, key=lambda value: value[0]):
        rows.append(
            [
                item["id"],
                item["name"],
                f"{total:.1f}",
                str(priority_rank(total)),
                str(score),
                trust_rank(score),
                item["connection_status"],
                item.get("risk_note", ""),
            ]
        )

    return "# 接続優先度\n\n" + md_table(
        ["ID", "名称", "総合点", "優先度", "信頼度点", "信頼度ランク", "状態", "リスク"],
        rows,
    ) + "\n"


def build_verification_markdown(results: list[dict]) -> str:
    rows = []
    for item in sorted(results, key=lambda row: row["verified_at"], reverse=True):
        rows.append(
            [
                item["id"],
                item["api_id"],
                item["verified_at"],
                item["result"],
                str(item.get("http_status") or "-"),
                str(item.get("response_time_ms") or "-"),
                item.get("note", ""),
            ]
        )
    return "# 接続検証結果\n\n" + md_table(
        ["検証ID", "API ID", "検証日時", "結果", "HTTP", "応答ms", "備考"],
        rows,
    ) + "\n"


def build_candidate_markdown(catalog: list[dict]) -> str:
    candidates = [item for item in catalog if item["connection_status"] == "本格利用候補"]
    rows = [
        [
            item["id"],
            item["name"],
            item["provider"],
            ", ".join(item.get("target_projects", [])),
            item.get("adoption_reason", ""),
        ]
        for item in candidates
    ]
    return "# 本格利用候補\n\n" + md_table(
        ["ID", "名称", "提供元", "利用候補PJ", "採用理由"],
        rows,
    ) + "\n"


def export_all() -> list[str]:
    catalog = load_catalog()
    verification_results = load_verification_results()
    verification_by_api = latest_verification_by_api(verification_results)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "API台帳.md": build_catalog_markdown(catalog, verification_by_api),
        "接続優先度.md": build_priority_markdown(catalog, verification_by_api),
        "接続検証結果.md": build_verification_markdown(verification_results),
        "本格利用候補.md": build_candidate_markdown(catalog),
    }

    for filename, content in outputs.items():
        (EXPORT_DIR / filename).write_text(content, encoding="utf-8")

    csv_fields = [
        "id",
        "name",
        "category",
        "provider",
        "region",
        "catalog_mode",
        "production_source",
        "production_imported_at",
        "api_key_required",
        "connection_status",
        "trust_rank",
        "connection_priority",
        "usage_summary",
    ]
    write_csv(EXPORT_DIR / "api_catalog.csv", catalog, csv_fields)
    write_json(EXPORT_DIR / "api_catalog.json", catalog)
    write_json(EXPORT_DIR / "catalog_metadata.json", load_catalog_metadata())
    return list(outputs) + ["api_catalog.csv", "api_catalog.json", "catalog_metadata.json"]


def main() -> int:
    outputs = export_all()
    print("Exported: " + ", ".join(outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
