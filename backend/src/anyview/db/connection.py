"""How the app reaches Postgres (ADR 0011).

Two ways to get an engine, chosen by configuration:

  - `DB_INSTANCE` set (Cloud Run, or a laptop pointed at Cloud SQL): the Cloud
    SQL Python Connector opens IAM-authenticated, TLS connections as
    `DB_IAM_USER`. No password anywhere.
  - `DATABASE_URL` set (tests, a local Postgres): a plain postgres:// URL.

SQLAlchemy is used *only* as the connection pool and to run `text()` SQL — no
ORM. The pool is deliberately small: db-g1-small allows few connections and
Cloud Run runs one instance.
"""

from __future__ import annotations

import logging

import sqlalchemy
from sqlalchemy.engine import Engine

from anyview.config import Settings

log = logging.getLogger(__name__)


def make_engine(settings: Settings) -> Engine | None:
    """An engine, or None when no database is configured (the API then serves
    Phase 0 routes only and /brain returns 503)."""
    if settings.database_url:
        return sqlalchemy.create_engine(
            settings.database_url, pool_size=2, max_overflow=2, pool_pre_ping=True
        )
    if not settings.db_instance:
        return None

    # Imported here so importing the app never touches GCP.
    from google.cloud.sql.connector import Connector

    connector = Connector(enable_iam_auth=True)

    def connect():
        return connector.connect(
            settings.db_instance, "psycopg", user=settings.db_iam_user, db=settings.db_name
        )

    # The URL carries no host or credentials: `creator` supplies every connection.
    return sqlalchemy.create_engine(
        "postgresql+psycopg://",
        creator=connect,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=1800,  # IAM tokens last an hour; recycle well inside that
    )
