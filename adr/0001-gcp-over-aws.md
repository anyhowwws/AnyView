# 0001 — GCP over AWS

- **Status:** Accepted
- **Date:** 2026-09-16
- **Amendment (2026-10-08):** "Cold starts" below no longer holds. Cold starts
  hurt (a ~66 s boot during which Cloud Run refused requests), so the API keeps
  one warm instance. See 0023.

## Context

AnyView is the successor to AnyPrep, which was built on AWS (Lambda Function
URLs with response streaming, DynamoDB, S3, Cognito, Terraform). That project
surfaced three problems that were not about the product but about the platform
it sat on:

1. **Ungoverned model access.** Bedrock was unusable on the account, so model
   calls went to the Anthropic API directly with an API key held in SSM. Access
   control for the most sensitive dependency in the system lived outside IAM.
2. **Streaming without an abstraction.** Lambda response streaming works, but
   it is a Lambda-specific mechanism; the code that streamed tokens to the
   browser was coupled to the runtime.
3. **Embeddings from a different provider.** Bedrock's absence meant any
   embedding model would have been a second vendor with a second credential.

Both clouds are live for the owner. The choice is expensive to reverse, so it
is recorded here with the alternative.

## Options considered

**AWS (stay).** Familiar. Lambda + DynamoDB is cheap at zero traffic. But
the three problems above remain, and the fix for the first — Bedrock — was
rejected by AWS support on the account in question.

**GCP.** Claude models are available on Vertex AI in the owner's project with
no account-level gating. Access is an IAM role on a service account, invocation
logging is a platform feature, and request data stays inside the project
boundary. Cloud Run gives a plain HTTP server (FastAPI) where streaming is just
a chunked response, so no runtime-specific streaming code. Text embeddings are
available from the same Vertex endpoint under the same identity.

## Decision

Build AnyView on GCP: Cloud Run for the API, Cloud SQL for PostgreSQL with
pgvector for data (see 0002), Cloud Storage for uploads, Cloud Tasks for async
ingestion, Identity Platform for auth, Secret Manager for any secret, Firebase
Hosting for the frontend, all provisioned by Terraform, with GitHub Actions
authenticating through Workload Identity Federation. Direct Claude access on
Vertex removes the API-key problem outright (see 0004).

## What this costs

- **A second cloud to keep sharp on.** The owner's depth is AWS. Every GCP
  primitive (IAM conditions, WIF, Cloud SQL connector, Cloud Run revisions) is
  learned on this project. That is partly the point — it is a portfolio piece —
  but it is real time.
- **Cloud SQL has a floor.** A db-g1-small instance costs money while idle in
  a way DynamoDB on-demand does not. Mitigated by the smallest tier, single zone,
  no HA, and a USD 50 budget alert from day one.
- **Cold starts.** Cloud Run scales to zero; the first request after idle pays
  a container start plus a Cloud SQL connection. Acceptable for a single-user
  practice tool; min-instances stays at zero until it hurts.
- **Portability of AnyPrep code is low.** The adapter and state-machine ideas
  carry over; the Lambda handler and DynamoDB access do not.
