# 0035 — Harvey's fixed lines in his Live voice, in several wordings

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0016 (the interjections), 0028 (the pre-flight's speaker check), 0032 (the clips the browser plays)

## Context

Since ADR 0032 the browser plays Harvey's fixed lines on Live: the nudge (`stalled`), the cut-ins
(`time_up`, `move_on`) and the `goodbye`. The pre-flight's speaker check plays `hello`. All of them
came from the Gemini TTS model, and the interviewer is Gemini Live (ADR 0031). Both use the
prebuilt voice `HARVEY_VOICE`, but they are different models and do not sound alike. The owner heard
two Harveys: one in the hearing test and in every nudge, another asking the questions.

Each line also had one wording. "Take a moment if you need it. Or shall we move on to the next
one?" heard several times an interview was the most annoying thing in it.

## Decision

**Live reads the fixed lines aloud.** `/interview/say` opens one short Live session per line
(`interview/fixed_lines.py`) with the interviewer's voice and delivery direction, and an instruction
to say the text it is sent word for word and nothing else (`prompts.LIVE_READER`). Proactive audio
is off for this session, so Live does not decide a line needs no reply. The audio comes back as the
same WAV clip as before, so the browser does not change.

**TTS is the fallback.** If Live fails, says nothing, or takes more than 15 s, the line comes from
`speak()` as before. A clip is never missing because of Live.

**Each finished clip is cached in the API's memory**, keyed by voice and text. The lines are the
same for every user, so the always-warm instance (ADR 0023) reads each one once. Later interviews
make no Live call for them. TTS fallbacks are not cached, so the next request tries Live again. This
is not session state (Phase 0's rule): losing it only means reading the lines again.

**Lines heard often have several wordings** (`INTERJECTIONS`: 4 time-ups, 5 nudges, 3 move-ons).
`/interview/say` takes `variant`, an index that wraps round, never text. The browser starts each
line at a random wording, moves to the next wording after each use, and fetches only the wording due
next. Every nudge still offers to move on, because the silence after it is taken as a yes; a test
holds them to that.

## Consequences

- One voice for Harvey throughout a Live interview, the hearing test included.
- Live may paraphrase. When the transcript's words differ from the line, it is logged
  (`live read a fixed line differently`). Check that log after the first real runs.
- A few extra Live sessions per instance lifetime, each a few seconds and each a `live` usage row.
  A nudge fetched mid-question is a second concurrent Live session for that user for a moment.
  Count that against the concurrent-session quota.
- The first `hello` after a deploy takes a Live connection (about 2–4 s), not a TTS call. The
  pre-flight now prefetches it when it opens, so the "Speak to me" click rarely waits.
- On the turn-based fallback path the questions are TTS while cached clips are Live, a small
  mismatch only when Live is already broken. Donna (ADR 0030, 0033) is unchanged.
- `FakeLive` reads aloud whatever text it is sent when its instruction holds no question, so tests
  and `ANYVIEW_FAKE_MODEL=1` exercise the Live path.

## Alternatives rejected

- **Only the hearing test on Live.** The mismatch moved into the interview, where it is worse.
- **Tuning the TTS direction to sound closer.** Two models, one voice name: never the same voice.
