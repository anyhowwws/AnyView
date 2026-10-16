# 0016 — Speaking by default, and a clock that belongs to the question

Status: accepted
Date: 2026-09-23

## Context

Voice mode (ADR 0013) shipped switched off, behind a toggle labelled "Voice
on / Voice off". Two things were wrong with that.

The first is the default. An interview is a spoken event. Building the whole
turn-taking loop and then making people find a toggle before they can use it
meant most runs were still typing practice — the thing that rehearses none of
what a real screening call demands.

The second is the label. "Voice on" did not say whose voice or which
direction. People read it as a mute button for Donna rather than as a choice
about how *they* answer.

And a practice interview with no clock is not practice. A real screening call
has a schedule: the interviewer has five questions and forty minutes, and the
candidate who takes twelve minutes on the first one does not get asked the
fifth. Rambling is the most common way a decent answer becomes a bad one, and
nothing in the app made you feel it.

## Decision

**Speaking is the default.** The stored preference now has to say `off` to mean
typing; no preference, or no storage at all, means speaking. The control is a
two-option segmented switch reading **Answer by speaking / Answer by typing**,
which names the direction and the actor. Nothing else about the fallbacks
changed: a browser with no `MediaRecorder`, a denied microphone or a blocked
`AudioContext` still lands on the typed interview.

**The clock belongs to the question, not to the interview.** A time-bounded
setup gives each question its own budget, and the *model* sets it when it plans
the interview — a `seconds` field beside `text`, `competency` and `rationale`.
An opener does not deserve the same three minutes as "tell me about a failure",
and only the thing that wrote the question knows which it is. The engine clamps
the answer into 45–300 s, so a stray number costs that question its clock
rather than costing the candidate a retry.

**Running out of time is tiered, and Donna says so out loud.**

- **Ten seconds of dead air** — nothing said at all — and she speaks up. The
  microphone stays open; this is a prompt, not a verdict. Untimed interviews
  keep the old behaviour, where prolonged silence means a broken microphone.
- **The budget expiring** ends the turn wherever it is, mid-sentence included,
  and she says so before moving on.

Her interjections are **fixed lines, not generated**. An interruption that
arrives after a model call has stopped being an interruption. `POST
/interview/say` takes a *key* — `time_up` or `stalled` — never free text, so
the route cannot become a way to have the TTS model read out whatever a caller
sends. The browser fetches each clip once and reuses it for the whole run, so a
five-question interview synthesises two short clips at most.

**Every interview opens with "tell me about yourself."** It is how nearly every
screening call starts, it is the answer people are worst at, and planning
around it was leaving out the one question they were guaranteed to face. The
plan prompt makes question one an opener phrased the way that particular room
would phrase it, with `background` as its competency — "almost always", so the
model can still depart when the situation makes an opener plainly wrong.

**Ending early discards.** "End interview" asks for confirmation, names the
question you are on and how many answers will be lost, and then clears the
session. No partial report: scoring two answers out of five would invite
comparison with a full run that does not hold, and the machinery to mark and
explain a partial report is not worth building for the case where someone
realises they set the interview up wrong.

## Consequences

- A timed interview is genuinely harder, and it is meant to be. The budget is
  visible from the moment the turn starts and turns red at thirty seconds.
- The clock pauses while the end-interview confirmation is open and resumes
  with the remainder it held, so the dialog is neither a free reset nor a
  penalty.
- An answer can now be `(no answer given)` — the clock ran out on someone who
  never started. It scores honestly rather than being hidden, and it keeps
  `finish()`'s "every question needs an answer" rule intact. The upload and the
  transcription call are both skipped, because there is nothing to transcribe.
- Two Agent Platform models are now on the critical path of a timed turn. A TTS failure
  still degrades to silence rather than stopping the interview.
- **The rubric does not really fit the opener.** "Tell me about yourself" is
  scored on STAR completeness, specificity, quantified outcome and ownership
  language like every other answer, and a background walkthrough is not a STAR
  story. The scores on question one will read harsher than they should. Fixing
  it means per-question rubrics, which is a larger change than this one and
  belongs with the Phase 3 probing work.
- `time_bounded` defaults to `false` on the wire and `true` in the form. A
  session saved by an older build does not acquire a countdown halfway through;
  a new interview is realistic unless you say otherwise.
- Dead air and the budget are both enforced in the browser, by the same
  `AnalyserNode` that already drives the level meter. Nothing about the clock
  is enforced server-side, which is fine for a practice tool and would not be
  if a score ever had to be trusted.

## Alternatives rejected

- **One fixed limit for every question** (two minutes, say). Simpler, and
  wrong in the same way a fixed difficulty would be: the opener and the failure
  story are not the same task.
- **A timer that nudges but never cuts.** Teaches the feel of the clock without
  the consequence, and the consequence is the entire lesson.
- **Generating the interruption.** More natural wording, several seconds too
  late, and a paid call every time someone overruns.
- **Scoring a partial interview on "End interview".** Considered and declined
  by the owner: a report on two questions is not comparable to a report on
  five, and the button exists for abandoning a run, not finishing one early.
