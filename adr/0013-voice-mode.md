# 0013 — Voice mode: Gemini TTS out, Gemini transcription in

Status: accepted
Date: 2026-09-22

## Context

Donna reads as a person but has never sounded like one. A screening interview
is a spoken event: the pauses, the thinking out loud, the moment you realise
you have not said the number yet. Typing an answer into a textarea rehearses
none of that. Voice mode should make a practice round feel like the call it is
preparing you for — Donna asks out loud, you answer out loud, she moves on.

Both directions needed a decision, and the options were not symmetric.

**Donna's voice.** Three ways to make audio:

1. The browser's own `speechSynthesis`. Free, instant, no backend. But the
   voice is whatever the operating system ships — good on macOS, robotic on
   Windows and Android — and no prebuilt female voice is guaranteed anywhere.
2. Gemini TTS on Agent Platform, through the existing `google-genai` client.
3. Cloud Text-to-Speech (Chirp 3 HD). The best voices and true streaming
   synthesis, at the cost of a dependency, an API enablement, IAM, and a second
   cost-tracking path outside the usage log.

**The candidate's voice.** Three more:

1. The browser's `SpeechRecognition`. Free and live, but Chrome and Safari
   only, it cuts out on the thinking pauses interview answers are full of, and
   it never hands back the audio — so keeping recordings would mean recording
   twice.
2. Record with `MediaRecorder`, transcribe with the model.
3. Cloud Speech-to-Text v2 streaming. Real partial transcripts, at the cost of
   a dependency, an API, IAM, and a bidirectional transport that ADR 0006's
   one-way SSE does not have.

## Decision

**Gemini TTS on Agent Platform for Donna, Gemini transcription for the candidate.**
Both go through `llm/adapter.py`, which keeps every rule this project already
has: one SDK, IAM only, no API key, and one usage row per model call.

`speak()` is a third operation on the adapter beside `generate()` and
`stream()`. It returns a WAV file as plain bytes — the model emits headerless
PCM, which no browser will play, so the adapter wraps it using the standard
library's `wave`. No new dependency in either direction: transcription reuses
the `attachment=` path that already lets the model read PDFs.

**Sentences are synthesised as they stream, not after.** `interview/voice.py`
splits the `ask` stream into sentences and sends each to TTS in a two-thread
pool while the next is still arriving, pushing `audio` frames down the SSE
channel ADR 0005 already defines. Waiting for the whole question would put two
seconds of silence at the top of every turn. Text never waits for audio: if
synthesis fails, one `voice_off` frame tells the browser to stop expecting
clips and the interview continues in text.

**The turn ends on silence, not on a click.** What makes the exchange feel live
is not word-by-word transcription — the design is turn-taking, so partials buy
little — but never having to reach for the mouse. Donna's last clip finishes,
the microphone opens itself, and about two and a half seconds of quiet ends
your turn. That is an `AnalyserNode` reading the level that already drives the
"she's listening" meter, and the rules live in a pure function so they can be
tested without a microphone.

**Recordings are kept for 30 days**, under `audio/<uid>/` in the existing
uploads bucket, written by the browser through the same signed-URL path as a
resume (ADR 0010) so audio never transits the API. A separate root, not
`uploads/<uid>/audio/`, because a bucket lifecycle rule matches a literal
prefix and cannot wildcard the uid in the middle. Resumes never expire;
recordings of your own voice should not sit in a bucket forever.

## Consequences

- There is a 1–3 second pause between the candidate finishing and Donna
  replying, while the recording uploads and is transcribed. Accepted: the
  alternative costs a new transport and two new Google APIs.
- Voice costs tokens in both directions, on top of the interview itself. Every
  call lands in the usage log as `speak` or `transcribe`, so the price of a
  spoken round is visible next to a typed one.
- The TTS model is a different model family with its own id (`TTS_MODEL_ID`),
  and it must be enabled in Model Garden for the project like any other. The
  default is `gemini-2.5-flash-preview-tts`; **confirm the id available in this
  project before the first real run.** Being a variable, a change is a plan,
  not a deploy.
- Voice is a preference, off by default, and text input never goes away — the
  mic panel has "Type this one instead", and a transcript can be edited before
  it is sent. Browsers without `MediaRecorder` see the typed interview exactly
  as before.
- A second Agent Platform model means a second thing that can be rate-limited. A 429
  maps to the same 503 as everything else, and the interview degrades to text
  rather than stopping.
- Recordings are the raw material for a Phase 2 idea this does not build:
  scoring delivery — pace, filler words, hesitation — rather than only content.

## Alternatives rejected

- **Browser `speechSynthesis`**: no control over the voice, no infrastructure
  story, and it would have to be reworked the moment the voice mattered.
- **Cloud TTS / Cloud STT v2**: better audio and real partial transcripts, but
  two APIs, two dependencies, new IAM, and a websocket transport that ADR 0006
  deliberately does not have. Revisit if turn-taking latency becomes the thing
  that spoils the illusion.
- **Browser `SpeechRecognition`**: ruled out by retention — it never returns
  the audio — before browser support ruled it out anyway.
