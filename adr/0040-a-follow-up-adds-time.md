# 0040 — A follow-up adds time to the question's clock

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** 0016 (each question's clock), 0032 (the browser owns the clock on Live)

## Context

Each question has one clock, set when the interview is planned (`Question.seconds`, 45–300 s, ADR
0016). On Live, Harvey may follow up twice on a question (`MAX_PROBES`, ADR 0031), and every
follow-up is more talking inside the same clock: the answer, Harvey asking, and up to two more
answers had to fit in the planned seconds. A 120–180 s clock could cut the candidate off during the
second follow-up, which is the opposite of what a follow-up is for.

## Decision

**Each follow-up Harvey is allowed adds `FOLLOW_UP_EXTRA_MS` (90 s) to the question's clock**
(`live-cues.ts`). The API's `follow_up` frame already says whether the follow-up was allowed; on
`allowed: true` the browser:

- raises the budget `nextCue` enforces (`LiveQuestion.budgetMs`, read on every tick), so the
  cut-in moves to the new deadline; and
- moves the on-screen countdown by the same amount (`Practice.extendClock`), so the two clocks
  keep agreeing.

An untimed interview has no budget and gains nothing. A refused follow-up adds nothing, so the
most a question can run is its planned seconds plus 2 × 90 s. The server's socket limit
(`seconds + 240`, capped at 9 minutes) already covers that.

The clock stays in the browser, as in ADR 0026 and 0032: no server-side timing was added.

## Consequences

- A question with two follow-ups can run up to three minutes longer than planned. That is the
  point; Harvey's follow-ups are bounded by `MAX_PROBES`, so the extension is too.
- 90 s is a judgement, not a measurement: long enough for a spoken follow-up answer plus Harvey's
  question. It is one constant to change.
- The turn-based fallback path has no follow-ups and is unchanged.

## Alternatives rejected

- **Longer planned seconds for every question.** Most questions end without a follow-up, so the
  candidate would get time they do not need on all of them.
- **Pausing the clock while Harvey speaks.** More precise, but the browser cannot always tell his
  speech from his tool call, and it still would not cover the candidate's follow-up answers.
