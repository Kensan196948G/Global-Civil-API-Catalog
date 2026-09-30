"""Engine/session factory.

The connection URL is taken exclusively from the CATALOG_DATABASE_URL
environment variable (secret management per CLAUDE.md §5/§13 — never
hard-code or log connection strings).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

ENV_VAR = "CATALOG_DATABASE_URL"
CONNECT_TIMEOUT_ENV = "CATALOG_DB_CONNECT_TIMEOUT"

# Seconds to wait for the TCP/auth handshake before giving up. Without this,
# psycopg/libpq uses the OS default (~2 minutes per address, and it retries
# every resolved address). A health probe against a dead database therefore
# *hung* instead of reporting failure — which is just as bad as the old
# always-200 behaviour, because monitoring times out and tells the operator
# nothing. 5s is comfortably above a healthy local/LAN connect.
DEFAULT_CONNECT_TIMEOUT = 5

# libpq parameter that carries the timeout. It must travel in the URL query
# string: the psycopg3 dialect discards `connect_args={"connect_timeout": ...}`
# when it builds the libpq keyword dict, so the connect_args spelling is
# silently ignored (verified against SQLAlchemy 2.0 + psycopg 3).
_TIMEOUT_PARAM = "connect_timeout"


def _connect_timeout() -> int:
    raw = os.environ.get(CONNECT_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_CONNECT_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CONNECT_TIMEOUT
    return value if value > 0 else DEFAULT_CONNECT_TIMEOUT


def database_url() -> str:
    url = os.environ.get(ENV_VAR, "")
    if not url:
        raise RuntimeError(f"{ENV_VAR} is not set; refusing to guess a database location")
    return url


def make_engine(url: str | None = None) -> Engine:
    parsed = make_url(url or database_url())
    # An explicit connect_timeout already in the URL always wins.
    if _TIMEOUT_PARAM not in parsed.query:
        parsed = parsed.update_query_dict({_TIMEOUT_PARAM: str(_connect_timeout())})
    return create_engine(parsed, pool_pre_ping=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)
