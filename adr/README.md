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
| [0001](0001-gcp-over-aws.md) | GCP over AWS | Accepted |
| [0002](0002-postgres-over-firestore.md) | Cloud SQL for PostgreSQL over Firestore | Accepted |
| [0003](0003-retrieval-over-user-authored-brain.md) | Retrieval over the user-authored brain (supersedes the earlier no-RAG decision) | Accepted |
| [0004](0004-llm-access-via-vertex-ai.md) | LLM access via Vertex AI, IAM-governed | Superseded by 0007 (model); access decision stands |
| [0005](0005-hand-rolled-sse-streaming.md) | Hand-rolled server-sent events over a streaming SDK | Accepted, amended by 0006 |
| [0006](0006-browser-to-cloud-run-direct.md) | Browser talks to Cloud Run directly, not through Firebase Hosting | Accepted |
| [0007](0007-gemini-on-vertex.md) | Gemini on Vertex AI as the Phase 0 model | Accepted |
| [0008](0008-custom-domain-dns-in-route53.md) | Custom domain on Firebase Hosting, DNS records managed in Route 53 | Accepted, amended by 0012 |
| [0009](0009-google-sign-in-with-allow-list.md) | Google sign-in through Identity Platform, allow-listed by email | Accepted |
| [0010](0010-resume-upload-via-signed-urls.md) | Resume upload: signed URLs into Cloud Storage, PDF read by the model | Accepted |
| [0011](0011-cloud-sql-iam-auth-and-event-log.md) | Cloud SQL access: IAM authentication, one state-free password, enforced event log | Accepted |
| [0012](0012-split-dns-into-its-own-stack.md) | Split the Route 53 DNS record into its own Terraform stack | Accepted |
| [0013](0013-voice-mode.md) | Voice mode: Gemini TTS for Donna, Gemini transcription for answers | Accepted |
