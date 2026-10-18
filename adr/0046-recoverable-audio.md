# 0046 — Recoverable audio: a fresh context on retry and on device change, and failures on screen

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** 0028 (one audio context for the interview)
- **Note:** first filed as a second 0041 by mistake; renumbered on 2026-10-18 with no change to its content

## Context

On 2026-10-16 the pre-flight's hearing test played nothing in the owner's normal browser window,
and worked in a fresh incognito window. The server was not the cause: every `/interview/say` call
returned 200, and the same `hello` line generated against Agent Platform was a 4 s clip at normal volume.

The page keeps one `AudioContext` for its whole life (ADR 0028), and a tab lives long. A context
can stay bound to an output that has gone (Bluetooth headphones that disconnected, a tab the
browser put to sleep) and report itself as `running` while playing to nowhere. A fresh window
makes a fresh context. This is the likeliest explanation, but it was not reproduced: no code
can see whether sound reaches a speaker.

Two things made it worse:

- "Speak again" reused the same context, so retrying could not help.
- A clip that failed to decode or play went only to the console. The card then sat on
  "Listen…", or, because `markComplete` still fired `onFinished`, said "Did you hear Harvey?" as
  if it had played.

## Decision

**The page's audio context can be rebuilt** (`resetAudio` in `lib/voice.ts`): a new context, the
old one closed, Harvey's and Donna's players moved to the new one (`VoicePlayer.rebind`), and
subscribers told (`onAudioReset`; the pre-flight's level meter reconnects, because an analyser on
a closed context reads zeros). Live's capture worklet is now loaded per context, since a module
added to one context is not on the next.

**When it is rebuilt:**

- **"Speak again" in the pre-flight** always rebuilds. It is a click, so the new context may start.
- **After `devicechange`** (headphones connected or removed), the next safe moment rebuilds:
  a pre-flight click (`unlockAudio`), the start of a Live question, or a click that plays
  Donna. Never while Harvey or Donna is speaking, so "let's move on" is not cut off.
- **In Discover**, the next "Read aloud" or spoken question after a failed clip rebuilds.

**Failures are shown.** `VoicePlayer.onError` fires when a clip will not decode or play, and a
failed run no longer reports `onFinished`. The pre-flight shows "Harvey's voice didn't play.
Press Speak again, or reload the page…" with "Speak again". Practice and Discover show a note,
and the question or answer stays on screen.

A context that is `suspended` or Safari's `interrupted` is resumed, not only `suspended`.

## Consequences

- One click (Speak again) does what reloading the page did, if the cause is a stale context.
  If the cause is outside the page (a muted tab, the system volume), nothing here can fix it,
  and the message says to reload.
- A rebuild mid-interview happens only between uses, so it cannot cut Harvey off. A device
  change during a Live question takes effect at the next question.
- Tested with stubbed Web Audio in Node (`tests/audio-reset.test.mts`) and in the browser with
  the fake model: "Speak again" made exactly one new context and the clip played on it, and a
  forced decode failure showed the message. Not tested with real headphones being unplugged.

## Alternatives rejected

- **A new context for every clip.** Browsers cap contexts per page, and the microphone meter
  and Live's capture share this one (Safari reads a mic as silence on a context it never saw a
  click for).
- **Rebuilding immediately on `devicechange`.** It could fire mid-sentence or mid-question and
  cut Harvey off, or leave Live's capture on a closed context.
