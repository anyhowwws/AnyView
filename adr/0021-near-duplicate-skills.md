# 0021 — Near-duplicate skills are folded by a checked model call

Status: Accepted
Date: 2026-09-30

## Context

Sectioned extraction (ADR 0019) reads each part of a resume on its own, and
each part names a skill its own way. One real resume produced "AWS" beside
"Amazon Web Services", "GCP" beside "Google Cloud", and "GitLab", "CI/CD" and
"GitLab CI/CD" from a single bullet. Code already merges exact names and
bracketed aliases ("Retrieval-Augmented Generation (RAG)" and "RAG"). The rest
needs judgement about what two names mean. Leaving them costs the user a
review queue full of cards that restate each other, and a garden where one
skill's evidence is split across two entries.

## Decision

**One call on the judgement model, after merging and before linking, proposes
groups. Code checks them and applies them.**

- Input: each skill draft's key, name and quote, and the user's confirmed
  skills by label. Output: `[{keep, merge}]`, with the schema pinning `keep`
  to this call's draft keys and garden labels, and `merge` to draft keys.
- The rules group abbreviations, vendor-prefix variants, spelling variants,
  and a tool with its practice **only when the document never uses the
  practice alone**. They never group related but different skills (AWS and
  Amazon S3, Kubernetes and Amazon EKS).
- `dedupe.checked` drops any group with an unknown key or a reused draft, and
  any group that would join two entries already in the garden. Merging
  confirmed entries is an edit to the garden, not tidying a proposal.
- The survivor keeps its own name and quote, takes the deepest self-rating,
  gains the others' links, and lists the names it absorbed in `merged_from`.
  The review queue shows "Also found as GCP, merged into this one."
- Keeping a garden label turns the draft into an update of that skill, under
  the garden's name. So "GCP" in a new resume updates a confirmed "Google
  Cloud" instead of queuing a second card.
- It runs before linking, so every link lands on the survivor.
- A failed call leaves the skills as extracted. Duplicates cost clicks, never
  the upload.

## Consequences

- One more call per upload, on the judgement model at low effort. It was about
  660 output tokens on the resume that prompted this.
- It is conservative by design. On that resume it merged "AWS" into "Amazon
  Web Services" and left "CI/CD" apart from "GitLab CI/CD", because the resume
  also uses CI/CD on its own. A merge the user disagrees with is visible in
  `merged_from`. Splitting it back out is by capture, not a button.
- `merged_from` is not stored. After confirming, the garden holds one skill,
  and the other names live only in the raw dump.

## Alternatives rejected

- **A synonym table in code.** It would be brittle and never complete, and it
  would be wrong for the part/compound case, which depends on how the
  document uses the words.
- **Merging after confirmation, in the garden.** It is the same judgement, made
  later, and it rewrites confirmed entries. Folding drafts keeps the garden's
  history plain: nothing confirmed is merged behind the user's back.
- **Asking the extraction calls to avoid duplicates.** They already are asked
  to (ADR 0019). They cannot see each other's sections.
