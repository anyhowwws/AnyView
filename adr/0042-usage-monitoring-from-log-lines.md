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

A log-match alert policy emails `alert_emails` (GitHub secret
`TF_ALERT_EMAILS`, a JSON list) on each `signup` line, at most one email per
5 minutes (the shortest rate limit Cloud Monitoring allows); an empty list
creates no channel and no policy. The email says that someone signed up, not
who: the identity is in the Identity Platform users list.

Lines carry no email, uid or text: logs outlive an erased account (ADR 0018).

Personal values reach Terraform from GitHub **secrets**, not variables:
`TF_BILLING_ACCOUNT_ID`, `TF_DB_OWNER_IAM_USER`, `TF_ALLOWED_EMAILS`,
`TF_ALERT_EMAILS`. A step's log prints its environment, a public repository's
logs are public, and a secret prints as `***`. `ci.yml` falls back to the old
variable while a secret is missing, so the switch can happen in any order.
The Terraform variables holding them are `sensitive`, which keeps them out of
the plan CI posts on a PR.

The privacy page says what is counted, that counts identify nobody, and that
the owner is emailed when someone new signs up, without the address.

## Consequences

- Metrics start at zero on the day they are created; earlier history stays in
  the database.
- Counts are events, not distinct people: two interviews by one person are two.
  Distinct users per period would need a uid label, which is the identifier the
  rule above keeps out.
- To see *who* signed up, read the Identity Platform users list in the
  console. It is the list an erasure updates, unlike an inbox.
- Adding a counter is a `record()` call plus one entry in `local.activities`.
