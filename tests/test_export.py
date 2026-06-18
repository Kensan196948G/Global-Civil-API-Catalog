from scripts.export_markdown import export_all
from scripts.catalog_utils import EXPORT_DIR


def test_export_all_generates_expected_files() -> None:
    outputs = set(export_all())

    assert "API台帳.md" in outputs
    assert "接続優先度.md" in outputs
    assert "接続検証結果.md" in outputs
    assert "本格利用候補.md" in outputs
    assert (EXPORT_DIR / "API台帳.md").exists()
    assert "GSI-TILE-STD-001" in (EXPORT_DIR / "API台帳.md").read_text(encoding="utf-8")
