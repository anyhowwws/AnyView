# 0014 — Interview setup describes a situation, not a set of sources

Status: accepted
Date: 2026-09-22

## Context

The setup form asked three questions that were really one. A toggle chose
between "Upload a resume", "My brain" and "Paste text"; `SetupInput` enforced
exactly one of `resume` / `resume_object` / `use_brain`; and when the brain was
chosen, `resolve_setup` rendered it *into* the `resume` field and set a
`source: "resume" | "brain"` flag so the prompt could explain the substitution.

That flag is the tell. There is one slot for "what Donna reads about you" and
the form kept swapping what sits in it. Two things are wrong with that:

1. It asks the candidate to make a modelling decision they have no basis for.
   Nobody preparing for an interview knows whether their resume or their
   Digital Garden is the better prompt input. It is our question, asked in
   their form.
2. It treats the resume and the garden as **alternatives**, when they are
   different objects. The resume is the artefact the interviewer actually
   received. The garden is everything the candidate knows that the interviewer
   did not get. An interview is precisely the gap between the two.

Two smaller asymmetries came along with it. The job description — the document
that decides what the role even is — was a paste-only textarea, while the
resume got the whole signed-URL upload path of ADR 0010. And company, role and
seniority were typed by hand even when the job description states all three on
its first line.

And there was no notion of difficulty. Every interview probed the same way,
which meant it could not simulate either the recruiter screen at the start of a
process or the panel at the end.

## Decision

**The setup form describes a situation: a candidate, a job, and a room.**

### One resume, on file

The resume stops being a per-interview choice and becomes a property of the
user. `users.resume_dump_id` points at a row in `raw_dumps` (migration `003`),
which already holds the extracted text and the Cloud Storage object name. The
form shows a confirmation card — filename, upload date, "Replace", "View
extracted text" — instead of an upload zone, once there is one on file.

A pointer column rather than "the most recent dump of a resume kind wins":
adding a second resume to the garden as raw material must not silently change
what interviewers see.

Because the extracted text is stored, **a second interview does not re-extract
the PDF.** The model call in `pdf_to_text` happens once per resume, not once
per interview. Without a database configured, the flow still works — it simply
asks for the file every time, as it does today.

### One target job, two ways in

The job description gets the same upload path as the resume: same `POST
/uploads` ticket, same `pdf_to_text` / `docx_to_text`, no new plumbing. The
extracted text becomes `job_description`, and one structured call parses
company, role, seniority and requirements out of it to **pre-fill the form
fields for confirmation** — the same dump → proposal → confirm shape the
Digital Garden already uses. Nothing reaches the prompt that the user has not
seen.

Filling it in by hand uses the Garden's "Formatted" capture pattern: a
structured fieldset, and a `formatJob()` twin of `formatCapture()` that folds
the fields into the same `job_description` string. One target job comes out of
either path.

### Difficulty decides what the interviewer knows

| Level | Questions planned from | The room |
|---|---|---|
| **Recruiter screen** | The resume only. The JD ranks which resume items matter, nothing more. | Everything is answerable from the page in front of them. |
| **Hiring manager** | Resume + JD. Questions may target a requirement the resume does not evidence. | "The role needs X and I don't see it — talk me through that." |
| **Panel** | Resume + JD + the confirmed Digital Garden. | They have done their homework: read your writing, talked to a reference, found the work that never made the CV. |

`Setup` gains `difficulty` and an optional `garden: str | None` **beside**
`resume` rather than inside it, and `source` is deleted. `session_system()`
gains a difficulty clause and, at Panel, a `<digital_garden>` block.

### The ideal answer always reads the garden

`ideal_user()` no longer says "using only facts that appear in the resume".
The ideal answer is coaching, not simulation — the candidate's own confirmed
record is exactly the right material, and citing `[S3]` tells them they already
had the story and did not reach for it. Bracketed placeholders remain for
details neither source holds.

### Replacing the resume always proposes to the review queue

The "Also add this resume to my brain" checkbox goes. Replacement always runs
`brain/extract.propose()` and lands drafts in the review queue, where nothing
is saved until confirmed — so the safety property is unchanged and one control
disappears from the form. What keeps that queue readable is ADR 0015.

## Consequences

- At Panel, the session payload carries both the resume and the garden, and
  Phase 0 posts the whole session every turn (ADR 0005). The garden render is
  capped, and Panel is the only level that pays this.
- `Report.source` becomes `difficulty` plus a `garden_used` flag. A report now
  records the room it was conducted in, which is the thing worth comparing two
  attempts on.
- A Panel interview against an empty garden is a Hiring manager interview with
  a nudge to go fill the garden. That is the intended on-ramp, not a failure.
- The resume card needs a database. Without one, the setup form falls back to
  asking for the file each time; nothing else changes.
- One new model call in the setup path — parsing an uploaded JD — offset by one
  removed: resume extraction no longer repeats per interview.
- Difficulty changes **sourcing only**. `MAX_PROBES` stays 0 until Phase 3, and
  Donna's manner is constant across levels. Panel is harder because of what it
  asks, not because it interrupts.
- `session_system()` stays stable within a session, so the ADR 0004 cache
  prefix still holds; the garden block is part of the cached prefix at Panel.

## Alternatives rejected

- **Keep the three-way toggle.** It is a question about our data model wearing
  the costume of a question about the candidate.
- **Keep the garden candidate-side at every level** — Donna never reads it,
  and harder only means probing JD gaps. Cleaner as a simulation, but it caps
  how hard the hardest level can get, and real senior interviews genuinely do
  arrive knowing more than the CV.
- **Difficulty as a tone knob** (a terser, more sceptical Donna at the same
  questions). Theatre. The thing that makes an interview hard is what it asks
  about, not how briskly.
