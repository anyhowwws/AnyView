# 0011 — Cloud SQL access: IAM authentication, one state-free password, enforced event log

- **Status:** Accepted
- **Date:** 2026-09-18
- **Builds on:** 0002 (Postgres + pgvector)

## Context

Phase 1 stores personal career data. ADR 0002 chose Cloud SQL for PostgreSQL;
this record settles how the application reaches it, where the only password
lives, and how the brief's two hard rules — provenance enforced by the
database, and an append-only event log as the sole write path — are made true
by the database rather than by the code.

## Decisions

**IAM database authentication for every real login.** The API logs in as its
service account (`anyview-api@<project>.iam`); the owner logs in from a laptop
as their Google account. The Cloud SQL Python Connector fetches short-lived
tokens; no database password exists for the application anywhere — not in
Secret Manager, not in env, not in state.

**One password, never in state.** Cloud SQL lets only members of
`cloudsqlsuperuser` create extensions, and IAM users are not members. The
built-in `postgres` user is, so it needs a password. Terraform generates it as
an *ephemeral* `random_password` and passes it through *write-only* arguments
to Secret Manager and to the SQL user in the same run; a `db_password_version`
variable controls when it is (re)written. The value is never stored in state or
in any file. It is read exactly once, by the owner running
`backend/scripts/db_bootstrap.py`, which creates the `vector` extension and
makes the API user own the database. Rotation is a version bump and a re-run.

**Connector + psycopg + SQLAlchemy Core as the pool.** The connector supports
psycopg directly; SQLAlchemy's `creator=` is the documented way to pool
connector connections. SQLAlchemy is used **only** as a pool and `text()`
executor — no ORM, no models, no session layer. Pool size 2 with overflow 2:
the instance is db-g1-small and Cloud Run is capped at one instance.

**Migrations as numbered SQL, applied at startup under an advisory lock.**
No Alembic. `backend/migrations/NNN_*.sql`, recorded in `schema_migrations`.
Startup migration is safe with one instance and `pg_advisory_lock` makes it
safe with more.

**The database enforces the brief's invariants.**
- Provenance: every projection row has `raw_dump_id NOT NULL REFERENCES
  raw_dumps` and `event_id NOT NULL REFERENCES events`. A fact without a source
  cannot be inserted.
- Append-only log: a trigger on `events` raises on `UPDATE` and `DELETE`. The
  projection tables are rebuilt from the log by `rebuild(user_id)`, and a test
  asserts incremental apply equals rebuild after every event kind.
- Entity IDs are minted at confirmation and stored in the event payload, so a
  rebuild reproduces the same IDs and nothing that references them breaks.

**Public IP, no authorized networks, TLS required.** Nothing can reach the
instance directly; the connector goes through the admin API. Private IP would
need a VPC connector for Cloud Run — cost and scope for no security gain here.

## What this costs

- **db-g1-small idles at roughly USD 25–30/month**, more than half the budget
  alert on its own. It is what the brief specifies; `db_tier = "db-f1-micro"`
  is the step-down.
- **Two project-level IAM roles** for the API SA (`cloudsql.client`,
  `cloudsql.instanceUser`): Cloud SQL has no per-instance IAM.
- **A one-time owner step** (`db_bootstrap.py`) that cannot be automated
  without giving Terraform superuser access to the database.
- **Ephemeral values need Terraform ≥ 1.11** and the `random` provider ≥ 3.7.
  Both pinned.
- **Startup migrations couple a deploy to a schema change.** Acceptable while
  every migration is additive; a destructive migration would need a separate
  step, and none is planned.
