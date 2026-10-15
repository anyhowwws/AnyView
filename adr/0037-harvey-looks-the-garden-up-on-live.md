# 0037 — At Panel, Harvey reads the garden's index on Live and looks entries up

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amends:** 0031 (the materials ride in each question's instruction; "a `recall` tool" rejected)

## Context

At Panel, Harvey's Live instruction carries the whole Digital Garden: up to `MAX_GARDEN_CHARS`
(20,000 characters), cut there with a note. Live re-bills the instruction on every turn with no
caching (ADR 0031), so the garden is paid for many times per question. A garden past 20,000
characters also loses its tail, so Harvey does not know about entries added later.

ADR 0031 rejected a `recall` tool because a tool call stops Harvey's speech until it returns.
But Harvey already makes one call he waits on before every follow-up: `ask_follow_up`, for
permission.

## Decision

**On Live at Panel, Harvey reads `<garden_index>`, not `<digital_garden>`.** The index is
`Repository.brain_index`, one line per live entry (label, title, and a project's or story's
result), carried on `Setup.garden_index` (capped at 12,000 characters). It covers every entry,
so nothing is cut at 20,000 characters any more.

**He opens entries through `ask_follow_up`.** The tool gains an optional `labels` (at most
three). When the follow-up is allowed, the socket looks those labels up for the signed-in user
(`Repository.garden_entries`, the same blocks `brain_context` renders) and adds them to the
result under `entries`, each capped at 1,500 characters. Harvey may then sharpen the follow-up
with what an entry says. He was already waiting on this result, so the lookup adds no pause of
its own.

**The rules sit in `LiveTurn`, with no I/O:** a lookup only at Panel with an index, only when
the follow-up was allowed, labels normalised (`[p3]` → `P3`), deduplicated and capped. An
unknown label is simply absent, so a guess finds nothing rather than an error. A failed lookup
returns no entries and never ends the question.

**Everything else is unchanged.** Planning, the planner between questions (ADR 0036) and
scoring still read `session_system`, which has the whole garden at Panel: those are text calls
whose system prefix is cached. A session started before this change has no index, and Harvey
gets the whole garden as before.

## Consequences

- Harvey's instruction at Panel shrinks from the garden's size to the index's, on every turn of
  every question.
- He knows each entry's headline walking in and its detail only when he looks it up. A
  follow-up built on a detail is now a deliberate lookup, not something he may notice in passing.
- Labels are computed per read from creation order (ADR 0011). An entry retired mid-interview
  shifts later labels, so a lookup could open a different entry from the one indexed. That is
  rare, and the result is still the candidate's own confirmed record.
- The lookup needs the database, so `ANYVIEW_FAKE_MODEL=1` without one has no garden and no
  lookup. `FakeLive` looks up the first indexed entry when it has an index.
- It is not semantic retrieval. Ranking entries by meaning is Phase 2 embeddings (ADR 0038).

## Alternatives rejected

- **A separate `recall` tool.** It would be a second blocking call, with its own pause, and
  another decision for the model.
- **Embeddings first.** They rank entries; they do not remove the need to fit the index in the
  instruction or to open an entry. Lookup by label needs no new infrastructure.
