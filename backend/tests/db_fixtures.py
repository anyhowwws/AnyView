"""A real Postgres for repository and brain-API tests.

Set TEST_DATABASE_URL (default: a local `anyview_test` database on the
Homebrew Postgres). Tests that need it skip with a clear reason when it is
unreachable, so the rest of the suite still runs without Postgres.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy

from anyview.db.migrate import migrate

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost/anyview_test"
)

ALL_TABLES = [
    "skill_evidence", "skills", "achievements", "stories", "projects", "roles",
    "events", "proposals", "raw_dumps", "usage_events", "users",
]  # fmt: skip


@pytest.fixture(scope="session")
def db_engine():
    engine = sqlalchemy.create_engine(TEST_DATABASE_URL, pool_size=2, max_overflow=2)
    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no test database"
        pytest.skip(f"no test database at {TEST_DATABASE_URL}: {exc.__class__.__name__}")
    # Start from a clean schema every session so migrations are exercised.
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    migrate(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """A clean database for one test. TRUNCATE is table-level and allowed on
    events (the append-only trigger guards rows); the app never does this."""
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE"))
    return db_engine
