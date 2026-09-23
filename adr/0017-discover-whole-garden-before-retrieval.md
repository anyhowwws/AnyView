# 0017 — Discover: ask Donna about the garden, whole garden before retrieval

Status: Accepted
Date: 2026-09-24

## Context

The Digital Garden can be seen as a graph, a list of entries, or a coverage
heatmap. None of these answers a plain question like "Which projects have I done
with AWS Bedrock?" For that you have to already know where to look. Discover
adds a fourth view: a chat with Donna about your own confirmed record.

ADR 0003 plans retrieval (one embedding per entity, filter-then-vector in one
SQL) for when a garden no longer fits in a prompt. Phase 2 has not started. The
database has the `vector` extension but no embedding columns. So Discover
either waits for Phase 2 or works without it.

Three facts decide it:

1. **Gardens are small.** `brain_context()` gives about 80 tokens per entry.
   A full 20-year career, carefully captured, comes to about 300–500 entries,
   or 30–50k tokens. Gemini accepts 1M. Resumes add little once the first is
   in: re-ingestion only queues what changed (ADR 0015).
2. **The motivating question lists everything of a kind.** "Which projects…"
   needs every match. Top-k similarity returns the closest few and can quietly
   miss a project where Bedrock is one item in `tech`. Reading the whole garden
   does not.
3. **The prefix is stable.** Within a conversation the garden does not
   change, so Gemini's implicit cache serves it at a discount on every turn
   after the first.

## Options considered

**Build Phase 2 retrieval first.** Embeddings, re-embedding on edit, a
retrieval query, a golden test set. All of it before the first answer, and
worse at "list them all" questions than reading everything.

**Whole confirmed garden in the system prompt.** No new infrastructure, exact
on list questions, and cheap thanks to caching. It stops being right somewhere
past ~100k tokens, where prompts get slower and the model gets less reliable at
spotting one detail.

**Tool calling (the model asks for `search_brain(tech="Bedrock")`).** The best
long-term shape for list questions over a large garden. It needs tool support
in `llm/adapter.py`, which only streams text today. Not justified at the
current size.

## Decision

**The whole confirmed garden, behind one seam.**

- `POST /brain/discover` streams SSE (ADR 0005): `token` frames, then one
  `citations` frame, then `done`.
- The system prompt is Donna's rules followed by `<digital_garden>` from
  `brain_context()`: confirmed entries only. No pending proposals, no raw dumps
  (ADR 0003's rule for what counts as truth).
- `brain/discover.py:discover_context()` is the one place that decides what
  Donna reads. Today it returns everything and logs a warning past
  `RETRIEVAL_THRESHOLD_CHARS` (400k characters, about 100k tokens). Phase 2
  changes its body, not its callers.
- **Model:** the fast model (Flash-Lite), as for `ask`. Discover is lookup,
  not judgement, and the Pro model spends 4–6 s thinking before its first
  token.
- **Stateless** (like Phase 0): the browser keeps the conversation and posts
  the last turns with each question; the server sends the most recent 12. No
  conversation table.
- **Read-only.** Donna cannot add to the garden. Capturing stays in the
  capture box → review queue. If guided capture from chat is ever added, it
  sends only the user's own messages to `POST /brain/dumps`. Donna's words must
  never become an entry's evidence.
- **Citations are checked.** The model cites labels (`[P3]`). The server
  resolves them against the user's label map and drops any that do not exist,
  so an invented `[P9]` is never rendered as a link.

## When to revisit

- A garden's context crosses `RETRIEVAL_THRESHOLD_CHARS` (the warning), or the
  `discover` usage rows show `input_tokens` regularly past ~100k.
- Answers miss entries that are in the garden. That is a quality signal for
  the Pro model, or for retrieval with a structured filter step.

## What this costs

- **Every turn pays for the whole garden.** Caching discounts the repeated
  part; it does not remove it. The cost grows with garden size, which is what
  the threshold watches.
- **Conversations are not kept.** Reloading the page loses them. Keeping them
  needs a table, a retention period, and a decision on whether what you say in
  a chat can ever count as evidence.
- **History rides in the user turn.** The adapter has one system and one user
  message, so earlier turns are flattened into text. This is fine for a
  handful of turns, and it keeps the garden as the cacheable prefix.
- **A second prompt reads the garden.** Discover's rules and the interview's
  garden rules (ADR 0014) must not drift. For example, a label format change
  touches both.
