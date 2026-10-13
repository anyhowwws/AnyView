# 0026 — Voice turns that flow: audio from question one, the question verbatim, no review step

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0013 (transcript review before sending), 0016 (dead air), the `ask` prompt

## Context

The first real voice interview after Phase 1 (production logs, 2026-10-13 16:09–16:15 UTC)
went wrong in a chain:

1. **Question one was text-only.** The first `/interview/ask` went out without `?voice=true`.
   Practice unlocks the `AudioContext` when it mounts, but it mounts after `/interview/start`
   returns, and planning took 23 s. A browser's permission to start audio after a click
   lasts seconds, so `resume()` failed and Practice fell back to typing.
2. **Switching to speaking opened the microphone on a question she never said.** By design
   (to avoid paying for the question twice) she stayed silent for an already-asked question.
   The candidate waited for her to speak, and ten seconds later the dead-air rule made her
   ask whether to move on — the only `/interview/say` call in the log.
3. **Then nothing moved on.** After the stall line, a timed question waited for the rest of
   its own clock (45–300 s) before giving up.
4. **Questions were cut down.** `ask` told the fast model to restate the planned question
   "in your own words", in "two or three sentences at most", after a greeting or
   acknowledgement. Each `ask` produced about 50 visible tokens: the planned question,
   written by the judgement model with its rationale, was compressed into a sentence or two.
5. **A transcript sat on screen for four seconds** before sending. In a real interview there
   is no reviewing what you just said; it only broke the rhythm.

## Decision

- **Unlock audio inside the Start click** (`unlockAudio()` in `lib/voice.ts`), so Practice
  finds the shared context already running.
- **Switching to speaking re-asks the current question aloud.** One more short `ask` call
  is cheaper than a candidate waiting on silence.
- **Silence after the stall line is a yes.** Timed questions get `giveUpMs` = 10 s of dead
  air + 15 s more: the turn ends as `(no answer given)` and she says the "let's move on" line.
  Untimed keeps its 30 s dead-microphone check, which is a different problem.
- **`ask` writes only the lead-in; the planned question follows word for word.** The plan
  prompt already asks for questions phrased as an interviewer says them aloud.
- **Spoken answers are sent as soon as they are transcribed.** The transcript is shown only
  if sending fails, so it can be sent again.

## Consequences

- What she asks is exactly what the report scores against: there is no longer a paraphrase
  between the plan and the candidate.
- A misheard word can no longer be corrected before sending. The report shows the
  transcript, and scoring is per answer, so one misheard word costs little.
- Unchanged and still worth watching: synthesising the question's long sentence took
  8–13 s in that run, so she says the lead-in, pauses, then asks. Splitting long sentences
  for synthesis, or a faster TTS model, is the next lever.
