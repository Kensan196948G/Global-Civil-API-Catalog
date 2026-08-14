from __future__ import annotations

import sys
from pathlib import Path

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


def build_catalog_report_html(
    catalog: list[dict],
    verification_by_api: dict[str, dict],
    metadata: dict,
) -> str:
    """Print-friendly 帳票 (one page per entry, browser print/PDF export)."""
    is_demo = metadata.get("catalog_mode") == "demo"
    banner = (
        '<p class="demoBanner">⚠ デモ用（全て架空データ）</p>'
        if is_demo
        else ""
    )
    rows = []
    for item in sorted(catalog, key=lambda row: row["id"]):
        latest = verification_by_api.get(item["id"], {})
        formats = ", ".join(item.get("data_formats", []) or [])
        key_line = f"{item.get('api_key_required', '-')} / {item.get('auth_type', '-')}"
        license_line = (
            f"{item.get('license_note', '-')}（商用: {item.get('commercial_use', '-')}）"
        )
        rank_line = (
            f"{item.get('trust_rank', '-')} / {item.get('connection_priority', '-')}"
        )
        score_line = (
            f"{item.get('business_fit_score', '-')} / "
            f"{item.get('integration_score', '-')}"
        )
        verification_line = (
            f"{latest.get('result', '未検証')}（{latest.get('verified_at', '-')}）"
        )
        rows.append(
            f"""<section class="entry">
  <h2>{item['name']} <span class="mono">{item['id']}</span></h2>
  <table>
    <tr><th>カテゴリ</th><td>{item.get('category', '-')} / {item.get('sub_category', '-')}</td></tr>
    <tr><th>提供元</th><td>{item.get('provider', '-')}（{item.get('provider_type', '-')}）</td></tr>
    <tr><th>地域</th><td>{item.get('region', '-')}</td></tr>
    <tr><th>データ形式</th><td>{formats}</td></tr>
    <tr><th>APIキー</th><td>{key_line}</td></tr>
    <tr><th>利用条件</th><td>{license_line}</td></tr>
    <tr><th>更新頻度</th><td>{item.get('update_frequency', '-')}</td></tr>
    <tr><th>接続状態</th><td>{item.get('connection_status', '-')}</td></tr>
    <tr><th>信頼度 / 優先度</th><td>{rank_line}</td></tr>
    <tr><th>事業適合 / 連携実装</th><td>{score_line}</td></tr>
    <tr><th>最新検証</th><td>{verification_line}</td></tr>
    <tr><th>公式URL</th><td>{item.get('official_url', '-')}</td></tr>
    <tr><th>ドキュメント</th><td>{item.get('document_url', '-')}</td></tr>
    <tr><th>利用説明</th><td>{item.get('usage_summary', '-')}</td></tr>
    <tr><th>注意点・リスク</th><td>{item.get('risk_note', '-')}</td></tr>
    <tr><th>最終確認</th><td>{item.get('last_checked_at', '-')}</td></tr>
  </table>
</section>"""
        )
    today = __import__("datetime").date.today().isoformat()
    mode = metadata.get("catalog_mode", "-")
    source = metadata.get("source", "-")
    imported_at = metadata.get("imported_at", "-")
    verification_count = metadata.get("verification_count", "-")
    meta_line = (
        f"データ状態: {mode} ／ 取込元: {source} ／ 取込日: {imported_at} ／ "
        f"登録: {len(catalog)}件 ／ 検証: {verification_count}件"
    )
    print_note = (
        "印刷: ブラウザの「印刷 → PDFに保存」で出力できます。"
        f"生成: {today}"
    )
    style = (
        "body { font-family: 'Hiragino Kaku Gothic ProN', 'Yu Gothic', sans-serif; "
        "margin: 24px; color: #1b1f23; } "
        "h1 { border-bottom: 3px solid #2563eb; padding-bottom: 8px; } "
        ".meta { color: #57606a; font-size: 13px; } "
        ".demoBanner { background: #fff3cd; border: 1px solid #e0a800; "
        "padding: 8px 12px; border-radius: 6px; } "
        ".entry { page-break-inside: avoid; margin: 24px 0; } "
        ".entry h2 { font-size: 16px; margin: 0 0 8px; } "
        ".mono { font-family: monospace; font-size: 12px; color: #57606a; } "
        "table { border-collapse: collapse; width: 100%; font-size: 12px; } "
        "th, td { border: 1px solid #d0d7de; padding: 4px 8px; "
        "text-align: left; vertical-align: top; } "
        "th { width: 140px; background: #f6f8fa; } "
        "a { color: #0969da; word-break: break-all; } "
        "@media print { body { margin: 0; } "
        "a { color: inherit; text-decoration: none; } }"
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>API台帳 帳票（{mode}）</title>
  <style>{style}</style>
</head>
<body>
  <h1>API・公開データ台帳 帳票</h1>
  <p class="meta">{meta_line}</p>
  {banner}
  <p class="meta">{print_note}</p>
  {''.join(rows)}
</body>
</html>
"""


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
        "API台帳_帳票.html": build_catalog_report_html(
            catalog, verification_by_api, load_catalog_metadata()
        ),
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
