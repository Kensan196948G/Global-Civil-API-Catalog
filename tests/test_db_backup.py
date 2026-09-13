"""scripts/db_backup.py の単体テスト（実DB・実pg_dumpは不要）。

カバーするのは「静かに壊れる」種類の不具合:

* pg_dump と pg_restore のメジャー版が不一致だと、バックアップは取れるのに
  検証も復元もできない（2026-09-13 に実測）。
* 不完全なアーカイブを残すと、復元時に初めて壊れていると分かる。
* 世代管理が効かないとディスクを食い潰す。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.db_backup as db_backup


def test_build_argv_uses_matched_bindir(tmp_path: Path) -> None:
    """pg_dump は bindir の絶対パスで解決されること（PATH 依存を排除）。"""
    argv = db_backup.build_pg_dump_argv(
        "somedb",
        tmp_path / "x.dump",
        host="/var/run/postgresql",
        bindir="/usr/lib/postgresql/16/bin",
    )
    assert argv[0] == "/usr/lib/postgresql/16/bin/pg_dump"
    assert "--format=custom" in argv
    assert "--no-owner" in argv
    assert "--no-privileges" in argv
    # パスワードを引数で渡さないこと（peer 認証を使う）
    assert not any("password" in a.lower() for a in argv)


def test_build_argv_defaults_to_server_matching_major() -> None:
    """既定の bindir はサーバ(16.14)と同一メジャーであること。

    新しい pg_dump は dump に `SET transaction_timeout = 0;` を埋め込み、
    サーバ16では復元に失敗する。また pg_restore とメジャーが違うと
    アーカイブ形式を読めない。両方を同時に満たす必要がある。
    """
    assert db_backup.DEFAULT_BINDIR == "/usr/lib/postgresql/16/bin"


def test_build_argv_without_bindir_falls_back_to_path(tmp_path: Path) -> None:
    argv = db_backup.build_pg_dump_argv(
        "somedb", tmp_path / "x.dump", host="127.0.0.1", port="5433", bindir=None
    )
    assert argv[0] == "pg_dump"
    assert "--port" in argv and "5433" in argv


def test_tool_falls_back_when_bindir_invalid() -> None:
    assert db_backup._tool("pg_dump", "/nonexistent/bin") == "pg_dump"


def test_verify_dump_rejects_missing_file(tmp_path: Path) -> None:
    ok, detail = db_backup.verify_dump(tmp_path / "nope.dump")
    assert ok is False
    assert "missing or empty" in detail


def test_verify_dump_rejects_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.dump"
    empty.write_bytes(b"")
    ok, detail = db_backup.verify_dump(empty)
    assert ok is False
    assert "missing or empty" in detail


def test_prune_keeps_newest_generations(tmp_path: Path) -> None:
    names = [
        "gcac-20260101-000000.dump",
        "gcac-20260102-000000.dump",
        "gcac-20260103-000000.dump",
        "gcac-20260104-000000.dump",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    removed = db_backup.prune(tmp_path, keep=2)
    # 新しい2世代(0103, 0104)を残し、古い2世代(0101, 0102)を消す
    assert sorted(p.name for p in removed) == names[:2]
    assert sorted(p.name for p in tmp_path.glob("gcac-*.dump")) == names[2:]


def test_prune_also_removes_orphan_checksum(tmp_path: Path) -> None:
    old = tmp_path / "gcac-20260101-000000.dump"
    old.write_bytes(b"x")
    old.with_suffix(".dump.sha256").write_text("deadbeef", encoding="utf-8")
    newest = tmp_path / "gcac-20260102-000000.dump"
    newest.write_bytes(b"x")

    db_backup.prune(tmp_path, keep=1)
    assert not old.exists()
    assert not old.with_suffix(".dump.sha256").exists()
    assert newest.exists()


def test_prune_ignores_foreign_files(tmp_path: Path) -> None:
    """命名規則に合わないファイルを勝手に消さないこと。"""
    keep_me = tmp_path / "manual-backup.dump"
    keep_me.write_bytes(b"important")
    (tmp_path / "gcac-20260101-000000.dump").write_bytes(b"x")
    db_backup.prune(tmp_path, keep=1)
    assert keep_me.exists(), "prune must not delete files outside its naming scheme"


def test_prune_keep_zero_is_noop(tmp_path: Path) -> None:
    (tmp_path / "gcac-20260101-000000.dump").write_bytes(b"x")
    assert db_backup.prune(tmp_path, keep=0) == []
    assert list(tmp_path.glob("gcac-*.dump"))


def test_dry_run_creates_nothing(tmp_path: Path) -> None:
    rc = db_backup.run_backup(
        dest_root=tmp_path,
        database="somedb",
        host="/var/run/postgresql",
        port=None,
        keep=3,
        dry_run=True,
    )
    assert rc == 0
    assert list(tmp_path.glob("*.dump")) == []


def test_main_rejects_negative_keep(tmp_path: Path) -> None:
    """keep が負でも落ちず、全世代を消さないこと。"""
    (tmp_path / "gcac-20260101-000000.dump").write_bytes(b"x")
    assert db_backup.prune(tmp_path, keep=-1) == []
    assert list(tmp_path.glob("gcac-*.dump"))


@pytest.mark.parametrize("stamp", ["gcac-20260101-000000.dump", "gcac-20261231-235959.dump"])
def test_stamp_pattern_accepts_expected_names(stamp: str) -> None:
    assert db_backup._STAMP_RE.match(stamp)
