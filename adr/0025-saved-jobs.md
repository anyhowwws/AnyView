# 0025 — Target jobs are saved

- **Status:** Accepted
- **Date:** 2026-10-13
- **Amends:** 0014 ("One target job, two ways in"), migration `003`'s note that a job
  description "is read, shown to the user and carried in the session, not remembered"

## Context

ADR 0014 made the resume a property of the user and left the job a
per-interview input. That fits one run per job. It does not fit how people
practise. A candidate keeps preparing for the same posting across several
sessions and difficulties, and each time they had to upload the file again,
wait for the parse call, and redo any corrections they had made to the company,
role or seniority Donna read.

## Decision

**Every job an interview is started for is saved, and the setup form opens on
the most recently used one.**

### A plain table, outside the event log

`saved_jobs` (migration `008`) holds company, role, seniority, the
`job_description` the prompt carries, the form's structured `fields` (team,
responsibilities, must-haves, nice-to-haves, one item per line), a `source`
of `upload` or `manual`, and `last_used_at`.

It is **not** event-sourced. ADR 0011's event log exists so that every fact in
the Digital Garden has provenance and the projection can be replayed. A saved
job is not a fact about the candidate. It is a setting for practice, like
`users.resume_dump_id`. Edits are an `UPDATE` and removal is a `DELETE`. The
table is in `ERASE_ORDER` (ADR 0018).

### Saved on Start, not by a checkbox

`SetupInput` gains an optional `job` block: `{id, source, fields}`. Once
planning succeeds, `/interview/start` saves it. Saving is best effort: a
failure is logged and the interview goes on.

Which row it lands in, in order:

1. `job.id`: the saved job the user picked, scoped to their own rows. Any
   corrections they made in the form are written back to it.
2. A saved job holding exactly this `job_description` (hash, then text).
3. A saved job with no description and the same company, role and seniority.
4. Otherwise, a new row.

So practising one posting ten times leaves one entry, not ten. Nothing is
stored without the user knowing: the form says "saved for next time when you
start", and every saved job has a Remove.

### Editing depends on how the job came in

- **Uploaded posting:** the posting's text is what the prompt carries, and it
  is read-only. Company, role and seniority can be corrected, and the
  corrections are saved. The parsed fields show as chips.
- **Filled in:** `job_description` is rebuilt from the fields by `formatJob()`
  every time, so the fields are the job, and they stay editable.

### A known posting skips the parse

`/interview/job/parse` looks the extracted text up in `saved_jobs` first. On a
match it returns the saved job (`saved_job` on `JobDocument`) and makes no
parse call. The form switches to that saved job, with last time's
corrections. Extracting a PDF's text still costs one call, because the text is
the key.

## Consequences

- Without a database nothing is saved, `GET /interview/jobs` is empty, and
  the form behaves as it did under ADR 0014.
- Reports do not point at a saved job yet. Comparing attempts against one job
  across difficulties is the natural next step, and the `id` is already there
  to hang it on.
- A user who uploads a slightly different version of the same posting gets a
  second entry. Matching on near-identical text was not worth the ambiguity;
  Remove covers it.
