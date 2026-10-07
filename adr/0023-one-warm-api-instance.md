# 0023 — One warm API instance instead of scaling to zero

- **Status:** Accepted
- **Date:** 2026-10-08
- **Amends:** 0001 ("Cold starts" under *What this costs*)

## Context

ADR 0001 accepted cold starts: "min-instances stays at zero until it hurts".
It hurts now.

The Digital Garden screen started showing "Can't reach the server" every so
often, and "Retry loading Garden" did not clear it. The Cloud Run logs for
2026-10-07 12:00 UTC show what happens:

| Time (UTC) | Event |
|---|---|
| 12:00:06 | `Starting new instance` (scale from zero) |
| 12:00:06, 12:00:30 | `GET /brain`, `/brain/proposals` → **500** in 0 s: *"The request was aborted because there was no available instance"* |
| 12:01:01 | `Started server process` (~55 s after the instance was scheduled) |
| 12:01:12 | `Application startup complete` (Cloud SQL connect + migrations, ~11 s) |
| 12:01:13 | `/brain/proposals` → 200 |

So a cold start took about 66 s, and for that whole time Cloud Run did not
queue the garden's requests: it refused them at once. With
`max_instance_count = 1` there was nowhere else for them to go. The refusal
carries no CORS headers, so the browser reports a network error, which is why
the screen says the server is unreachable. Every retry inside that minute
failed the same way. There were 29 cold starts in the week before this
record, so this was routine, not rare.

Scale-to-zero was fine for a practice tool used in occasional bursts. It is
not fine for an app whose first screen loads from the API: a user who opens
the garden after a quiet hour should not be told to try again later.

## Options considered

**Keep scale-to-zero; retry in the browser.** GET requests now retry with
backoff for about 75 s (`frontend/lib/api.ts`), so a cold start reads as a
slow load, not an error. That stays as a safety net, but on its own it means
a minute's wait after every idle period. It hides the problem without fixing it.

**Startup CPU boost alone.** Cloud Run gives the container extra CPU while it
starts, at almost no cost. It shortens the import and migration part of the
boot. It does nothing about the time before the process starts, and it leaves
a cold start on the first request after idle.

**`max_instance_count = 2`.** Lets a second instance take traffic while one
is replaced. It does not help scale-from-zero, where no instance exists to
take anything, and it doubles the Cloud SQL connection ceiling ADR 0011 sized
for one instance.

**One minimum instance, plus startup CPU boost.** There is always a booted
instance, so the scale-from-zero case disappears. The boost shortens the
remaining boots: deploys, and the times Cloud Run replaces an instance.

## Decision

**`min_instance_count = 1` and `startup_cpu_boost = true` on the API service.**
`max_instance_count` stays at 1. `cpu_idle` stays `true`: the warm instance's
CPU is throttled and billed at the idle rate between requests.

The browser's GET retry stays. It covers what a warm instance does not:
deploys, instance replacement, and a 5xx from a transient fault.

## What this costs

- **A floor on the bill.** One idle 1 vCPU / 512 MiB instance, all month,
  at Cloud Run's idle (throttled) rates is in the order of USD 10 a month in
  us-central1, before the free tier. Together with the Cloud SQL floor (ADR
  0001) that is most of the monthly spend at this traffic. The USD 50 budget
  alert still applies.
- **The app now costs money while nobody uses it.** That was already true of
  Cloud SQL. Going back to zero is one line in `infra/cloud_run.tf`, if the
  project ever goes dormant.
- **A held Cloud SQL connection.** The warm instance keeps its small pool
  (ADR 0011) open, so one or two connections are always in use. db-g1-small
  has plenty of room.
- **Boot time itself is not fixed.** The ~55 s before the process starts is
  unexplained (image size and pull, or import cost). It now affects deploys and
  replacements only. It is worth looking into, but this record does not
  depend on it.
