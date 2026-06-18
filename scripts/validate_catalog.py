from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (
    load_catalog,
    load_verification_results,
    validate_catalog,
    validate_verification_results,
)


def main() -> int:
    catalog = load_catalog()
    verification_results = load_verification_results()
    errors = validate_catalog(catalog)
    errors.extend(validate_verification_results(verification_results, catalog))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(catalog)} catalog records, "
        f"{len(verification_results)} verification results"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
