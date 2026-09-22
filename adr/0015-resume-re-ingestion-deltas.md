# 0015 — Re-ingesting a resume: suppress what has not changed

Status: accepted
Date: 2026-09-22

## Context

ADR 0014 makes the resume a property of the user, and replacing it a routine
act — a new version before each application, a bullet added after a launch.
Every replacement runs `brain/extract.propose()` into the review queue.

`propose()` already carries the user's `brain_index` and instructs the model to
set a draft's `existing` field to a label like `R2` rather than invent a
duplicate. That works, but it is **advisory and additive**: the model correctly
recognises an entity it has seen and then emits a complete draft for it anyway,
"with the full updated fields". Re-uploading a CV with one new bullet produces
thirty cards, twenty-nine of which restate what the user already confirmed.

The review queue is the whole safety property of the Digital Garden — the
reason nothing reaches the brain unconfirmed. A queue that is thirty cards of
noise gets approved in bulk without reading, and the property is gone. So the
cost of re-ingestion is not tokens. It is the user's attention.

## Decision

**Two deterministic filters. No extra model call, no diffing of document text.**

### 1. Identical text is a no-op

`raw_dumps` gains `text_sha256` (migration `003`). If an uploaded resume's
*extracted text* hashes equal to the current resume's, there is no dump row, no
proposal and no model call — the card says "No changes since your last upload."

The hash is of the extracted text, not the file bytes: the same CV exported
twice from Word differs byte for byte and extracts identically, and that is the
case worth catching.

### 2. Unchanged drafts are dropped before the user sees them

A third filter in `brain/extract.py`, beside `_keep_only_evidenced` and running
after it. For every draft that names an `existing` label, compare its fields
against the live entity:

- identical → drop the draft;
- different → keep it, and let the review queue render the differing fields as
  *before → after* rather than as a fresh card.

Comparison normalises the way `_normalise` already does (whitespace collapsed,
case-folded), compares `competencies`, `tech` and `metrics` as sets rather than
ordered lists, and **ignores `evidence`** — a new quote for the same fact is
not a change.

### 3. Absence is not evidence

A role that disappears from the new resume is **not** retired. A CV trimmed for
one application is the normal reason a job vanishes from it, and the brain does
not invent — in either direction. Retiring an entity stays a deliberate act in
`/brain`.

## Consequences

- Both filters are pure functions over a `Patch` and the current brain, in the
  file that already holds this pipeline's other filter, and are testable with
  no model and no database.
- The second upload of a slightly changed resume produces a short, readable
  queue: what is new, and what changed and how. That is the outcome this is for.
- Field-level comparison has to track the projection's schema. A new column on
  `roles` or `projects` that nobody adds to the comparison shows up as a
  silently unchanged draft. A test that walks the draft models' fields, rather
  than a hand-written field list, keeps that honest.
- The hash catches only exact re-uploads. A one-character change still costs a
  full extraction call — accepted, because it happens once per resume, not once
  per interview.

## Alternatives rejected

- **Diff the resume text and send only the changed regions to the model.**
  Cheaper per call, and genuinely tempting. Rejected on two grounds: a changed
  bullet separated from its employer heading is ambiguous, so the patch quality
  drops exactly where precision matters; and chunking raw documents is out of
  scope by the brief. The call runs once per resume replacement. The ambiguity
  is not worth the saving.
- **Let the model decide what is new**, by giving it the previous resume text
  as well as the current one. It puts a judgement call where a string
  comparison suffices, and makes the queue's contents non-deterministic across
  two runs on the same input.
- **Version resumes and diff the confirmed projections.** The event log already
  makes history recoverable; a second history of resume versions would be a
  parallel source of truth for no gain that this problem needs.
