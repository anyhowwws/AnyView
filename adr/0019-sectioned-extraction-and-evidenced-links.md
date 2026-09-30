# 0019 — Sectioned extraction, evidenced skill links, and roles that carry responsibilities

Status: Accepted
Date: 2026-09-30

## Context

A one-page resume with fourteen certifications produced three. The whole
resume produced 22 entries, and the user had to add the rest by hand, which
defeats the point of uploading it.

Nothing capped the output. The logs for that upload show the extraction call
used about 8k of its ~20k output budget and was not truncated. The model chose
to propose little, because the prompt told it to:

1. **"Prefer fewer, well-supported drafts over many thin ones."** A list of
   twelve credentials on one line reads exactly like "many thin ones".
2. **"Do not infer."** "Data Engineer, CloudOps, Developer, ML & SA Associate"
   is five credentials only if "Associate" is applied to each and "SA" is read
   as Solutions Architect. The rules said not to.
3. **One call reads everything.** A single structured call over a whole
   document skims the dense, list-shaped sections: certifications, core
   skills.

Two more problems were hidden behind the low count:

4. **The evidence filter drops drafts silently.** On the same upload it removed
   three skills because their quotes did not match the text word for word. The
   match ignored only whitespace and case, so an en dash against a hyphen was
   enough. The user never saw those drafts.
5. **Roles are bare, so projects absorb everything.** A role was company, title
   and dates. Ongoing work ("support day-2 operations", "contribute to RFQs")
   had nowhere to go but a made-up project, or nowhere at all. Skills could
   link only to projects, so a skill backed only by an ongoing responsibility
   could not be linked.

And the user wants skills tied to where they were used, which the graph and
the interviewer both need.

## Decision

### 1. What a role, a project and a story are

| | What it is | Test |
|---|---|---|
| **Role** | The job: company, title, dates, and what the candidate did **continuously** in it | It recurred for as long as the job lasted |
| **Project** | **Bounded** work inside a role: problem → action → result | It can be named, and it has an end or a deliverable |
| **Story** | A **moment** of behaviour, STAR-shaped | It is about how they acted, not what was built |

Tie-break: a bullet with a specific scope **and** a result or metric is a
project; otherwise it is a responsibility of its role. "Experience" is a
resume heading, not an entity. Resume bullets are outcomes, not stories: a
story is proposed only when the text narrates a situation and what the
candidate did in it.

Roles gain `responsibilities` (a list of short statements). Skills gain
`role_ids` beside `project_ids`. Migration `006` is additive: a `text[]`
column on `roles` and a `skill_roles` link table shaped like
`skill_evidence`. Events written before it replay unchanged: a missing field
reads as empty.

### 2. Lists are expanded

The prompt now says every item in a list is its own entry, and a shared
suffix or an abbreviation is expanded **when the section header makes it
unambiguous**: under "AWS — 12x Certified", "SA Associate" becomes "AWS
Certified Solutions Architect – Associate". The whole list line is valid
evidence for each item. "Prefer fewer" is gone.

This relaxes "never infer" in one narrow place. It is still not invention:
the credential is on the page, only abbreviated, and the user confirms every
card.

### 3. Sections, found by the model as line ranges

Long dumps (≥ 2,000 characters) are split before extraction:

1. **Segment.** The transcript goes to the fast model with numbered lines. It
   returns only `[{kind, start_line, end_line}]`, with `kind` from a fixed list:
   `experience · projects · skills · certifications · education · languages ·
   summary · other`. It never rewrites text, so every section is an exact slice
   of the original and quotes stay checkable. Code checks the result: ranges
   are clamped and made non-overlapping, and uncovered lines become `other`.
   Nothing is lost.
2. **Extract per section, in parallel.** The same extraction prompt and schema,
   plus a line saying which section this is. A thread pool, like `finish()`'s
   scoring.
3. **Merge.** Keys are renumbered across sections, and duplicates are merged by
   kind and normalised name ("Terraform" from the skills list and from an
   experience bullet become one skill). Then the existing filters run.

