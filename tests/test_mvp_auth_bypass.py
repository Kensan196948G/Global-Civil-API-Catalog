"""MVP 公開デモ用のログイン認証バイパス（CATALOG_AUTH_BYPASS）。

DB を必要としない範囲で、有効化条件と付与ロールを固定する。
- 既定は無効（未ログインは従来どおり None）
- ``CATALOG_ENV`` が development/demo の**明示的な許可リスト**にある場合のみ有効
  （未設定・production・未知の値では必ず無効）
- 付与ロールは既定 Catalog.Viewer、未知のロール名は無視する
"""

from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("fastapi")

from web.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    auth_bypass_enabled,
    current_session,
)


class _Req:
    """cookie を持たない最小のリクエストスタブ。"""

    cookies: dict[str, str] = {}


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CATALOG_AUTH_BYPASS",
        "CATALOG_AUTH_BYPASS_ROLES",
        "CATALOG_AUTH_BYPASS_SUB",
        "CATALOG_AUTH_BYPASS_NAME",
        "CATALOG_ENV",
    ):
        monkeypatch.delenv(key, raising=False)


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    assert auth_bypass_enabled() is False
    assert current_session(_Req(), None) is None


def test_enabled_returns_viewer_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
    monkeypatch.setenv("CATALOG_ENV", "development")
    assert auth_bypass_enabled() is True
    session = current_session(_Req(), None)
    assert session is not None
    assert session.roles == [ROLE_VIEWER]


def test_production_is_never_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
    monkeypatch.setenv("CATALOG_ENV", "production")
    assert auth_bypass_enabled() is False
    assert current_session(_Req(), None) is None


def test_fails_closed_when_env_is_unset_or_unrecognised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回帰防止: 許可リスト方式であること。

    以前は拒否リスト方式（``CATALOG_ENV != "production"`` なら有効）だった
    ため、環境変数が未設定・別名・大文字小文字違い・末尾空白のいずれでも
    認証バイパスが成立してしまった。未設定／未知の環境では必ず無効でなければ
    ならない。
    """
    for env_value in (None, "", "prod", "Production", "production ", "stg", "staging", "test"):
        _clear(monkeypatch)
        monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
        if env_value is not None:
            monkeypatch.setenv("CATALOG_ENV", env_value)
        assert auth_bypass_enabled() is False, f"bypass must be off for CATALOG_ENV={env_value!r}"
        assert current_session(_Req(), None) is None


def test_demo_env_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """デモ環境も明示的な許可対象であること。"""
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
    monkeypatch.setenv("CATALOG_ENV", "demo")
    assert auth_bypass_enabled() is True


def test_roles_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
    monkeypatch.setenv("CATALOG_ENV", "development")
    monkeypatch.setenv("CATALOG_AUTH_BYPASS_ROLES", f"{ROLE_EDITOR},{ROLE_ADMIN}")
    session = current_session(_Req(), None)
    assert session is not None
    assert session.roles == [ROLE_EDITOR, ROLE_ADMIN]


def test_unknown_roles_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """存在しないロール名で権限を捏造できないこと。"""
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_AUTH_BYPASS", "true")
    monkeypatch.setenv("CATALOG_ENV", "development")
    monkeypatch.setenv("CATALOG_AUTH_BYPASS_ROLES", "Catalog.SuperUser,root")
    session = current_session(_Req(), None)
    assert session is not None
    assert session.roles == [ROLE_VIEWER]


def test_truthy_variants_do_not_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    """"1" や "yes" では有効化しない（明示的な "true" のみ）。"""
    _clear(monkeypatch)
    monkeypatch.setenv("CATALOG_ENV", "development")
    for value in ("1", "yes", "on", ""):
        monkeypatch.setenv("CATALOG_AUTH_BYPASS", value)
        assert auth_bypass_enabled() is False
