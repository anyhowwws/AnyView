# 0047 — A daily limit per user: ten interviews and ten uploads

- **Status:** Accepted
- **Date:** 2026-10-18
- **Amends:** 0041 (open sign-in now has a spending limit)

## Context

Since ADR 0041 any verified Google account can sign in. The two expensive things a user can do
are starting an interview (planning on Gemini 3.1 Pro, then five `score` and five `ideal` calls
for the report) and handing Donna a document or a note to read (4 + *n* calls, mostly Pro, ADR
0019). ADR 0042 made usage visible (a dashboard and an email per sign-up), but only after the
fact: one account in a loop could spend the month's budget before anyone saw the chart.

The upload path had a second gap. `POST /uploads` refused a declared size over 10 MB, but the
signed URL did not bind the size, so a browser that lied about `size_bytes` could put any object
in the bucket, and the API or the worker would then read all of it into memory.

## Options considered

- **One shared budget** (ten interviews *or* uploads a day). Simpler, but a new user's first day
  is several uploads (resume, feedback, notes) before the first interview.
- **Every model call, Discover included.** Discover runs on the fast model and costs little; a
  limit of ten questions would stop the feature being useful.
- **Cloud Armor or API Gateway rate limits.** They limit requests per IP, not per account, and
  one interview is a handful of requests spread over twenty minutes.
- **Ten interviews and ten uploads per user per UTC day, counted separately** (chosen).

## Decision

- A `daily_usage` table (user, UTC day, action, count) and `Repository.take_daily`: one
  `INSERT … ON CONFLICT DO UPDATE … WHERE count < limit RETURNING`, so the count never passes the
  limit even when two requests arrive together.
- `api/limits.py:daily()` wraps `POST /interview/start`, `POST /brain/jobs` and the synchronous
  `/brain/dumps` routes. At the limit the route answers **429** with a sentence saying so and when
  it resets (midnight UTC). The browser already shows a route's `detail` and does not retry a POST.
- **A failed attempt is given back.** If the work raises before it is done (no resume on file,
  planning fails, the job cannot be queued), the slot is returned. A job that was queued counts,
  whatever happens to it on the worker: the model calls were made.
- Entries typed into a form (ADR 0022), edits, Discover and the report are not counted: they make
  no Pro calls, or belong to an interview already counted.
- Without a database (a laptop run with no `DATABASE_URL`) there is nothing to count, and no limit.
- **Upload size.** The signed PUT URL now signs `x-goog-content-length-range: 0,10485760`, so Cloud
  Storage refuses a larger body. The ticket returns the header as `upload_headers` for the browser
  to send, and the bucket's CORS rule allows it. Every read also checks the object's size from its
  metadata before downloading it (`UploadTooLarge` → 413), which covers URLs signed before this
  change and any other way an object could arrive.

## Consequences

- One account can start at most ten interviews and ten readings a day. At roughly ten Pro calls
  each, that bounds a single account's daily model spend.
- Erasing an account (ADR 0018) deletes its counter with everything else, so erase-and-return
  resets the day. Accepted: erasing also deletes the garden, which is the thing worth keeping.
- The limit is a constant (`DAILY_LIMIT`), not a setting. Changing it is a one-line change and a
  deploy, which is the right amount of friction for a spending control.
- The size header must be sent exactly as signed. A client that drops it gets a 403 from Cloud
  Storage, which `putTicket` reports as "The upload was rejected".
