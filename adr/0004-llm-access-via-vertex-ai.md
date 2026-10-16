# 0004 — LLM access via Gemini Enterprise Agent Platform, IAM-governed

- **Status:** Superseded by 0007 (model choice); the IAM-governed access decision stands
- **Date:** 2026-09-16

## Context

AnyPrep reached Claude through the Anthropic API with an API key. It recorded
what that gave up: IAM-governed access, platform invocation logging, data
staying inside the account boundary, and unified billing. That ADR set a
migration trigger for moving to a governed path. This project starts on the
governed path.

## Options considered

**Anthropic API directly.** Simplest SDK usage. Requires an API key that must
be stored, rotated, and guarded; access control lives outside the cloud IAM
model; resume text — personal data — leaves the project boundary to a
third-party endpoint.

**Gemini Enterprise Agent Platform (Claude on Agent Platform).** Same models, same official `anthropic` Python
SDK via its `AnthropicVertex` client. Authentication is the Cloud Run service
account's IAM role (`roles/aiplatform.user`). Requests are logged by the
platform. Spend is a line in the GCP bill. No key exists anywhere.

## Decision

All model calls go to Gemini Enterprise Agent Platform using the official Anthropic SDK's Agent Platform
client. Model access is governed entirely by IAM on the Cloud Run service
account. There is no API key, no direct Anthropic API path, and no environment
variable that could hold one.

All model interaction sits behind one thin adapter module exposing
`generate()`, `stream()`, and a `tools` parameter, returning plain Python
types. No SDK object leaks into application code. The adapter is an indirection
layer, not a framework — it exists so that the SDK can be swapped, not so that
prompts can be composed.

Text embeddings come from the same Agent Platform endpoint under the same identity.

Every model call writes a usage row (session, tokens in/out, cached tokens,
model) so Agent Platform token spend is tracked as its own line item and cost per
interview session is a query, not a guess.

## What this costs

- **Region and model availability.** Claude on Agent Platform is available in specific
  regions; the model ID and region are Terraform variables, not constants, so a
  move is a variable change.
- **Local development needs ADC.** `gcloud auth application-default login`
  replaces "paste a key in .env". Slightly more setup; considerably safer.
- **Agent Platform quotas are per-project.** A separate project for a second
  environment means separate quota requests. Acceptable for a single-owner tool.
