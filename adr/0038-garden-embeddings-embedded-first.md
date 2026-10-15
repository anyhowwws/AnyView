# 0038 — Garden embeddings: four kinds, 768 dimensions, embedded before the write

- **Status:** Accepted
- **Date:** 2026-10-15
- **Amends:** 0003 (which kinds, "both or neither"), 0017 (the report gets the same "whole garden until it does not fit" rule)

## Context

ADR 0003 planned one embedding per confirmed story, project and achievement, searched
filter-then-vector in one SQL statement. It was deferred to Phase 2. Meanwhile interviews cut the
garden at `MAX_GARDEN_CHARS` (20,000 characters), so a large garden already loses its tail in
the report's ideal answers. ADR 0037 fixed Harvey's side with an index and lookup by label; this
fixes the report's, and lays the ground for the rest of Phase 2.

Checked on this project before building (`gemini-embedding-2`, location `global`):

- A list of texts in one request comes back as **one** vector for all of them: the model reads
  the list as the parts of a single input. Each text is its own request.
- `output_dimensionality=768` works, and vectors come back at unit length.
- `task_type` has no effect: the document, query and unset vectors were identical.
- About 1.2 s per request.

## Decision

**Kinds:** project, story, achievement and **feedback** (the owner's choice). Roles, skills,
education and languages are short, structured and better served by filters and the index.

**768 dimensions** (`EMBEDDING_DIMENSIONS`, `vector(768)`). This is the smallest size the model
recommends that keeps retrieval quality, and it stays under pgvector's 2,000-dimension limit for
an index if one is ever needed. **No vector index:** one user's garden is tens to hundreds of
rows, and an exact scan of those is faster than keeping an index up to date.

**What is embedded** (`_embedding_texts`, `EMBED_RENDER_VERSION` = 1): the entity's own block
from `brain_context`, without its label (labels move when an entity is retired), led by what it
is ("Project:", "Story:", "Credential:", "Feedback from …"), plus the role it belongs to. A role
edit therefore re-embeds its projects and stories.

**Embedded before the write** (the owner's choice), in `Repository._write`:

1. A dry run applies the write in a transaction that is rolled back, and lists every live
   entity whose text has no current vector (`_stale`, comparing a SHA-256 of the text).
2. Those texts are embedded with no transaction open, so no lock is held during a model call.
   If embedding fails, nothing has been written, and the route answers 503.
3. The write runs for real and stores the vectors in the same transaction, matched by text
   hash (a new entity gets a fresh id on each run). If the garden changed in between, so a
   text has no vector, the write is refused with 409 rather than store a wrong one.

Every stale entity is embedded, not only the ones the write touched, so a garden heals itself as
it is used. `scripts/embed_garden.py` backfills existing gardens once.

**The table is derived and outside the event log** (`entity_embeddings`, migration 010). It has
no foreign key to the entities, because `rebuild` deletes and replays the projection with the
same ids, and a cascade would drop every vector. Search joins to the live entities instead, and a
write deletes the vectors of retired ones. It is in `ERASE_ORDER`.

**Search** (`Repository.search_garden`): this user, these kinds, live only, then ordered by
cosine distance, in one statement. The vector is sent as text and cast in SQL, so no pgvector
client library is added.

**First use: the report's ideal answers, only when the garden is cut.** While the garden fits in
`MAX_GARDEN_CHARS`, the ideal answer reads all of it, which nothing nearest-first can beat (the
same rule as ADR 0017). Past that, each question's ideal answer gets its `RELEVANT_ENTRIES` (6)
nearest entries in full, plus the garden index, in place of the cut-off garden. The five
questions are embedded in one call before scoring (`call="embed_query"`). If search fails, the
report reads the garden as before.

## Consequences

- Each garden write that changes an embedded entity adds embedding requests before it saves:
  about 1–2 s for an edit, a few seconds for confirming a resume's proposal (up to 8 requests run
  at once). Each request writes a usage row.
- The first write after deploy embeds the whole existing garden unless the backfill has run.
  Run `scripts/embed_garden.py` after the deploy.
- If the embedding model is down, the garden cannot be changed. This is the cost of "embed
  first": no entity is ever live without its vector.
- Changing `_embedding_texts` means bumping `EMBED_RENDER_VERSION`. Every entity is then stale,
  and the backfill re-embeds them.
- **Not done:** the golden retrieval test set (deferred by the owner), Discover's search past
  `RETRIEVAL_THRESHOLD_CHARS`, and using search to pick entries for the planner (ADR 0036).

## Alternatives rejected

- **Save first, embed after** (a missing vector until it is filled in). Rejected by the owner:
  search would miss an entity until then.
- **Embedding inside the write's transaction.** That holds the user's row lock for the length of
  a model call.
- **A pgvector client library.** Casting a text literal is all the queries need.
