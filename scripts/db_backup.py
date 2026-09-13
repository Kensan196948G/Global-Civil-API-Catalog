"""PostgreSQL の論理バックアップ（pg_dump）と世代管理。

Usage:
    python scripts/db_backup.py [--dest DIR] [--keep N] [--database NAME]
                                [--dry-run]

``docs/backup-restore.md`` は「Neon の PITR ＋ 任意の pg_dump」を前提に書かれて
いるが、本番DBがローカル PostgreSQL へ移行した時点で PITR は存在しなくなり、
pg_dump を定期実行する機構も無かった（2026-09-13 実測: ``backups/`` ディレクトリ
も systemd unit も timer も無し）。このスクリプトがその欠落を埋める。

設計方針:

* 認証は Unix ソケットの peer 認証（``-h /var/run/postgresql``）を使う。
  パスワードを環境変数・引数・ログのどこにも出さないため。TCP を使う場合は
  ``--host`` を明示し、``PGPASSWORD`` 等は呼び出し側の責任で管理する。
* ``--format=custom`` ＋ ``-Z`` で圧縮。``pg_restore --list`` が通ることを
  取得直後に検証する（「ファイルができた」だけでは PASS にしない）。
* 世代管理は既定14世代。ディレクトリ名のタイムスタンプで新しい順に判定する。
* 失敗は非 0 終了で報告する。systemd の failed 状態は次の成功で消えるため、
  呼び出し側 unit が durable なマーカーを残せるよう出力を明示する。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATABASE = "global_civil_api_catalog"
DEFAULT_KEEP = 14
# peer 認証で接続するための Unix ソケットディレクトリ。TCP を使うと
# パスワードが要る／平文が設定ファイルに載るため、既定はソケット。
DEFAULT_SOCKET_DIR = "/var/run/postgresql"

# 【重要・2026-09-13 実測した不具合】
#   1) PATH 上の pg_dump は /usr/local/bin -> PostgreSQL 17.10、pg_restore は
#      /usr/bin -> PostgreSQL 16.14 と**メジャー不一致**だった。pg_dump 17 は
#      アーカイブ形式 1.16 を書き、pg_restore 16 はそれを読めない
#      （"ファイルヘッダ内のバージョン(1.16)はサポートされていません"）。
#   2) さらに新しい pg_dump (18) を使うと、dump に
#      `SET transaction_timeout = 0;` が埋め込まれる。これは PG17 以降の
#      パラメータなので、サーバが 16.14 だと復元時に
#      `unrecognized configuration parameter "transaction_timeout"` で失敗する。
#   したがって dump と restore は (a) 相互に同一メジャー、(b) サーバ以下、
#   の両方を満たす必要がある。本ホストのサーバは 16.14 なので 16 を既定にする。
#   サーバをメジャーアップグレードした場合は CATALOG_PG_BINDIR を合わせること。
DEFAULT_BINDIR = "/usr/lib/postgresql/16/bin"

_STAMP_RE = re.compile(r"^gcac-(\d{8}-\d{6})\.dump$")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _tool(name: str, bindir: str | None) -> str:
    """bindir 内の絶対パスを優先し、無ければ PATH 上の名前を使う。"""
    if bindir:
        candidate = Path(bindir) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return name


def build_pg_dump_argv(
    database: str,
    dest_file: Path,
    *,
    host: str,
    port: str | None = None,
    bindir: str | None = DEFAULT_BINDIR,
) -> list[str]:
    """pg_dump の引数を組み立てる（テスト可能なように分離）。"""
    argv = [
        _tool("pg_dump", bindir),
        "--format=custom",
        "--compress=9",
        "--no-owner",
        "--no-privileges",
        "--host",
        host,
        "--dbname",
        database,
        "--file",
        str(dest_file),
    ]
    if port:
        argv.extend(["--port", port])
    return argv


def prune(dest_root: Path, keep: int, *, dry_run: bool = False) -> list[Path]:
    """古いバックアップを削除し、削除した一覧を返す。"""
    if keep <= 0:
        return []
    dumps = sorted(
        (p for p in dest_root.glob("gcac-*.dump") if _STAMP_RE.match(p.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    stale = dumps[keep:]
    if not dry_run:
        for path in stale:
            path.unlink()
            checksum = path.with_suffix(path.suffix + ".sha256")
            if checksum.exists():
                checksum.unlink()
    return stale


def verify_dump(dump_file: Path, *, bindir: str | None = DEFAULT_BINDIR) -> tuple[bool, str]:
    """アーカイブが pg_restore で読めることを確認する。"""
    if not dump_file.exists() or dump_file.stat().st_size == 0:
        return False, "dump file is missing or empty"
    restore = _tool("pg_restore", bindir)
    if shutil.which(restore) is None and not Path(restore).is_file():
        return False, f"pg_restore not found ({restore}); cannot verify archive"
    proc = subprocess.run(
        [restore, "--list", str(dump_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False, (proc.stderr.strip() or "pg_restore --list failed")
    tables = sum(1 for line in proc.stdout.splitlines() if " TABLE DATA " in line)
    return True, f"{tables} table data entr(ies) readable"


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_backup(
    *,
    dest_root: Path,
    database: str,
    host: str,
    port: str | None,
    keep: int,
    bindir: str | None = DEFAULT_BINDIR,
    dry_run: bool = False,
) -> int:
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_file = dest_root / f"gcac-{_stamp()}.dump"
    argv = build_pg_dump_argv(database, dest_file, host=host, port=port, bindir=bindir)

    if dry_run:
        print(f"DRY-RUN would execute: {' '.join(argv)}")
        return 0

    dump_tool = argv[0]
    if shutil.which(dump_tool) is None and not Path(dump_tool).is_file():
        print(f"ERROR: pg_dump not found ({dump_tool})", file=sys.stderr)
        return 1

    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        # stderr に接続文字列そのものは出ないが、念のためそのまま出す
        print(f"ERROR: pg_dump failed (exit {proc.returncode})", file=sys.stderr)
        print(proc.stderr.strip(), file=sys.stderr)
        if dest_file.exists():
            dest_file.unlink()  # 不完全なアーカイブを残さない
        return 1

    ok, detail = verify_dump(dest_file, bindir=bindir)
    if not ok:
        print(f"ERROR: dump verification failed: {detail}", file=sys.stderr)
        dest_file.unlink(missing_ok=True)
        return 1

    checksum = _sha256(dest_file)
    dest_file.with_suffix(dest_file.suffix + ".sha256").write_text(
        f"{checksum}  {dest_file.name}\n", encoding="utf-8"
    )
    size_mb = dest_file.stat().st_size / (1024 * 1024)
    print(f"OK: {dest_file} ({size_mb:.1f} MiB, sha256={checksum[:16]}...)")
    print(f"    verified: {detail}")

    removed = prune(dest_root, keep)
    for path in removed:
        print(f"    pruned: {path.name}")
    remaining = len(list(dest_root.glob("gcac-*.dump")))
    print(f"    retained: {remaining} generation(s) (keep={keep})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default=os.environ.get(
            "CATALOG_BACKUP_DIR", str(Path.home() / "backups" / "global-civil-api-catalog")
        ),
        help="backup destination directory",
    )
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="generations to retain")
    parser.add_argument(
        "--database", default=os.environ.get("CATALOG_BACKUP_DATABASE", DEFAULT_DATABASE)
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("CATALOG_BACKUP_HOST", DEFAULT_SOCKET_DIR),
        help="socket directory (peer auth) or TCP host",
    )
    parser.add_argument("--port", default=os.environ.get("CATALOG_BACKUP_PORT") or None)
    parser.add_argument(
        "--bindir",
        default=os.environ.get("CATALOG_PG_BINDIR", DEFAULT_BINDIR),
        help="directory holding matching-major pg_dump/pg_restore",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    return run_backup(
        dest_root=Path(args.dest),
        database=args.database,
        host=args.host,
        port=args.port,
        keep=args.keep,
        bindir=args.bindir or None,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
