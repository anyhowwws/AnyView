# 0042 — Usage monitoring from log lines

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

With sign-in open to any Google account (ADR 0041), the owner needs to see how
many people signed up, how many interviews ran and how many questions Donna
answered. The database already holds the answers (`users`, `usage_events`),
but reading them means a Cloud SQL connection, and nothing shows a trend.

## Options considered

- **A stats script over the database.** Exact and has all history, but it is
  a command to run, not something to look at.
- **An admin page in the app.** A new route, an admin role, and UI, for one
  reader.
- **Log-based metrics and a Cloud Monitoring dashboard.** The app writes one
  JSON line per activity; Cloud Run stores it as a structured entry; Terraform
  defines metrics that count the entries and a dashboard that charts them. No
  new service, no new dependency, no database access, all in IaC.

## Decision

Log-based metrics (`infra/monitoring.tf`):

- `anyview/activity.py:record(name)` logs `{"activity": "<name>"}` on the
  `anyview.activity` logger. Names: `signup` (the first `ensure_user` for a
  uid, which every screen triggers through `GET /brain`), `interview_started`,
  `interview_completed` (every report item sent), `discover_question`,
  `garden_upload`. An unknown name raises, and a test checks that every name
  has a tile in Terraform.
- `anyview_activity` counts those lines, labelled by activity;
  `anyview_model_calls` counts the existing `anyview.usage` lines by `call`
  and `model`.
- The "AnyView usage" dashboard shows a 7-day total per activity and daily
  bars for activity and model calls. `terraform output usage_dashboard_url`.

Lines carry no email, uid or text: logs outlive an erased account (ADR 0018).

## Consequences

- Metrics start at zero on the day they are created; earlier history stays in
  the database.
- Counts are events, not distinct people: two interviews by one person are two.
  Distinct users per period would need a uid label, which is the identifier the
  rule above keeps out.
- Adding a counter is a `record()` call plus one entry in `local.activities`.