A dump under the threshold, a segmentation that finds fewer than two real
sections, or a segmentation call that fails, all take the single-call path
as before.

The transcription prompt also now says to keep each section's content
together and not interleave columns. Only the model reading the PDF can see
the layout.

### 4. A linking pass, and every link has a quote

After merging, one more call links skills to the roles and projects that
evidence them. Its output is `[{skill, target, evidence}]`. The evidence must be
a verbatim quote from **the target's own span** of the text: from the target's
evidence quote to the next role's or project's. Code checks that. A quote from
the skills list justifies nothing, and a link that fails the check is dropped
and logged. The rule the model is given: link only when the quote names the
skill, a product that is an instance of it (EKS for Kubernetes), or the work it
describes. The extraction call now links a skill only to an entry already in
the garden (a label like `P2`), which this dump cannot quote.

Each skill draft carries its links' quotes (`link_evidence`) to the review
queue, where each link is shown with its quote and can be removed.

### 5. The evidence check tolerates punctuation, and never deletes silently

Before comparing, dashes, bullets, middle dots and curly quotes are folded
together, and Unicode is NFKC-normalised. A draft whose quote is still not
found is **kept and flagged** (`unverified`). The queue shows it in its own
section, unticked, for the user to accept or leave.

### 6. One name, one skill

The database allows one live skill, and one live language, per name. A section
read on its own cannot know the garden already has "Terraform", so before the
queue is built a new skill or language draft named like a live one becomes an
update to it. The merge also treats a bracketed abbreviation as the same skill
("Retrieval-Augmented Generation (RAG)" and "RAG"). A name edited in the queue
that still collides is a 409 with a message, not a 500.

## Consequences

- An upload makes 3 + *n* calls instead of 2: transcribe, segment (fast
  model), one extraction per section, one link. Each call is smaller, so the
  token increase is modest. Every call still writes a usage row.
- Latency is set by the experience section's call plus the segment and link
  calls. It should land close to today's single 50-second call; the ADR
  accepts it being somewhat slower.
- Duplicate merging is by normalised name and bracketed alias. "AWS" and
  "Amazon Web Services" stay two skills, and the user merges them by hand.
- On the resume that prompted this, a recall run (`scripts/extraction_recall.py`)
  found all 14 certifications, both roles with 9 responsibilities, 8 projects
  and 36 checked skill links, for about 26k output tokens across 10 calls.
- Responsibilities carry no per-item quote. They are short restatements of
  bullets, covered by the role's evidence and confirmed by the user.
- Linking reads only this dump. A link to a project confirmed from an earlier
  dump still comes from the extraction call, unquoted, because that project's
  text is not here to quote. On re-upload, a confirmed skill keeps the links it
  had: absence is not evidence (ADR 0015).
- Certifications still link to nothing. Tying a credential to the skills it
  demonstrates is the same linking pass with a new target kind, and a separate
  decision.

## Alternatives rejected

- **Split on headings in code.** The user's own resume has "C E R T I F I C A T
  I O N S" in its text layer, and two columns interleaved so that Languages
  sits between the Experience heading and the jobs. Resumes vary too much for
  rules.
- **Segment inside the PDF transcription call.** One fewer call, but DOCX and
  pasted text would need a second segmentation path. Segmenting text keeps one
  path for every format.
- **This is chunking, which the brief rules out.** The brief rules out
  chunking raw documents *for retrieval*. Nothing here is embedded or
  retrieved: sections exist only for the length of one ingestion. ADR 0015's
  objection to splitting, that a bullet cut off from its employer heading is
  ambiguous, does not apply: an experience section keeps its roles and bullets
  together.
- **Let the extraction call keep making skill links to new drafts.** Its links
  had no quote and no check, and it made few of them.
- **A fourth configured model (Gemini 3.8 Flash) for linking.** Cheaper per
  call, but another model id to configure and confirm in Model Garden. Linking
  runs on the judgement model at medium effort until cost says otherwise.
