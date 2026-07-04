from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    CATALOG_METADATA_PATH,
    CATALOG_PATH,
    ROOT,
    VERIFICATION_PATH,
    load_catalog,
    load_verification_results,
    write_json,
)

DESIGN_HTML_PATH = ROOT / "web" / "Global Civil API Catalog.html"
PRODUCTION_SOURCE = "claude-design-bundle"


def _script_content(html: str, script_type: str) -> str:
    match = re.search(
        r'<script type="' + re.escape(script_type) + r'">\s*(.*?)\s*</script>',
        html,
        re.S,
    )
    if not match:
        raise ValueError(f"missing bundled script: {script_type}")
    return match.group(1)


def _decode_resource(manifest: dict[str, Any], uuid: str) -> bytes:
    item = manifest[uuid]
    raw = base64.b64decode(item["data"])
    if item.get("compressed"):
        raw = gzip.decompress(raw)
    return raw


def load_design_resources() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, str]
]:
    html = DESIGN_HTML_PATH.read_text(encoding="utf-8")
    manifest = json.loads(_script_content(html, "__bundler/manifest"))
    resources = json.loads(_script_content(html, "__bundler/ext_resources"))

    decoded: dict[str, bytes] = {}
    for resource in resources:
        decoded[resource["id"]] = _decode_resource(manifest, resource["uuid"])

    if "catalog" not in decoded or "verification" not in decoded:
        raise ValueError(
            "design bundle must include catalog and verification resources"
        )

    hashes = {
        "design_html_sha256": hashlib.sha256(DESIGN_HTML_PATH.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(decoded["catalog"]).hexdigest(),
        "verification_sha256": hashlib.sha256(decoded["verification"]).hexdigest(),
    }
    return (
        json.loads(decoded["catalog"]),
        json.loads(decoded["verification"]),
        hashes,
    )


def merge_catalog(
    production_catalog: list[dict[str, Any]],
    current_catalog: list[dict[str, Any]],
    imported_at: str,
) -> list[dict[str, Any]]:
    current_by_id = {item["id"]: item for item in current_catalog}
    production_ids = {item["id"] for item in production_catalog}
    current_ids = set(current_by_id)
    if production_ids != current_ids:
        raise ValueError(
            "production and current catalog IDs differ: "
            f"only_production={sorted(production_ids - current_ids)}, "
            f"only_current={sorted(current_ids - production_ids)}"
        )

    merged: list[dict[str, Any]] = []
    for production_item in production_catalog:
        current_item = current_by_id[production_item["id"]]
        merged_item = dict(production_item)
        for key, value in current_item.items():
            if key not in merged_item:
                merged_item[key] = value
        merged_item["catalog_mode"] = "production"
        merged_item["production_source"] = PRODUCTION_SOURCE
        merged_item["production_imported_at"] = imported_at
        merged.append(merged_item)
    return merged


def check_verification_consistency(
    production_verification: list[dict[str, Any]],
    current_verification: list[dict[str, Any]],
    keep_local_verification: bool,
) -> None:
    """Guard the bundle/canonical verification equality unless explicitly kept local.

    When ``keep_local_verification`` is set the canonical ``verification_results.json``
    is treated as authoritative (it advances via weekly live verification), so the
    bundled snapshot is allowed to lag behind and no equality check is enforced.
    """
    if keep_local_verification:
        return
    if production_verification != current_verification:
        raise ValueError(
            "production verification data differs from canonical verification data"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the production catalog bundle."
    )
    parser.add_argument(
        "--keep-local-verification",
        action="store_true",
        help=(
            "Keep the canonical data/verification_results.json as authoritative and "
            "skip the bundle/canonical verification equality check."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    keep_local_verification = args.keep_local_verification

    imported_at = date.today().isoformat()
    production_catalog, production_verification, hashes = load_design_resources()
    current_catalog = load_catalog()
    current_verification = load_verification_results()

    check_verification_consistency(
        production_verification, current_verification, keep_local_verification
    )
    if keep_local_verification:
        hashes["verification_sha256"] = hashlib.sha256(
            VERIFICATION_PATH.read_bytes()
        ).hexdigest()

    merged_catalog = merge_catalog(production_catalog, current_catalog, imported_at)
    metadata = {
        "dataset_name": "Global Civil API Catalog production catalog",
        "catalog_mode": "production",
        "source": PRODUCTION_SOURCE,
        "source_path": DESIGN_HTML_PATH.relative_to(ROOT).as_posix(),
        "imported_at": imported_at,
        "record_count": len(merged_catalog),
        "verification_count": len(current_verification),
        "merge_policy": (
            "Production bundle fields are authoritative; local enrichment fields such as "
            "usage_summary and usage_notes are preserved."
        ),
        **hashes,
    }

    write_json(CATALOG_PATH, merged_catalog)
    write_json(CATALOG_METADATA_PATH, metadata)
    print(
        "Imported production catalog: "
        f"{metadata['record_count']} records, {metadata['verification_count']} verification results"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
