"""Unit tests for scripts/backup_catalog.py (uses tmp dirs only)."""

import json
from pathlib import Path

from scripts.backup_catalog import backup


def _fixture(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "export").mkdir()
    (root / "data" / "api_catalog.json").write_text('[{"id": "A"}]', encoding="utf-8")
    (root / "data" / "verification_results.json").write_text("[]", encoding="utf-8")
    (root / "data" / "catalog_metadata.json").write_text('{"record_count": 1}', encoding="utf-8")
    (root / "export" / "API台帳.md").write_text("# API台帳", encoding="utf-8")


def test_backup_copies_and_validates_json(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    _fixture(src)

    count, copied = backup(src, dest)

    assert count == 4
    assert len(copied) == 4
    snapshot = next(dest.glob("catalog-*"))
    payload = json.loads((snapshot / "api_catalog.json").read_text(encoding="utf-8"))
    assert payload == [{"id": "A"}]
    assert (snapshot / "API台帳.md").exists()


def test_backup_without_export_still_copies_core(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "data").mkdir(parents=True)
    (src / "data" / "api_catalog.json").write_text("[]", encoding="utf-8")

    count, _ = backup(src, dest)

    assert count == 1
