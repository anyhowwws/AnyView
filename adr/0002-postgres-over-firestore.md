# 0002 — Cloud SQL for PostgreSQL over Firestore

- **Status:** Accepted
- **Date:** 2026-09-16

## Context

The brain is a set of related entities — Role, Project (belongs to a Role),
Story (tagged to competencies), Skill (evidence links to Projects),
Achievement, RawDump — with two hard requirements:

- **Provenance enforced by the database.** Every extracted fact points at the
  raw dump it came from, and that pointer must be a real foreign key, not a
  convention the application promises to follow.
- **Hybrid retrieval in one query.** Structured filters first (competency tag,
  entity type, date range, employer), then vector similarity over what remains.

Two GCP-native datastores were considered.

## Options considered

**Firestore.** Serverless, scales to zero, no instance cost, and has vector
search built in. But:

- Firestore's vector `find_nearest` supports pre-filtering only with equality
  filters. **Inequality filters (date ranges) are not supported as
  pre-filters**, so "stories from the last three years about ambiguity, nearest
  to this question" cannot be expressed as one query. It becomes over-fetch and
  filter in Python, which is exactly the shape that gets slow and wrong.
- No foreign keys. Provenance would be a document reference the application
  has to keep honest.
- The entity graph (Role → Project → Story, Skill → evidence Projects) either
  denormalises into duplicated data or turns into N+1 reads. The
  join/denormalisation cost is paid on every feature.

**Cloud SQL for PostgreSQL + pgvector.** Relational, foreign keys, one SQL
statement for filter-then-similarity. Costs money while idle and needs a
connection strategy from Cloud Run.

## Decision

Cloud SQL for PostgreSQL, smallest tier (db-g1-small), single zone, no HA, with
the `pgvector` extension in the same database. Accessed from Cloud Run through
the Cloud SQL Python connector with a deliberately small connection pool.

All database access goes through one repository module with app-meaningful
methods (`stories_for_competency`, `roles_for_user`, `search_brain`), not a
generic query interface.

## What this costs

- **An idle bill.** Roughly the price of a small VM per month whether or not
  anyone practises an interview. Budget alert at USD 50 catches drift.
- **Connections are a scarce resource.** db-g1-small allows few concurrent
  connections. Cloud Run instances × pool size must stay under that; the pool
  is small on purpose and the instance count is capped in Terraform.
- **Schema migrations are a thing.** Firestore would have let the shape drift;
  Postgres makes it explicit. This is a cost worth paying for provenance.
- **Migration direction.** If this turns out wrong, Postgres → Firestore is the
  cheap direction (relational data denormalises easily; the reverse — inferring
  a schema from documents — is not). Choosing Postgres first keeps the exit
  cheap.
