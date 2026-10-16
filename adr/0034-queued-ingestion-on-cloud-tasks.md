# 0034 — Ingestion runs as a queued job: Cloud Tasks and a private worker

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0019 (how its progress frames reach the browser; the frames themselves stand)

## Context

Reading a resume into a proposal is 4 + *n* model calls and about 90 seconds
(ADR 0019). Until now all of it ran inside one HTTP request.
`POST /brain/dumps/from-upload/stream` started the pipeline on a thread in the
API and streamed `progress` frames back over SSE (ADR 0005) until the
proposal arrived.

That works, but only while nothing goes wrong:

- **The work only lives as long as the connection.** Reloading the page,
  closing the laptop lid, or a network change mid-upload drops the stream. The
  pipeline either dies with it or finishes unseen, and the browser can't find
  out which. The user uploads again and pays for the model calls twice.
- **The work only lives as long as the instance.** A deploy, or Cloud Run
  replacing the instance (ADR 0023 counts these as routine), kills the
  request. Nothing retries it.
- **A model hiccup fails the whole upload.** A 429 or 503 from Agent Platform partway
  through ends the stream with an error frame. There is no backoff and no
  second try.
- **It competes with the interview.** The API runs on one instance (ADR 0023,
  `max_instance_count = 1`), and a resume's parallel extraction shares it with
  whoever is mid-interview on Live.

ADR 0023's warm instance made the request path *reliable enough*. This record
moves ingestion off the request path, so it no longer depends on the request
lasting.

## Options considered

**Keep SSE; make it resumable.** Store the frames in a table and let the
browser reconnect to a stream that replays them. That fixes the reload, but
the work still runs on a thread in the API instance. A deploy still kills it,
and nothing retries it.

**A background thread after the response.** Answer at once and keep
working. On Cloud Run with `cpu_idle = true`, CPU outside a request is
throttled to almost nothing. Turning that off bills the instance all the
time. Either way, a replaced instance loses the work silently.

**Pub/Sub push to a worker.** Also at-least-once with retries. But it is a
fan-out bus, and this is a work queue with one consumer. Cloud Tasks has the
controls a work queue needs and Pub/Sub lacks: named tasks for dedupe,
per-task dispatch deadlines, and rate and concurrency limits on the queue.

**Cloud Run Jobs.** Built for batch work with no HTTP. Starting one execution
per resume means a container start every time (the ~55 s boot in ADR 0023)
and a heavier API to pass arguments through. Progress would still need a
table.

**Cloud Tasks → a worker service, progress in a table, the browser polls.**
The API writes a job row, enqueues a task named after the job, and answers
`202`. Cloud Tasks delivers it to the worker with an OIDC token and retries
with backoff until the worker answers 2xx. The worker writes each progress
frame into the row. The browser polls `GET /brain/jobs/{id}`. A reload,
another tab or another API instance reads the same row.

On where the worker runs, two shapes were considered. **A route on the
public API** verifies the Cloud Tasks token in code (the API is `allUsers`,
ADR 0009) and shares the one instance with interviews. **A second, private
Cloud Run service** is called only by Cloud Tasks, guarded by Cloud Run's own
IAM check before any code runs, and scales on its own.

## Decision

**Cloud Tasks, a private worker service, a job table, and polling.**

```
browser ─POST /brain/jobs─▶ anyview-api ─create task─▶ Cloud Tasks (anyview-ingest)
browser ◀─GET /brain/jobs/{id}── anyview-api                │ OIDC token as anyview-tasks
                 ▲                                          ▼
                 └──────── ingest_jobs (Cloud SQL) ◀── anyview-worker (private)
```

- **The queue** (`infra/ingest.tf`) has 5 attempts with backoff of 15 s,
  30 s, 60 s and 120 s, and at most 2 dispatches in flight. Every dispatch is
  logged. Each task is named after its job, so enqueueing the same job twice
  is refused by Cloud Tasks (`ALREADY_EXISTS`), not run twice.
- **The worker** (`anyview-worker`) is the API's image started with
  `APP_MODULE=anyview.worker:app`. It has one route, `POST /tasks/ingest`. It
  sits behind two locks. Ingress is internal-only, so only callers inside
  Google Cloud in this project (Cloud Tasks is one) reach it. Of those, only
  the `anyview-tasks` service account holds `run.invoker`. It scales from zero
  to one: a queued job can wait out a cold start, which the API's first screen
  could not (ADR 0023).
