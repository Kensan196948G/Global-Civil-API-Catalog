"""db.session エンジン設定の単体テスト（実DB接続は不要）。

ここで固定したい性質は、2026-08 の本番DB障害を「見えなく」していた原因の
ひとつである。DBが死んでいる場合の health probe は、

* 200 + status=ok を返してはならない（監視が成功と誤認する）、
* ハングしてはならない（監視がタイムアウトし、何も分からない）。

``create_engine()`` は接続を開かないため ``CATALOG_DATABASE_URL`` は不要だが、
``db.session`` は SQLAlchemy を要する。CI の ``catalog`` ジョブは
意図的に stdlib のみ（`pip install pytest ruff mypy pip-audit`）で DB 依存を
入れないため、**モジュールレベルで importorskip する**。これを怠ると
コレクション時 ImportError でジョブ全体が落ちる（PR #98 で実際に発生）。
DB 依存が入る ``db-api`` ジョブでは実行される。
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from db.session import (  # noqa: E402
    DEFAULT_CONNECT_TIMEOUT,
    make_engine,
)


def _libpq_args(engine) -> dict:
    """libpqへ渡る実際のキーワード引数を取り出す。"""
    _, opts = engine.dialect.create_connect_args(engine.url)
    return opts


def test_engine_sets_connect_timeout_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CATALOG_DB_CONNECT_TIMEOUT", raising=False)
    engine = make_engine("postgresql+psycopg://u:p@127.0.0.1:1/db")
    assert _libpq_args(engine)["connect_timeout"] == str(DEFAULT_CONNECT_TIMEOUT)


def test_default_timeout_is_fast_enough_for_monitoring() -> None:
    """OS既定(約120秒)を継承していないこと。監視が待たされると意味がない。"""
    assert DEFAULT_CONNECT_TIMEOUT <= 10


def test_connect_timeout_is_overridable(monkeypatch) -> None:
    monkeypatch.setenv("CATALOG_DB_CONNECT_TIMEOUT", "3")
    engine = make_engine("postgresql+psycopg://u:p@127.0.0.1:1/db")
    assert _libpq_args(engine)["connect_timeout"] == "3"


def test_invalid_connect_timeout_falls_back_to_default(monkeypatch) -> None:
    for bad in ("abc", "0", "-5", "  "):
        monkeypatch.setenv("CATALOG_DB_CONNECT_TIMEOUT", bad)
        engine = make_engine("postgresql+psycopg://u:p@127.0.0.1:1/db")
        assert _libpq_args(engine)["connect_timeout"] == str(
            DEFAULT_CONNECT_TIMEOUT
        ), f"invalid value {bad!r} must fall back to the default"


def test_explicit_url_timeout_wins(monkeypatch) -> None:
    """接続文字列に明示された connect_timeout を上書きしないこと。"""
    monkeypatch.setenv("CATALOG_DB_CONNECT_TIMEOUT", "9")
    engine = make_engine("postgresql+psycopg://u:p@127.0.0.1:1/db?connect_timeout=2")
    assert _libpq_args(engine)["connect_timeout"] == "2"


def test_url_credentials_and_params_are_preserved() -> None:
    """タイムアウト付与で既存のURL要素を壊さないこと。"""
    engine = make_engine("postgresql+psycopg://u:p@db.example:5433/catalog?sslmode=require")
    args = _libpq_args(engine)
    assert args["host"] == "db.example"
    assert args["port"] == 5433
    assert args["dbname"] == "catalog"
    assert args["sslmode"] == "require"
    assert "connect_timeout" in args


def test_make_engine_requires_url_when_env_absent(monkeypatch) -> None:
    """環境変数が無い状態でDB位置を推測しないこと（誤接続の防止）。"""
    import pytest

    from db.session import database_url

    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        database_url()
