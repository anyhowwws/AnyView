# 0023 — Entries show their origin and quote, not their whole source

Status: Accepted
Date: 2026-10-02

## Context

Every garden card had a "Show source" link that printed the entire raw dump
under the card. For a resume, that meant the same few pages of extracted
text repeated under every role, skill and certificate it produced. It did
not show *which* part of the document justified the entry, because entries
did not keep that. The draft's evidence quote was checked at extraction
(ADR 0019) and dropped at confirmation.

## Decision

**Keep each entry's quote, and lead with where the entry came from.**

- Migration 008 adds a nullable `evidence` column to each entity table.
  `_resolve` puts the draft's quote in the `patch_confirmed` payload and
  `_apply_patch` stores it, so replay and rebuild reproduce it. Events
  confirmed earlier carry none and replay with NULL. Edits do not touch it.
  A later patch that updates an entry replaces it with the new quote.
- `Repository.brain` adds three read-only fields to each entry's
  `Provenance`: `origin` (`resume`, `file` for an uploaded image or diagram,
  `capture`, or `manual` for a dump no proposal came from, ADR 0022),
  `added_on`, and `evidence`. A hand-added entry's "quote" is its own form,
  so it is not returned.
- The card shows one quiet line ("From your resume · 2 Oct 2026"). It opens
  to the quote, and from there to the whole document in a side panel,
  scrolled to the quote and highlighted. The match ignores case and line
  breaks, which PDF extraction moves. Hand-added entries show the line only.

## Consequences

- Entries confirmed before 008 say where they came from but have no quote.
  Re-uploading the same resume does not backfill it: unchanged drafts are
  suppressed (ADR 0015).
- The full dump is fetched only when the user asks for the document.