- **The worker runs as the API's service account.** It needs exactly the
  API's data access: Agent Platform, the uploads bucket, and the same Cloud SQL IAM
  user. A separate runtime account would be a second database user with the
  same grants, with no reduction in what either can reach. The *invoker*
  identity is separate: `anyview-tasks` can call the worker and nothing else.
- **The API** creates tasks on that one queue (`cloudtasks.enqueuer` on the
  queue) and may act as `anyview-tasks` (`serviceAccountUser` on that one
  account), which Cloud Tasks requires before it attaches a token for it.
  Cloud Tasks is called over REST with `google-auth`'s authorised session,
  which is already installed. The `google-cloud-tasks` client would add a
  gRPC stack to an image whose boot time is already the open question in
  ADR 0023, all for one POST.
- **The job table** (`ingest_jobs`, migration 009) is a plain table, not
  event-sourced, like `saved_jobs` (ADR 0025). A job is machinery. The dump
  and the proposal it produces are recorded where they always were. It is in
  `ERASE_ORDER` (ADR 0018).
- **Status codes are the contract with Cloud Tasks.** `204`: done, failed for
  good (bad input, nothing found), or already finished. `503`: a retryable
  failure, so try again later. `409`: another delivery holds the job. On the
  queue's last attempt (`X-CloudTasks-TaskRetryCount` + 1 =
  `INGEST_MAX_ATTEMPTS`, set from the same Terraform variable as the queue)
  the worker fails the job rather than ask for a retry nobody will send.
- **At-least-once delivery is handled by a lease.** A delivery *claims* the
  row: `queued → running` in one `UPDATE … WHERE`. Each progress frame bumps
  `updated_at`, which acts as a heartbeat. A second delivery that arrives
  while the first is alive gets `409`. A delivery whose heartbeat is older
  than 120 s is presumed dead and can be taken over. The backoff schedule adds
  up to more than the lease, so a later retry always gets there.
- **A retry does not repeat paid work.** The row keeps `raw_dump_id` once the
  text is read, so a second attempt does not transcribe the PDF again.
- **The browser** polls every 1.5 s and rebuilds the progress view from all
  the frames so far, so a retry that starts over simply redraws. On mount, the
  capture box asks for running jobs (`GET /brain/jobs`) and follows the newest
  one. A job with no heartbeat for 15 minutes reads as failed, so nothing
  spins for ever.
- **Locally and in tests** (`TASKS_QUEUE` unset) an `InlineQueue` runs the job
  in the API process. The polling path is the same; only the delivery
  differs.

The synchronous `POST /brain/dumps` and `/brain/dumps/from-upload` stay for
scripts and tests; the browser no longer calls them. The two `/stream` routes
are gone.

## What this costs

- **More moving parts.** A queue, a second Cloud Run service, a third service
  account, a table, and a second deploy target in CI. Each is small. Together
  they are more to understand than "the request does the work".
- **Progress is up to 1.5 s late,** and costs a cheap indexed read every
  1.5 s while a job runs. Per-section progress moved at that pace anyway.
- **A cold worker adds a wait.** The first job after an idle spell waits
  for the worker to boot (about a minute, ADR 0023). The progress view shows
  it as the "Queue" step rather than hiding it. A minimum instance would
  remove the wait for about USD 10 a month. Not worth it yet.
- **Two pools to Cloud SQL.** The worker's small pool adds up to 4
  connections, well inside db-g1-small's limit.
- **Deploy order matters.** CI deploys the worker before the API, because
  the API queues work for it. Both services run the migrations at startup
  (under the advisory lock, ADR 0011), and a deploy starts the new revision
  once, so the table exists before the new API needs it.
- **Ingress needs checking on the first real run.** Cloud Run treats Cloud
  Tasks as an internal source for `INGRESS_TRAFFIC_INTERNAL_ONLY`. If the first
  real delivery is refused at ingress (a 403/404 in the queue's dispatch logs
  with no request in the worker's logs), drop the ingress to `ALL`. IAM alone
  still keeps everyone else out.
- **A queue name is reserved for about a week after deletion,** so
  `anyview-ingest` is renamed, never destroyed and recreated.
