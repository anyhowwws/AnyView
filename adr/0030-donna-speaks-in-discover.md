# 0030 — Donna speaks in Discover, when asked to

- **Status:** Accepted, amended by 0033 (the Type / Speak switch is gone)
- **Date:** 2026-10-14
- **Amends:** 0017 (Discover), 0029 ("her voice is not decided yet")

## Context

Discover (ADR 0017) is typed: a question in a text box, Donna's answer streamed back as text with
citation chips. The owner wants to be able to ask out loud and hear the answer, the way Harvey's
interview already works (ADR 0013, 0016, 0026). But Discover is mostly a reading tool — answers
are lists with `[P3]` labels that link to entries — so speech must not become the default.

Everything voice needs already exists for Harvey: sentence-by-sentence synthesis interleaved with
the token stream (`interview/voice.py:voiced`), a gap-free clip player and a silence-detecting
recorder (`lib/voice.ts`), signed-URL audio uploads under `audio/<uid>/` and transcription by the
chat model through the adapter's `attachment=` path.

## Decision

- **Typing stays the default.** A Type / Speak switch sits in Discover's header. Speak mode is
  chosen per visit and not remembered: leaving the garden, or switching back, stops Donna and
  releases the microphone. The switch click is the user gesture that unlocks audio.
- **In speak mode every answer is spoken**, whether the question was asked out loud (the
  microphone button) or typed. The text and the citations arrive exactly as before; audio frames
  ride beside them.
- **Asking out loud is push-to-talk**: one click opens the microphone, a 2.5 s pause (or "Done")
  ends the question, eight seconds of nothing closes it, and a question is capped at a minute
  (`QUESTION` limits in `lib/voice.ts`). The transcript becomes the question bubble, then is asked
  like a typed one. No auto-listening after Donna finishes: a garden question is not a turn-taking
  conversation, and an always-open microphone would hear her.
- **Same machinery, Donna's settings.** `POST /brain/discover` takes `voice: true` and wraps the
  stream in `voiced()`. `POST /brain/discover/transcribe` shares one helper with
  `/interview/transcribe` (`api/uploads.py:transcribe_recording`): same ownership check, same
  `audio/<uid>/` prefix and 30-day expiry, usage rows under the conversation's
  `discover-<id>` session.
- **What is spoken is cleaned, what is shown is not.** `discover.for_speech` strips citation
  labels, `**`, backticks and list markers before synthesis, so "[P3]" is never read out as
  "open bracket P three". A sentence that is only labels is skipped rather than paid for.
- **Spoken answers are asked to be short.** A note in the *user* turn (so the garden stays the
  cached system prefix) tells the model the answer will be heard: two or three sentences, or a
  brief list.
- **Donna's voice is `DONNA_VOICE`**, default **`Kore`** (firm, female-sounding), set by Terraform
  variable `donna_voice`. Her delivery, `discover.DONNA_DELIVERY`, follows ADR 0029's lessons: one
  short positive clause, warm, confident and brisk. Both are first choices, not chosen by ear yet.
- **One player per persona.** `HarveyVoice` became the generic `VoicePlayer`; `harveyVoice()` and
  `donnaVoice()` each hand out their own instance on the one shared `AudioContext`.

## Consequences

- A spoken answer costs one TTS call per sentence on top of the Discover call, and a spoken
  question one transcription call. Typing costs nothing more than before.
- `Kore` and the delivery need auditioning on the real project before they are called final. An
  unknown voice name is a 400 on every clip; the stream then sends one `voice_off` and the answer
  carries on as text, so a wrong name looks like "voice is broken", not like an outage.
- **Terraform must be applied** to set `DONNA_VOICE` on Cloud Run; until then the in-code default
  (`Kore`) is used.
- Listening errors in `lib/voice.ts` now say "type instead" rather than "type your answer", since
  the same recorder serves a question.
