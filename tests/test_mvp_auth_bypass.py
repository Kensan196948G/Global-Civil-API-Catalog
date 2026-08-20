"""MVP 公開デモ用のログイン認証バイパス（CATALOG_AUTH_BYPASS）。

DB を必要としない範囲で、有効化条件と付与ロールを固定する。
- 既定は無効（未ログインは従来どおり None）
- CATALOG_ENV=production では設定値によらず必ず無効（安全装置）
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
