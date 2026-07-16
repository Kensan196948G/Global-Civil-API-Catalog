import json
import sys

import scripts.refresh_catalog_metadata as refresh_catalog_metadata
from scripts.catalog_utils import load_catalog, load_verification_results


def test_refresh_writes_live_counts_only_with_write_flag(tmp_path, monkeypatch) -> None:
    metadata_path = tmp_path / "catalog_metadata.json"
    metadata_path.write_text(
        json.dumps({"record_count": 0, "verification_count": 0, "catalog_sha256": "unchanged"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(refresh_catalog_metadata, "CATALOG_METADATA_PATH", metadata_path)
    monkeypatch.setattr(
        refresh_catalog_metadata,
        "load_catalog_metadata",
        lambda: json.loads(metadata_path.read_text(encoding="utf-8")),
    )

    monkeypatch.setattr(sys, "argv", ["refresh_catalog_metadata.py"])
    assert refresh_catalog_metadata.main() == 0
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["record_count"] == 0

    monkeypatch.setattr(sys, "argv", ["refresh_catalog_metadata.py", "--write"])
    assert refresh_catalog_metadata.main() == 0

    written = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert written["record_count"] == len(load_catalog())
    assert written["verification_count"] == len(load_verification_results())
    assert written["catalog_sha256"] == "unchanged"
