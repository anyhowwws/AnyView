# 0003 — Retrieval over the user-authored brain

- **Status:** Accepted
- **Date:** 2026-09-16
- **Supersedes:** the AnyPrep-era decision to do no retrieval and load the whole
  profile into every prompt.

## Context

AnyPrep held a resume and a handful of testimonials — small enough to paste
into every prompt. That "no RAG" decision was correct for that corpus.

AnyView's brain is different in two ways:

1. **It is unbounded.** Every brain dump and every confirmed interview gap adds
   to it. There is no upper limit on the number of stories.
2. **It is user-authored and user-confirmed.** Nothing enters the brain without
   review. The corpus is clean, structured, and already split into meaningful
   units (a Story, a Project). This is not a pile of PDFs.

Loading everything into every prompt stops being possible; naive chunk-and-
embed of raw documents would throw away the structure the review queue worked
to create.

## Options considered

**Keep no-RAG, load everything.** Breaks at a few dozen stories. Also makes
cost per interview grow linearly with brain size.

**Chunk raw dumps and embed the chunks.** The standard RAG recipe. Wrong here:
raw dumps are the *unedited* input, not the truth. Retrieval would surface
unreviewed, possibly retracted text beside the confirmed entity derived from it.

**One embedding per confirmed entity.** Each Story / Project / Achievement gets
a single embedding generated from a canonical text rendering of the entity.
Retrieval returns whole entities with their IDs, which the ideal-answer prompt
can cite.

## Decision

One embedding per confirmed Story, Project, and Achievement, generated from a
canonical rendering at confirmation time. Raw dumps are read once at ingestion
and are never a retrieval target.

Query is hybrid, in one SQL statement: structured filters first (competency
tags, entity type, date range, employer), then pgvector similarity on the
filtered set.

A compact **brain index** — one line per entity (ID, type, title, competency
tags) — is always loaded into the prompt and cached with the system prompt, so
the model can reason about what the brain *does not* contain and say so rather
than invent.

A golden test set of twenty question → expected-story pairs runs as an
automated test so retrieval regressions are caught in CI.

## What this costs

- **Embeddings are stale if the canonical rendering changes.** Any change to
  how an entity renders to text requires re-embedding every entity. The
  rendering function is versioned and the version is stored beside the vector.
- **The brain index grows.** One line per entity is cheap but not free; at
  thousands of entities it will need its own pruning strategy. Not a Phase 2
  problem.
- **Two paths to keep in sync.** The event log is the source of truth; the
  projection and the embeddings are both derived. A confirmed patch must update
  both or neither.
