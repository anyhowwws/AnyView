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
| [0004](0004-llm-access-via-vertex-ai.md) | LLM access via Vertex AI, IAM-governed | Accepted |
| [0005](0005-hand-rolled-sse-streaming.md) | Hand-rolled server-sent events over a streaming SDK | Accepted |
