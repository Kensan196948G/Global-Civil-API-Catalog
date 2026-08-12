from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    latest_verification_by_api,
    load_catalog,
    load_verification_results,
    validate_catalog,
    validate_verification_results,
)


def consistency_warnings(
    catalog: list[dict],
    verification_results: list[dict],
) -> list[str]:
    """Warnings for operational data-quality drift (not hard errors)."""
    from datetime import date

    warnings: list[str] = []
    latest = latest_verification_by_api(verification_results)
    verified_statuses = {"接続検証済", "実装接続済", "本格利用候補"}
    for item in catalog:
        status = item.get("connection_status")
        if status in verified_statuses:
            latest_result = latest.get(item["id"])
            if latest_result is None:
                warnings.append(
                    f"{item['id']}: status='{status}' but no verification result recorded"
                )
            elif latest_result.get("result") != "success":
                warnings.append(
                    f"{item['id']}: status='{status}' but latest verification is "
                    f"'{latest_result.get('result')}' ({latest_result.get('verified_at')})"
                )
        checked = item.get("last_checked_at")
        try:
            age = (date.today() - date.fromisoformat(str(checked))).days
        except (TypeError, ValueError):
            continue
        if age > 180:
            warnings.append(
                f"{item['id']}: last_checked_at is {age} days old (>180 days)"
            )
    return warnings


def main() -> int:
    catalog = load_catalog()
    verification_results = load_verification_results()
    errors = validate_catalog(catalog)
    errors.extend(validate_verification_results(verification_results, catalog))
    warnings = consistency_warnings(catalog, verification_results)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    print(
        f"OK: {len(catalog)} catalog records, "
        f"{len(verification_results)} verification results, "
        f"{len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
