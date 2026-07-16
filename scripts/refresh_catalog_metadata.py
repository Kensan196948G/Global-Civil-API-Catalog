"""Recompute record_count/verification_count in catalog_metadata.json.

scheduled-verify.yml overwrites api_catalog.json and verification_results.json
weekly but never touches catalog_metadata.json, so these two counters drift
from the live data every time a candidate's connection_status crosses the
run_verification.py acceptance filter. Provenance fields set at import time
(catalog_sha256, verification_sha256, imported_at, source, ...) are left
untouched here; they describe the last production bundle import, not the
live catalog, so recomputing them from current data would be wrong.

Run: python scripts/refresh_catalog_metadata.py [--write]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    CATALOG_METADATA_PATH,
    load_catalog,
    load_catalog_metadata,
    load_verification_results,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh record_count/verification_count in catalog_metadata.json."
    )
    parser.add_argument(
        "--write", action="store_true", help="write refreshed counts to catalog_metadata.json"
    )
    args = parser.parse_args()

    catalog = load_catalog()
    verification_results = load_verification_results()
    metadata = load_catalog_metadata()

    before = (metadata.get("record_count"), metadata.get("verification_count"))
    metadata["record_count"] = len(catalog)
    metadata["verification_count"] = len(verification_results)
    after = (metadata["record_count"], metadata["verification_count"])

    print(f"record_count: {before[0]} -> {after[0]}")
    print(f"verification_count: {before[1]} -> {after[1]}")

    if args.write:
        write_json(CATALOG_METADATA_PATH, metadata)
        print("written:", CATALOG_METADATA_PATH)
    else:
        print("(dry run; pass --write to persist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
