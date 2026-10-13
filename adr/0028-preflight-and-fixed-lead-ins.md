# 0028 — A pre-flight before question one; fixed lead-ins; one microphone per interview

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0026 (the `ask` lead-in), 0013 (where the microphone is opened)

## Context

The first run after ADR 0026 (production, 2026-10-13 16:32–16:34 UTC, Safari):

- **The question was said twice.** Asked for "one sentence, do not ask the question", the fast
  model wrote a greeting *and* the question (70 visible tokens, seven speech clips), and the
  planned question was then appended verbatim.
- **Safari's microphone prompt appeared mid-question.** `listen()` called `getUserMedia` per
  answer, and the first call came while question one was still being spoken.
- **The candidate was never heard.** Two answers ended as "(no answer given)" without a
  transcription, and the third came back from transcription as silence. `listen()` built a new
  `AudioContext` for its level meter on every answer. Safari leaves a context it never saw a
  click for suspended, and a suspended analyser reads zeros: speech looked like silence.
- **"Let's move on" was cut off.** The next question arrived in the same second, and Practice,
  which remounts per question, stopped its own player.
- **"Thanks" after a cut-in.** The model's lead-in thanked the candidate for an answer Donna had
  just interrupted.

We considered moving to an agentic, model-driven interviewer loop instead. Rejected for now:
every failure above is in browser audio plumbing or in one prompt, and a model decision on each
turn adds 2–6 s and makes behaviour harder to predict. Bounded probing (Phase 3, `MAX_PROBES`)
comes after a clean voice run.

## Decision

- **A pre-flight screen between Start and question one** (`components/preflight.tsx`). It shows
  at once, while the questions are planned (~20 s), and checks three things: the microphone
  (permission plus a live level meter), the speaker (Donna's fixed `hello` line, "did you hear
  her?"), and the questions (ready or not). **Begin** is enabled when all three are done, or when
  the candidate chooses to type. The Begin click unlocks audio for the interview, and the
  pre-flight prefetches the `time_up` and `stalled` clips, so the first cut-in is never queued
  behind the question that follows it.
- **One microphone stream, one `AudioContext`, one player for the whole interview.**
  `acquireMicrophone()` opens it in the pre-flight, `listen()` reuses it, and the App releases it
  when the interview ends. The level meter taps the shared, already-unlocked context. A new
  question calls `DonnaVoice.detach()`: whatever is playing finishes, and the new clips queue
  behind it.
- **Fixed lead-ins, no model call in `ask`.** `prompts.lead_in` chooses the line by how the last
  turn ended:
  - first question: a greeting;
  - after an answer: one of four short thanks;
  - after a cut-in or no answer: nothing when spoken (her "let's move on" said it), or "Let's
    move on." on screen.

  `Answer.cut_off` carries "the clock ended this", set by the browser.

## Consequences

- `ask` costs nothing and returns at once. Its only latency is speech synthesis.
- Donna's lead-ins are less varied. That is a fair price for never repeating a question or
  thanking someone she interrupted.
- The microphone indicator stays on for the whole interview, as it would on a call.
- A candidate who refuses the microphone can still begin, by typing.
- Not addressed: synthesising a long question still takes 4–7 s, so there is a pause between the
  lead-in and the question.
