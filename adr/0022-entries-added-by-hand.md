# 0022 — Entries added by hand skip the model and the review queue

Status: Accepted
Date: 2026-10-02

## Context

Until now every garden entry came from one path: the user writes or uploads
something, Donna drafts a Patch, the user confirms it in the review queue.
That path exists because a model's reading of free text needs checking. It
was also the only way to add anything, so adding a language you speak, or a
certification you already know the date of, meant writing prose for the
model, waiting for extraction, and then confirming the fields you had just
typed. The Entries view had no way to add an entry at all.

The database's provenance rule (ADR 0011) still applies: every projection row
points at the raw dump it came from and the event that wrote it.

## Decision

**`POST /brain/entities/{kind}` takes a form's fields and confirms them at
once, with no model call and no proposal.**

- The form is rendered as text ("Education added by hand", then one
  `Label: value` line per filled field) and stored as an ordinary `text` raw
  dump. That dump is the entry's provenance, and "Show source" reads like
  what the user typed. No migration: `raw_dumps.kind` keeps its CHECK, and
  `events.proposal_id` was already nullable.
- The fields become a one-draft Patch (`brain/manual.py`), validated by the
  same Draft models the extraction uses, then go through the same
  `_resolve` → `_append` → `_apply` path as a confirmed proposal, in one
  transaction with the dump insert (`Repository.add_entry`). Replay and the
  rebuild test see an ordinary `patch_confirmed` event.
- A project, story or feedback can name a role or project by label, as a
  draft can. Skill links to projects and roles are not offered on the form;
  they stay evidence-backed (ADR 0019) and editable later.
- Bad input is a 422 with a message for the user; a name clash or a label
  that resolves to nothing is a 409; either way nothing is written.

## Consequences

- Two ways in: a quick form for what the user already knows precisely, and
  capture for prose and resumes, where extraction earns its keep.
- An event with `proposal_id IS NULL` and kind `patch_confirmed` marks an
  entry added by hand. Nothing reads that distinction today.
- The form and the review queue share field definitions and validation
  (`frontend/lib/entry-fields.ts`), so the two cannot drift into asking for a
  field differently.
