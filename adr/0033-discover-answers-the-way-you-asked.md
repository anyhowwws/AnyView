# 0033 — Discover answers the way you asked

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0030 (replaces its Type / Speak switch; everything else in it stands)

## Context

ADR 0030 put a Type / Speak switch in Discover's header. Labelled "How do you want to ask?", it
actually decided whether Donna *answered* out loud: in Speak mode every answer was spoken, typed
or not, and the only change to asking was a microphone button appearing in the composer. So the
screen had two controls that looked like input controls, in two places, and only one of them was.
The switch was also a second click before the first spoken question.

## Decision

- **No mode.** The composer always has the text box, a microphone button and send — the shape
  every chat assistant has.
- **The answer comes back the way the question went in.** A typed question (or a suggested one)
  gets a written answer, as before. A question asked out loud gets the same answer spoken too:
  the browser sends `voice: true` to `POST /brain/discover` for that question only. Typing stays
  the default and Donna still speaks only when asked; pressing the microphone is the asking.
- **A spoken answer's text waits for her voice.** The text streams in a second or two before her
  first clip is synthesised (one TTS call, a fixed cost no server tuning removes). Shown at once,
  it is half read by the time she talks over it. So the browser holds the text back, behind
  "Donna is looking through your garden…", until the first clip arrives, then shows it and lets
  the rest stream (`lib/hold-text.ts`). Her voice failing, Stop, the end of the stream, or
  `HOLD_TEXT_MS` (4 s) with no clip all release it, so a slow or broken voice never hides the
  answer. Revealing each sentence as it is spoken was rejected for now: it needs the server to
  say which text each clip covers (label-only sentences have none), and makes a fast reader wait
  on her every sentence.
- **The microphone click unlocks audio.** It is the user gesture `VoicePlayer.enable()` needs, so
  there is no separate step. If the browser still blocks playback, the question goes through and
  the answer stays on screen, with a note saying why.
- **Every answer has a Read aloud button**, which turns into Stop while that answer is playing.
  `POST /brain/discover/read-aloud` takes the answer's text and returns `audio` frames only,
  through the same `voiced()` wrapper, `for_speech` cleaning and `DONNA_VOICE` as a spoken answer.
  A complete reading is kept in the page, so playing an answer again costs nothing.
- **"Donna is speaking — Stop" stays** above the composer whenever she is talking. Stopping also
  silences clips still arriving for that answer, and aborts a read-aloud request in flight.
- **The microphone is released after each question.** The switch used to hold it open for the
  visit; with no mode, a garden question is a one-off, and the browser's recording light should
  not stay on between them.

## Consequences

- One click to ask out loud instead of two, and the header carries only the title and
  "New conversation".
- A spoken answer appears a second or two later than its text could have; the wait reads as
  Donna thinking rather than as a lag between what is shown and what is heard.
- Losing the mode loses one case: typing every question and hearing every answer. Read aloud
  covers it at one click per answer.
- `/brain/discover/read-aloud` synthesises text the browser sends, not text the server just
  generated. It is behind the same sign-in and allow-list as every `/brain` route, capped at
  8,000 characters (a history turn's cap), and every clip writes a usage row under the
  conversation's `discover-<id>` session, so misuse is bounded and visible.
- A spoken answer the candidate stops early still synthesises its remaining sentences on the
  server, because the text stream it rides on is still wanted. Read aloud, which has no text to
  protect, is aborted outright.
