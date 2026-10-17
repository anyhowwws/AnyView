# 0043 — The clock pauses while Harvey speaks, and he times his own follow-ups

- **Status:** Accepted
- **Date:** 2026-10-18
- **Amends:** 0040 (a follow-up adds time), 0032 (the browser owns the clock on Live)

## Context

Two things made a timed interview feel unfair:

- **Harvey's talking ate the answer's time.** On Live the clock started when Harvey finished
  asking, but kept running while he asked a follow-up, nudged, or bridged. On the turn-based
  fallback path the on-screen countdown started when the question's *text* finished arriving,
  while his voice was still reading it.
- **Every follow-up added the same 90 s** (ADR 0040), whatever it asked. "Which region was
  that?" and "Walk me through the incident you skipped" got the same time.

The question's own clock stays as ADR 0016 has it: the model picks it when planning, 45–300 s.

## Decision

- **The clock runs only while Harvey is quiet.** On Live, `nextCue` adds up the candidate's time
  (`CueState.usedMs`) tick by tick and skips any tick where Harvey is audible: his Live voice, or
  one of his fixed lines. The budget is checked against that, not against the time since he
  asked. `LiveQuestion` reports what is left on every tick (`onClock`), and the screen's
  countdown shows that number instead of keeping its own, so the two cannot drift apart.
- **On the turn-based path** the countdown starts when Harvey's voice finishes (`harveyAsking`
  in `practice.tsx`), which is also when the microphone opens. `MAX_ANSWER_MS`, the recording
  cap, is now 5 minutes, the longest clock a question can have.
- **Harvey picks what each follow-up adds.** `ask_follow_up` takes an optional `seconds`: how
  long a strong spoken answer to that follow-up needs. `LiveTurn` holds it to
  `MIN_FOLLOW_UP_SECONDS`–`MAX_FOLLOW_UP_SECONDS` (30–300 s, `follow_up_seconds`), and uses
  `DEFAULT_FOLLOW_UP_SECONDS` (90 s, ADR 0040's number) when it is missing or not a number. The
  `follow_up` frame carries it to the browser, which adds it to the budget. A refused follow-up
  adds nothing. `MAX_PROBES` stays at 2.

## Consequences

- A question can now ask for its clock plus up to 2 × 300 s of follow-ups, plus Harvey's talking.
  The server still ends a Live question at `MAX_TURN_S` (9 min), inside Live's ten-minute
  connection limit: the question closes with what was said, marked as cut off. The socket limit
  no longer depends on the question's seconds, because follow-up time is not known in advance.
- Harvey's pick depends on the realtime model filling a tool argument well. It needs a smoke test
  on real Live before relying on it; the clamp and the default keep a bad value harmless.
- The browser falls back to 90 s for a `follow_up` frame without `seconds`, so an older API
  during a deploy still works.
- The time between the candidate's last word and Harvey starting a follow-up (the model's latency
  and the `ask_follow_up` round trip) still counts. It is a second or two.
- Nudges pause the clock too: they are Harvey talking.

## Alternatives rejected

- **The planner picks a follow-up time per question.** Simpler and testable, but it is decided
  before anyone knows what the follow-up will ask.
- **A fixed five minutes per question and per follow-up.** Tried first in this ADR's draft; the
  owner preferred clocks the model judges per question.
- **Three follow-ups.** With up to five minutes each, one question would far outrun Live's
  connection limit.
