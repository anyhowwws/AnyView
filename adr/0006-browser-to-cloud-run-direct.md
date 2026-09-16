# 0006 — Browser talks to Cloud Run directly, not through Firebase Hosting

- **Status:** Accepted
- **Date:** 2026-09-16
- **Amends:** 0005 (the "Proxy behaviour" cost was wrong)

## Context

The scaffold routed API traffic through a Firebase Hosting rewrite
(`/api/** → Cloud Run`) so the frontend and API would share one origin. ADR
0005 assumed that path would stream.

It does not. Firebase Hosting rewrites to Cloud Run **buffer the whole
response** in the CDN layer before sending it to the client, and enforce a
**60-second request timeout** regardless of the Cloud Run timeout. Server-sent
events through that path arrive all at once, after the model has finished — or
not at all, as a 504. The streaming interviewer is the core of the Practice
surface, so this is a blocker, not an inconvenience.

## Options considered

**Keep the rewrite, stop streaming.** Buffer the interviewer's turn and render
it in one go. Kills the product's central interaction.

**Firebase App Hosting / a Node server in front.** A second runtime to
operate, for a frontend that is otherwise static files. Also does not remove
the Hosting buffering for the API path.

**Browser calls Cloud Run directly.** Hosting serves only static files. The API
URL is baked into the static export at build time (`NEXT_PUBLIC_API_BASE_URL`).
Cloud Run streams natively. Cross-origin, so the API sets CORS headers for the
Hosting origin and `localhost:3000`.

## Decision

Direct. Firebase Hosting serves the static export and nothing else; the
`/api/**` rewrite is removed. FastAPI runs `CORSMiddleware` with an explicit
origin allow-list from configuration — never `*`.

Because there is no longer a Hosting proxy that needs an unauthenticated
invoker, the Cloud Run service carries **no `allUsers` binding in Phase 0**.
It is reachable by IAM invokers only (the owner via `gcloud run services
proxy`) until Identity Platform lands in Phase 1 and app-level auth exists.
An open, unauthenticated LLM endpoint is a cost trap; the budget alert only
alerts.

## What this costs

- **Two origins.** Cookies do not flow between them, so Phase 1 auth uses
  bearer tokens (Identity Platform ID tokens in an `Authorization` header),
  not session cookies. That is the right shape for a static frontend anyway.
- **CORS is ours to get right.** Preflight requests on every non-simple call;
  the allow-list is configuration that must match the deployed Hosting origin.
- **The API URL is a build input.** Changing the Cloud Run URL means a
  frontend rebuild. Custom domains later make it stable.
- **No single-origin CDN caching of API responses.** Nothing in the API is
  cacheable anyway — every response is per-session.
