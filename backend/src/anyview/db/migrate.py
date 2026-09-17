"""Apply `backend/migrations/NNN_*.sql` in order (ADR 0011).

Each file runs once, inside a transaction, and is recorded in
`schema_migrations`. A Postgres advisory lock serialises concurrent starters.
Runs at app startup and as `python -m anyview.db.migrate`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import sqlalchemy
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
LOCK_KEY = 7_140_926  # arbitrary, fixed: "the anyview migrations lock"


def pending(engine: Engine) -> list[Path]:
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
            )
        )
        done = {r[0] for r in conn.execute(sqlalchemy.text("SELECT name FROM schema_migrations"))}
    return [p for p in sorted(MIGRATIONS_DIR.glob("*.sql")) if p.name not in done]


def migrate(engine: Engine) -> list[str]:
    """Apply everything pending; return the names applied."""
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
        done = {r[0] for r in conn.execute(sqlalchemy.text("SELECT name FROM schema_migrations"))}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            log.info("applying migration %s", path.name)
            # exec_driver_sql runs the file as-is: many statements, $$ bodies,
            # and no :param parsing.
            conn.exec_driver_sql(path.read_text())
            conn.execute(
                sqlalchemy.text("INSERT INTO schema_migrations (name) VALUES (:n)"),
                {"n": path.name},
            )
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    from anyview.config import Settings
    from anyview.db.connection import make_engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = make_engine(Settings.from_env())
    if engine is None:
        sys.exit("no database configured (set DB_INSTANCE or DATABASE_URL)")
    names = migrate(engine)
    print("applied:", names or "nothing (up to date)")
