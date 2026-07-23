"""Engine/session factory.

The connection URL is taken exclusively from the CATALOG_DATABASE_URL
environment variable (secret management per CLAUDE.md §5/§13 — never
hard-code or log connection strings).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

ENV_VAR = "CATALOG_DATABASE_URL"


def database_url() -> str:
    url = os.environ.get(ENV_VAR, "")
    if not url:
        raise RuntimeError(f"{ENV_VAR} is not set; refusing to guess a database location")
    return url


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)
