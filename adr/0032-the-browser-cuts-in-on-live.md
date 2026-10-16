# 0032 — On Live, the browser cuts in; Harvey bridges, and closes the interview

- **Status:** Accepted, amended by [0035](0035-harveys-fixed-lines-in-his-live-voice.md) (the clips are read by Live, in several wordings)
- **Date:** 2026-10-14
- **Amends:** 0031 (the cue channel and the closing line), 0016 (how silence is measured on Live)

## Context

The first real run on Live (ADR 0031) worked, follow-ups and all, and showed six problems:

1. **Time-up did not cut in.** The browser sent `[time_up]` as text, but with automatic voice
   activity detection Live answers only once it decides the candidate's turn is over, and their
   continuing speech counts as barge-in on anything it starts to say. Barge-in runs one way: the
   candidate can interrupt Harvey, not the reverse. Harvey waited for them to stop, so the clock
   meant nothing.
2. **No nudge on a long pause or an "err…".** The dead-air clock counted any microphone level
   ≥ 0.02 as speech, so a filler, a breath or the room kept resetting it.
3. **The question was split on screen.** It was built from Live's output transcript, which
   arrives late and in fragments; its tail landed in the follow-up line.
4. **Harvey's last words could be clipped**: playback stopped the moment `done` arrived.
5. **No goodbye.** The interview just ended.
6. **Transitions felt abrupt and doubled.** Harvey closed each question with a line, then opened
   the next with "thanks" again, and neither said anything about the answer.

## Decision

**The browser owns time and silence outright, and Live is never asked to interrupt.** When the
budget runs out, or the silence after a nudge says "move on", the browser stops sending the
microphone upstream, silences Harvey's Live audio, plays a fixed `/interview/say` clip
(`time_up` or the new `move_on`), and sends `{"type": "end", "reason": ...}`. The server closes
the question at once. `cut_off` comes from the reason: `time_up` and `move_on` are cuts; `manual`
(the candidate's own "Next question") is finishing. There are no text cues any more; `[begin]` is
the only text the API sends Live, and nothing the browser sends is ever spoken.

**Silence is measured from the last real word.** The dead-air clock resets on a transcript
fragment with a word in it that is not a filler (um, uh, er, err, erm, hmm, mm, ah, oh, eh, with
any repeats), or while Harvey is audible. Nudges are the fixed `stalled` clip; the give-up is the
fixed `move_on` clip. This relies on Live transcribing input while the candidate is still talking,
which it does in fragments every second or so.

**The screen shows the plan, not the transcript.** The question area shows the planned
`question.text`; the line under it shows the follow-up as Harvey declared it to `ask_follow_up`,
replaced on each follow-up.

**On `done`, queued audio plays out** before the next question takes the screen.

**One acknowledgement per transition, and a specific one.** Harvey calls `finish_question` with no
closing line. The next question opens by bridging from something specific the candidate said
(a project, a number, a decision), and the last answer reaches that prompt at 1,200 characters
rather than 600. After a cut, the next question opens straight away: the clip already said
"let's move on".

**The last question closes the interview.** The prompt tells Harvey to say that's all his
questions and thank them for their time. When the browser ends it instead (time-up, move-on,
"Finish"), or on the turn-based fallback path, the fixed `goodbye` clip plays, once.

## Alternatives

**Manual turn-taking.** Live can run with automatic activity detection off, the client marking
when the candidate's turn starts and ends. At time-up the browser would end the turn and Harvey
would cut in in his own Live voice, with no barge-in to stop him. Not taken yet: the browser
would then have to judge the end of *every* answer, which Live's own detection does well today,
and the behaviour on Agent Platform is untested. Worth an experiment against the real model.

## Consequences

- Nudges and cut-ins are fixed lines, not Harvey's own words. They always fire, at the moment
  the clock says, which is what an interview on a schedule needs. ADR 0031's "nudges in his own
  words" is given up for that.
- If Live's input transcription turns out to arrive only at the end of a turn, a candidate
  talking for ten seconds straight would be nudged mid-sentence. The fix then is to accept a mic
  level well above the noise floor as speech as well; watch for it on the next real run.
  **It happened** (2026-10-14): candidates talking without a pause were nudged and moved on.
  A level now counts as talking when it is at least 4× the room's own (never under 0.02) for
  300 ms (`live-cues.ts:hearVoice`). The price is the one this ADR set out to avoid, in a
  smaller form: a long "ummm" now delays the nudge.
- Fake mode (`FakeLive`) closes silently, or with a goodbye on the last question, so the walk-
  through matches the real prompt. It sends one transcript per answer, so the nudge path is
  covered by `tests/live-cues.test.mts`, not by the walk-through.
- `/interview/say` accepts five keys; a test ties them to `INTERJECTIONS`.
