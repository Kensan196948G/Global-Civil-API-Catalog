from scripts.catalog_utils import EXPORT_DIR
from scripts.export_markdown import export_all


def test_export_all_generates_expected_files() -> None:
    outputs = set(export_all())

    assert "API台帳.md" in outputs
    assert "API台帳_帳票.html" in outputs
    assert "接続優先度.md" in outputs
    assert "接続検証結果.md" in outputs
    assert "本格利用候補.md" in outputs
    assert (EXPORT_DIR / "API台帳.md").exists()
    assert (EXPORT_DIR / "API台帳_帳票.html").exists()
    assert "GSI-TILE-STD-001" in (EXPORT_DIR / "API台帳.md").read_text(encoding="utf-8")


def test_print_report_html_is_print_ready() -> None:
    text = (EXPORT_DIR / "API台帳_帳票.html").read_text(encoding="utf-8")
    assert "API・公開データ台帳 帳票" in text
    assert "@media print" in text
    assert "GSI-TILE-STD-001" in text
