# 0039 — The report fails fast and falls back; transcription moves to the fast model

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amends:** 0007 (judgement calls stay on Pro, but the report no longer waits on it indefinitely)

## Context

On 2026-10-15 a report took over eight minutes, and Donna's spoken questions felt slow. The
logs (`anyview.usage` and Cloud Run) showed the same cause for both: `gemini-3.1-pro-preview`,
a preview build on shared global capacity, was throttling.

- The report fires ten Pro calls at once (a score and an ideal answer for each of five
  questions). 13 of them got `429 Too Many Requests` in the first 12 s (5 the day before,
  none the day before that). Three then got `504 DEADLINE_EXCEEDED` after about two minutes.
- The SDK client used a 120 s timeout and 4 attempts, so one stuck call kept retrying for up to
  eight minutes, and the report waits for all ten.
- Spoken questions to Donna are transcribed first, and `audio_to_text` used the judgement model.
  It took 4-10 s normally and 17-51 s on the slow ones, for a dozen words, while Donna's own
  answer (Flash-Lite) took 1-3 s.

## Decision

**The report's calls fail fast and fall back.** `generate(..., fallback=True)`, used for `score`
and `ideal` and nothing else:

1. On the judgement model, one request gets 75 s (`TIGHT_TIMEOUT_MS`; healthy calls take 15-55 s)
   and `TIGHT_ATTEMPTS` = 2, so a throttled call retries once, quickly.
2. If that fails in a way retrying can fix (429, 5xx, timeout), the call goes once to
   `gemini-3.8-flash` (`FALLBACK_MODEL_ID`) **at `low` effort**. A bad request is not retried
   anywhere.
3. If the fallback fails too, the error is the caller's, as before.

The worst case is about three and a half minutes, not eight or more. The usage row names the
model that actually answered, and a warning logs each fallback.

**Why `low`:** measured on the real scoring prompt, `gemini-3.8-flash` takes 5-10 s at `low` (no
thinking) and 37-69 s at `medium` or `high` (5-9k thinking tokens), for the same four scores. A
fallback as slow as the model it replaces is no fallback.

**Transcription runs on the fast model** (`fast=True`). On five synthetic spoken sentences, Pro
averaged 16 s (up to 38 s) against 2.3 s for Flash-Lite. Word error rates were close (0.05 against
0.08): the differences were numbers written as digits or words, and Flash-Lite split
"Databricks" and wrote "meantime". Transcription is mechanical, and this takes a call off the
Pro capacity that scoring depends on.

**A client timeout is now a retryable `ModelError`.** `httpx.TimeoutException` used to fall
through `_translate` as "Unexpected model error", and the SDK does not retry timeouts.

**One log line per report item** (`report <id>: question N sent after S s`), because the
browser once showed "0 of 5 done" while the logs showed three questions complete, and nothing
recorded when items were sent.

## Consequences

- When Pro is healthy, nothing changes. When it is struggling, a report finishes in minutes with
  some answers scored by Flash.
- **A fallback ideal answer can be more cautious.** On a thin test resume, Flash at `low` said
  the resume recorded no matching experience where Pro built an answer from what was there. The
  scores matched except one dimension (2 against 3). The report does not mark which model wrote
  which item; the usage rows do.
- Transcripts from Flash-Lite may mishear technical terms more often. Typed answers and Live
  transcripts are not affected, so this only touches the turn-based voice path and Discover.
- `plan` (interview start) is **not** covered: it runs once, and nothing in the logs showed it
  failing.
- The tight timeout also applies to the fallback request, which is fine for a `low` call.

## Alternatives rejected

- **Lower thinking effort on Pro for the report.** It changes the quality of every report,
  even healthy ones, to fix a capacity problem.
- **Fewer concurrent calls (staggering).** The 429s are a quota on this model, and ten calls over
  a few more seconds still add up to the same quota while making every report slower.
- **A fallback at `high` effort.** Measured at 53-69 s, as slow as the failing calls.
