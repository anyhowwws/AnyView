# 0005 — Hand-rolled server-sent events over a streaming SDK

- **Status:** Accepted
- **Date:** 2026-09-16

## Context

The interviewer's tokens must appear in the browser as they are generated. On
Cloud Run the API is a plain HTTP server, so the transport question is just:
which streaming protocol, and how much library sits on top of it.

## Options considered

**A streaming-UI SDK** (e.g. an AI SDK with server and client halves). Gives
typed message parts, tool-call rendering, and React hooks for free. Also brings
a second provider abstraction (its own model adapters), its own wire format,
and a dependency whose upgrade cadence is faster than this project's.

**WebSockets.** Bidirectional, but the interview is strictly request/response
per turn; the browser never needs to push mid-stream. Also harder to proxy and
to keep stateless behind Cloud Run's request model.

**Server-sent events, hand-rolled.** A FastAPI `StreamingResponse` yielding
`data: ...\n\n` frames; an `EventSource` (or `fetch` + `ReadableStream`) in the
browser. ~40 lines each side. Unidirectional, which matches the interview
engine's shape: text arrives, the state machine decides, tokens go back.

## Decision

Hand-rolled SSE. The adapter module (see 0004) already provides the provider
abstraction, so a streaming SDK would duplicate it. The interview engine is a
state machine over turns and is independent of how text arrives; SSE is the
transport for Phase 0–4, and voice replaces the transport in Phase 5 without
touching the engine.

## What this costs

- **We own the protocol.** Reconnect, heartbeat, and error frames are ours to
  write. Kept minimal: a `ping` comment every 15 s and a terminal `done` event.
- **No free tool-call rendering.** If the interviewer ever needs to stream
  structured parts (not just text), the event schema grows. It is JSON on the
  wire, so it can.
- **Proxy behaviour.** Cloud Run supports streaming responses; anything placed
  in front of it must not buffer. Firebase Hosting rewrites to Cloud Run are
  fine; a CDN with buffering would not be.
