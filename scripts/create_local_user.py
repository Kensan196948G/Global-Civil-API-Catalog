"""Create or update a local login account (auth mode ``local``).

Usage:
    CATALOG_DATABASE_URL=... python scripts/create_local_user.py \
        --username admin --role Catalog.Admin [--display-name 管理者] [--inactive]

The password is read interactively (getpass, asked twice) or from
CATALOG_USER_PASSWORD for scripted setups; it is never echoed, logged or
stored anywhere except as an scrypt hash in the local_users table.
Existing accounts are updated in place (password/role/display/active) and
any pending lockout is cleared, so this doubles as the reset tool.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.models import LocalUser  # noqa: E402
from db.session import make_session_factory  # noqa: E402
from web.auth import (  # noqa: E402
    ALL_ROLES,
    MIN_PASSWORD_LENGTH,
    hash_password,
    revoke_user_sessions,
)


def read_password() -> str:
    password = os.environ.get("CATALOG_USER_PASSWORD", "")
    if not password:
        password = getpass.getpass("パスワード: ")
        confirm = getpass.getpass("パスワード(確認): ")
        if password != confirm:
            print("エラー: パスワードが一致しません", file=sys.stderr)
            raise SystemExit(2)
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"エラー: パスワードは{MIN_PASSWORD_LENGTH}文字以上にしてください",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update a local login account")
    parser.add_argument("--username", required=True, help="login name (stored lowercase)")
    parser.add_argument("--role", required=True, choices=ALL_ROLES)
    parser.add_argument("--display-name", default="", help="name shown in the UI")
    parser.add_argument("--inactive", action="store_true", help="disable the account")
    args = parser.parse_args(argv)

    username = args.username.strip().lower()
    if not username:
        print("エラー: --username が空です", file=sys.stderr)
        return 2
    password_hash = hash_password(read_password())

    factory = make_session_factory()
    with factory() as db:
        user = db.get(LocalUser, username)
        created = user is None
        if user is None:
            user = LocalUser(username=username)
            db.add(user)
        user.password_hash = password_hash
        user.role = args.role
        user.display_name = args.display_name or username
        user.is_active = not args.inactive
        user.failed_attempts = 0
        user.locked_until = None
        db.commit()
        # A role/status change must take effect immediately: existing login
        # sessions are revoked so the next request re-authenticates (issue #61).
        revoked = revoke_user_sessions(db, f"local:{username}")

    action = "created" if created else "updated"
    print(
        f"OK: {action} local user '{username}' (role={args.role}, "
        f"active={not args.inactive}, revoked_sessions={revoked})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
