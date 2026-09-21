"""One-time database bootstrap (ADR 0011). Run by the owner after `terraform apply`:

    cd backend && GOOGLE_CLOUD_PROJECT=anyapps-anyview .venv/bin/python scripts/db_bootstrap.py

What it does, as the built-in `postgres` user (the only role Cloud SQL lets
create extensions):
  1. CREATE EXTENSION vector            — pgvector, ready for Phase 2
  2. make the API's IAM user own the database and the public schema, so the
     migrations it runs at startup own their tables
  3. let the owner's IAM user act as the API user (same privileges) for local
     migrations, tests and break-glass

The postgres password is read from Secret Manager with your ADC. Nothing is
written to disk. Safe to run again: every statement is idempotent.
"""

from __future__ import annotations

import os
import sys

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud.sql.connector import Connector

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or sys.exit("set GOOGLE_CLOUD_PROJECT")
REGION = os.environ.get("DB_REGION", "us-central1")
INSTANCE = os.environ.get("DB_INSTANCE", f"{PROJECT}:{REGION}:anyview-pg")
DB = os.environ.get("DB_NAME", "anyview")
API_USER = os.environ.get("DB_IAM_USER", f"anyview-api@{PROJECT}.iam")
OWNER_USER = os.environ.get("DB_OWNER_IAM_USER") or sys.exit(
    "set DB_OWNER_IAM_USER (your Google account)"
)
SECRET = os.environ.get("DB_PASSWORD_SECRET", "anyview-postgres-password")


def postgres_password() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(creds)
    url = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{SECRET}/versions/latest:access"
    r = session.get(url, headers={"x-goog-user-project": PROJECT})
    r.raise_for_status()
    import base64

    return base64.b64decode(r.json()["payload"]["data"]).decode()


def quoted(ident: str) -> str:
    # Double-quote an identifier (IAM user names contain @ and .).
    return '"' + ident.replace('"', '""') + '"'


def main() -> None:
    api, owner = quoted(API_USER), quoted(OWNER_USER)
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        # Postgres requires the granting role to already hold membership in a
        # role before it can transfer ownership to it (ALTER ... OWNER TO
        # checks SET-role privilege, not just superuser status). `postgres`
        # is a member of cloudsqlsuperuser, which can self-grant IAM roles —
        # this is Cloud SQL's documented pattern for handing IAM users
        # ownership. Without this line, the ALTER statements below fail with
        # "must be able to SET ROLE".
        f"GRANT {api} TO postgres",
        f"ALTER DATABASE {quoted(DB)} OWNER TO {api}",
        f"ALTER SCHEMA public OWNER TO {api}",
        f"GRANT ALL ON SCHEMA public TO {api}",
        # Schema ownership only covers CREATE/USAGE on the schema itself — it
        # does not retroactively grant privileges on tables that already
        # exist inside it (e.g. created by a manual break-glass migration run
        # as the owner IAM user before this script's first run, which is
        # exactly what happened in production: every brain table ended up
        # owned by the owner, and the API got "permission denied" on its own
        # tables). Without these, that gap resurfaces any time a table gets
        # created by a role other than the API's own. Idempotent and safe to
        # re-run after every migration that adds a table.
        f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {api}",
        f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {api}",
        f"GRANT {api} TO {owner}",
    ]
    with Connector() as connector:
        conn = connector.connect(
            INSTANCE, "psycopg", user="postgres", password=postgres_password(), db=DB
        )
        try:
            with conn, conn.cursor() as cur:
                for sql in statements:
                    cur.execute(sql)
                    print("ok  ", sql)
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                print("pgvector", cur.fetchone()[0])
                cur.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (DB,)
                )
                print("database owner:", cur.fetchone()[0])
        finally:
            conn.close()


if __name__ == "__main__":
    main()
