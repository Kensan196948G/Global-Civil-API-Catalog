from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.models import Base  # noqa: E402

target_metadata = Base.metadata

# Offline mode ("alembic upgrade --sql") renders SQL without connecting, so a
# postgresql dialect placeholder is enough there; online mode requires the
# real URL from the environment (never stored in the repo).
_OFFLINE_URL = "postgresql+psycopg://"


def _database_url() -> str:
    url = os.environ.get("CATALOG_DATABASE_URL", "")
    if not url:
        raise RuntimeError("CATALOG_DATABASE_URL is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=os.environ.get("CATALOG_DATABASE_URL", _OFFLINE_URL),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
