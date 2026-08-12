"""Snapshot the JSON catalog and export artifacts into a timestamped folder.

Usage:
    python scripts/backup_catalog.py [--dest backups]

Copies data/api_catalog.json, data/verification_results.json,
data/catalog_metadata.json and all export/ files, then verifies that every
copied .json file parses. The JSON catalog is the dual-run source of truth,
so this is a cheap daily/weekly safety net alongside Neon PITR.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORE_FILES = (
    "data/api_catalog.json",
    "data/verification_results.json",
    "data/catalog_metadata.json",
)


def backup(source_root: Path, dest_root: Path) -> tuple[int, list[str]]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_root / f"catalog-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for relative in CORE_FILES:
        src = source_root / relative
        if src.exists():
            target = dest / Path(relative).name
            shutil.copy2(src, target)
            copied.append(str(target.relative_to(dest_root)))
    export_dir = source_root / "export"
    if export_dir.exists():
        for src in sorted(export_dir.iterdir()):
            if src.is_file():
                target = dest / src.name
                shutil.copy2(src, target)
                copied.append(str(target.relative_to(dest_root)))
    for name in copied:
        path = dest_root / name
        if path.suffix == ".json":
            with path.open(encoding="utf-8") as file:
                json.load(file)
    return len(copied), copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", default=str(ROOT / "backups"), help="backup destination root"
    )
    args = parser.parse_args(argv)
    count, copied = backup(ROOT, Path(args.dest))
    print(f"backed up {count} file(s) to {Path(args.dest).resolve()}")
    for name in copied:
        print(f"  {name}")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
