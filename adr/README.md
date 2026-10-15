# Architecture Decision Records

Short records of decisions that were not obvious at the time they were made.

Each ADR covers one decision: the context that forced it, the options that were
genuinely considered, what was chosen, and what that choice costs. A decision
with no listed cost has not been thought about properly.

ADRs are written **as the decision is made**, not retroactively. They are
immutable once merged. If a decision is reversed, write a new ADR that
supersedes the old one and add a `Superseded by` line to the original — the
record of having been wrong is the useful part.

## Status values

- `Accepted` — in force
- `Superseded by NNNN` — replaced, see the newer record
- `Deferred` — deliberately postponed; the trigger for revisiting is stated

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-gcp-over-aws.md) | GCP over AWS | Accepted, amended by 0023 |
| [0002](0002-postgres-over-firestore.md) | Cloud SQL for PostgreSQL over Firestore | Accepted |
| [0003](0003-retrieval-over-user-authored-brain.md) | Retrieval over the user-authored brain (supersedes the earlier no-RAG decision) | Accepted, amended by 0038 |
| [0004](0004-llm-access-via-vertex-ai.md) | LLM access via Vertex AI, IAM-governed | Superseded by 0007 (model); access decision stands |
| [0005](0005-hand-rolled-sse-streaming.md) | Hand-rolled server-sent events over a streaming SDK | Accepted, amended by 0006 and 0031 |
| [0006](0006-browser-to-cloud-run-direct.md) | Browser talks to Cloud Run directly, not through Firebase Hosting | Accepted |
| [0007](0007-gemini-on-vertex.md) | Gemini on Vertex AI as the Phase 0 model | Accepted, amended by 0039 |
| [0008](0008-custom-domain-dns-in-route53.md) | Custom domain on Firebase Hosting, DNS records managed in Route 53 | Accepted, amended by 0012 |
| [0009](0009-google-sign-in-with-allow-list.md) | Google sign-in through Identity Platform, allow-listed by email | Accepted |
| [0010](0010-resume-upload-via-signed-urls.md) | Resume upload: signed URLs into Cloud Storage, PDF read by the model | Accepted |
| [0011](0011-cloud-sql-iam-auth-and-event-log.md) | Cloud SQL access: IAM authentication, one state-free password, enforced event log | Accepted, amended by 0018 |
| [0012](0012-split-dns-into-its-own-stack.md) | Split the Route 53 DNS record into its own Terraform stack | Accepted |
| [0013](0013-voice-mode.md) | Voice mode: Gemini TTS for Donna, Gemini transcription for answers | Accepted, extended by 0016; the fallback path since 0031 |
| [0014](0014-interview-setup-situation-not-sources.md) | Interview setup describes a situation, not a set of sources | Accepted, amended by 0031 |
| [0015](0015-resume-re-ingestion-deltas.md) | Re-ingesting a resume: suppress what has not changed | Accepted |
| [0016](0016-voice-first-and-the-clock.md) | Speaking by default; a per-question clock and an opener | Accepted |
| [0017](0017-discover-whole-garden-before-retrieval.md) | Discover: ask Donna about the garden, whole garden before retrieval | Accepted, amended by 0038 |
| [0018](0018-erasing-an-account.md) | Erasing an account: the one delete the event log allows | Accepted |
| [0019](0019-sectioned-extraction-and-evidenced-links.md) | Sectioned extraction, evidenced skill links, and roles that carry responsibilities | Accepted, amended by 0034 |
| [0020](0020-certifications-evidence-skills.md) | Certifications evidence skills | Accepted |
| [0021](0021-near-duplicate-skills.md) | Near-duplicate skills are folded by a checked model call | Accepted |
| [0022](0022-entries-added-by-hand.md) | Entries added by hand skip the model and the review queue | Accepted |
| [0023](0023-one-warm-api-instance.md) | One warm API instance instead of scaling to zero | Accepted |
| [0024](0024-terraform-in-ci.md) | Terraform plan on pull requests, automatic apply on main | Accepted |
| [0025](0025-saved-jobs.md) | Target jobs are saved, outside the event log | Accepted |
| [0026](0026-voice-turns-that-flow.md) | Voice turns that flow: audio from question one, the question verbatim, no review step | Accepted |
| [0027](0027-job-posting-from-a-link.md) | A job posting can come from a link, fetched by the API | Accepted |
| [0028](0028-preflight-and-fixed-lead-ins.md) | A pre-flight before question one; fixed lead-ins; one microphone per interview | Accepted, amended by 0031 |
| [0029](0029-harvey-interviews-donna-keeps-the-garden.md) | Harvey interviews; Donna keeps the Digital Garden | Accepted |
| [0030](0030-donna-speaks-in-discover.md) | Donna speaks in Discover, when asked to | Accepted, amended by 0033 |
| [0031](0031-harvey-on-gemini-live.md) | Harvey on Gemini Live: planned questions, a live conversation, follow-ups now | Accepted, amended by 0032, 0036, 0037 |
| [0032](0032-the-browser-cuts-in-on-live.md) | On Live, the browser cuts in; Harvey bridges, and closes the interview | Accepted, amended by 0035 |
| [0033](0033-discover-answers-the-way-you-asked.md) | Discover answers the way you asked: no Type / Speak switch | Accepted |
| [0034](0034-queued-ingestion-on-cloud-tasks.md) | Ingestion runs as a queued job: Cloud Tasks and a private worker | Accepted |
| [0035](0035-harveys-fixed-lines-in-his-live-voice.md) | Harvey's fixed lines in his Live voice, in several wordings | Accepted |
| [0036](0036-adaptive-planning-and-the-carry-over-note.md) | Adaptive planning between questions, and the carry-over note | Accepted |
| [0037](0037-harvey-looks-the-garden-up-on-live.md) | At Panel, Harvey reads the garden's index on Live and looks entries up | Accepted |
| [0038](0038-garden-embeddings-embedded-first.md) | Garden embeddings: four kinds, 768 dimensions, embedded before the write | Accepted |
| [0039](0039-the-report-fails-fast-and-falls-back.md) | The report fails fast and falls back; transcription moves to the fast model | Accepted |
