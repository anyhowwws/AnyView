# 0031 — Harvey on Gemini Live: planned questions, a live conversation, follow-ups now

- **Status:** Accepted
- **Date:** 2026-10-14
- **Amends:** 0005 (a WebSocket beside SSE), 0013 (voice in and out), 0014 (what each room knows),
  0028 (the agentic loop it rejected for now)
- **Brings forward:** Phase 3 probing (`MAX_PROBES`)

## Context

The turn-based voice loop (ADR 0013, 0026, 0028) leaves 6–20 s of silence between the end of an
answer and the next question: a 2.5 s silence wait, the upload, transcription, then speech
synthesis of the question (4–13 s for a long one). Every fix so far has been plumbing around that
gap. It is still the thing that makes a practice round feel unlike a call.

The owner also wants Harvey to behave like an interviewer, not a script: follow up on a vague
answer, refer to the resume or the garden, nudge in his own words when the candidate stalls.
That is Phase 3's probing, and there is no time to wait for Phase 3.

Gemini Live is one speech-to-speech session: the candidate's audio streams in, Harvey's streams
out, the session's own voice-activity detection decides when a turn ends, and both sides come
back transcribed. It supports function calling, so the app can keep control of anything that
matters while the model handles the conversation.

ADR 0028 rejected a model-driven interviewer for two reasons: a model decision each turn added
2–6 s, and behaviour got harder to predict. Live answers the first, because the decision happens
inside the model that is speaking. Tools only the API can approve answer the second.

## Decision

**The plan still decides the questions; Live runs the conversation around each one.** Pro plans
five questions as before. Each question becomes one Live session whose system instruction holds
Harvey's persona, the materials his room allows, short excerpts of earlier answers, and the
planned question to say word for word.

**The rooms, stated once:**

| Room | Difficulty | Harvey has |
|---|---|---|
| Recruiter screen | Easy | The resume only — no job description, in planning or on Live |
| Hiring manager | Medium | The resume and the job description |
| Panel | Hard | The resume, the job description and the Digital Garden |

The recruiter screen used to read the job description to weight the resume. It no longer does:
a recruiter's first call has the CV in front of them and nothing else.

**What the app decides, and what Harvey decides.** The app owns which question is asked, the
clock, the follow-up budget and where one answer ends. Harvey owns how a pause is read, how a
nudge is worded, rephrasing on request, a brief acknowledgement, and whether a follow-up is worth
asking. He asks through two tools, answered by the API:

- `ask_follow_up(question, reason)` — allowed while fewer than `MAX_PROBES` (2) have been asked
  on this question and the clock has not ended it. He asks only if allowed.
- `finish_question()` — closes the question.

**The browser keeps the clock** (`lib/live-cues.ts`), because Live reacts only after someone
speaks and never notices silence on its own. Ten seconds of dead air sends `[silent]` (Harvey
nudges in his own words, twice at most); fifteen more after a nudge sends `[move_on]`; the
question's budget sends `[time_up]`. Cues are keys, never free text: the browser chooses when
Harvey speaks up, never what he says.

**One WebSocket per question, relayed by the API** (`WS /interview/live`). Vertex Live
authenticates with IAM only, and browser tokens exist only for the API-key product this project
does not use, so the API holds the session with its own identity. The Firebase ID token arrives
in the socket's first frame (a browser cannot set headers on a WebSocket) and is checked by the
same code as `current_user`; the `Origin` header is checked against the CORS list. The question
ends with a `done` frame carrying an `Answer` — text, `cut_off`, and `follow_ups` — which the
browser posts to `/interview/answer` like a typed one. The session stays in the browser and the
engine stays transport-agnostic; it walks `probe → answer` once per follow-up.

**Scoring sees the whole exchange.** `score_user` gets the answer and each follow-up with its
reply, and is told to credit detail given only when pressed while saying that it took a
follow-up. The report shows the follow-ups under the answer.

**The turn-based voice path stays as the fallback.** If Live fails to open or drops, the socket
sends `error` with `fallback: true`; the browser marks Live broken for the page and carries on
with `/ask` + TTS + transcription. Typed answers are unchanged and have no follow-ups.

## Consequences

- Turn-taking drops to about a second, and the candidate can talk over Harvey.
- The voice layer costs about 3× the turn-based one: Live re-bills the whole session context on
  every turn, with no caching. One session per question keeps that context small; a single
  session for the whole interview would have grown with the square of the turn count. Every Live
  usage report is a `live` usage row, so the real spend is visible beside every other call.
- The materials ride in each question's system instruction (up to ~11k tokens at Panel) rather
  than behind a retrieval tool. That costs text-input tokens on every turn and saves a tool round
  trip that would have stopped Harvey mid-sentence. Phase 2 retrieval replaces it.
- Harvey speaks freely, so he can paraphrase the planned question — the problem ADR 0026 fixed.
  The instruction says verbatim; the transcript of what he actually said is what the candidate
  heard.
- Recorded answers are no longer kept on the Live path (ADR 0013's 30-day archive): the
  transcripts are. The turn-based fallback still records.
- Live audio now transits the API, where uploads never did (ADR 0010). It is streamed, not stored.
- A socket pins a question to one Cloud Run instance; a deploy mid-question drops it and the
  browser falls back for the rest of that interview. The Cloud Run request timeout rises to 600 s.
- Donna's Discover speak mode (ADR 0030) is unaffected: it stays on Gemini TTS through
  `speak()` and `voiced()`, which this decision keeps as Harvey's fallback.
- Live models are regional (`LIVE_REGION`, default `us-central1`), unlike every other model here.
  `LIVE_MODEL_ID` defaults to `gemini-live-2.5-flash-native-audio`; **confirm the id, proactive
  audio and the concurrent-session quota in Model Garden before the first real run.** A
  newer Live model is a variable change.
- `ANYVIEW_FAKE_MODEL=1` gets `FakeLive`: it asks the planned question, takes four seconds of
  microphone audio as an answer, asks one follow-up, and closes — so the whole loop can be walked
  through locally with no tokens.

## Alternatives rejected

- **One Live session for the whole interview.** Continuity for free, but quadratic cost, a
  ten-minute connection cap to resume across, and a model that drifts further from the plan
  with every question.
- **Pre-synthesising the planned questions on the old path.** Removes the synthesis pause and
  nothing else: no follow-ups, no natural nudges, ~6 s still left on every turn.
- **ADK, or Agent Engine.** ADK is an orchestration library, which the brief rules out, and would
  replace a few dozen lines. Agent Engine's bidirectional streaming sits behind an experimental
  server mode, and its managed sessions and memory duplicate the event log and the garden.
- **A `recall` tool over the garden.** A tool call stops Harvey's speech until it returns. With
  the garden small enough to sit in the instruction, the tool bought nothing yet.
