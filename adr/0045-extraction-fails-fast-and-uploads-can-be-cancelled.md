# 0045 — Extraction fails fast and falls back; an upload can be cancelled

- **Status:** Accepted
- **Date:** 2026-10-18
- **Extends:** 0039 (the same fail-fast fallback, now for extraction), 0034 (a job gains a way out)

## Context

On 2026-10-17 a feedback upload sat in "Donna is reading…" for over eight minutes. The worker's
logs showed no hang: one `gemini-3.1-pro-preview` call returned `504 DEADLINE_EXCEEDED` after about
two minutes, three times in a row, then a fourth. Extraction used the client's defaults (120 s,
4 attempts), so one stuck call held the upload for ~8 minutes, and then the job asked Cloud Tasks
for another delivery, which could do it all again (up to 5 deliveries). ADR 0039 had fixed exactly
this for the report and left extraction alone.

The user also had no way to stop it. The job carried on in the worker, and the only thing a user
could do was wait or reload.

## Decision

**Extraction's model calls fail fast and fall back** (`fallback=True`, as in ADR 0039):

- `propose` and `link` get `deadline_ms=EXTRACT_DEADLINE_MS` (120 s): **one** try that long on the
  judgement model, then one try on `gemini-3.8-flash` at `low` effort.
- `dedupe` gets the report's tighter 75 s x 2, because it is a short, optional step.
- The deadline is longer than the report's 75 s because extraction reads whole documents. Of 30
  real `propose` calls, p95 was 79 s and the slowest 112 s, so 75 s would have cut off good calls.
  It is one try, not two, because Agent Platform gives up on a stuck call at ~115 s: a retry on
  the same model spends another two minutes on the same answer.
- Worst case for one call: about 3 minutes, not 8.

**A queued or running upload can be cancelled** (`POST /brain/jobs/{id}/cancel`, a Cancel button
beside "Donna is reading…"):

- Cancelling marks the job `failed` with `error = "Cancelled."` and `error_status = 499`. No new
  status and no migration: a cancelled job is a job that ended, and 499 tells the browser it was
  the user's choice, so it shows a neutral "Cancelled. Nothing was added to your garden." and keeps
  what was typed.
- The worker stops cooperatively. Every progress frame is also the cancel check
  (`report_job_progress` returns False once the job is not `running`), and `finish_job` only lands
  on a running job; if the cancel arrived during the last step, the proposal that was just built is
  discarded. A Cloud Tasks redelivery finds a finished job and does nothing (`gone`, 204).
- `requeue_job` and `fail_job` no longer touch a job that already ended, so a late retry handler
  cannot revive a cancelled job or overwrite "Cancelled." with an error.

## Consequences

- When Pro is healthy, nothing changes. When it is struggling, an upload finishes in minutes with
  some sections read by Flash at `low` effort, which may find fewer entries on a dense document.
  The review queue does not say which model read a section (the same trade-off as 0039's ideal
  answers). If that matters, `extraction_recall.py --expect` on a known document is the check.
- **Cancel is not instant for the worker.** A model call already in flight runs to its end (at most
  about two minutes) before the worker notices. The user sees the cancel at once, because the job
  row is already failed; only the spend is not recovered.
- A cancelled upload keeps its `raw_dumps` row if the text was already read (the dump is the
  provenance record and a retry reuses it). It never produces a proposal.
- Only a job that is `queued` or `running` can be cancelled; there is no undo.
