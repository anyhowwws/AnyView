# 0007 — Gemini on Gemini Enterprise Agent Platform as the Phase 0 model

- **Status:** Accepted
- **Date:** 2026-09-16
- **Supersedes:** 0004 (the *which model* part; the *how access is governed* part
  stands unchanged)
- **Amendment (2026-09-16):** streamed interviewer turns (`ask`) run on
  `gemini-3.5-flash-lite`. Measured time to first token on the real prompt:
  Pro 5.6 s (~450 thinking tokens even at `low`), 3.8 Flash 4 s (thinking
  cannot be disabled; one 148 s hang seen), Flash-Lite 0.8–1.2 s with
  identical output quality. Judgement calls stay on Pro. The prompt cache was
  not engaging anyway (prefix below the implicit minimum), so the single-model
  argument cost nothing to give up. `fast_model_id` in Terraform.

## Context

ADR 0004 chose Claude on Gemini Enterprise Agent Platform. The first real call from the project
returned `429 Quota exceeded for global_online_prediction_requests_per_base_model:
anthropic-claude-opus` — a fresh GCP project has a zero quota for Anthropic
partner models until they are enabled in Model Garden and a quota increase is
granted. Gemini models are Google's own and carry a default quota on day one:
`gemini-3.1-pro-preview`, `gemini-3.8-flash` and `gemini-3.7-flash` all
answered immediately from the same project and the same IAM role.

The owner wants to start building and evaluating now, and to try both model
families once the Claude quota is in place.

## Options considered

**Wait for the Claude quota.** Blocks every end-to-end run on a support ticket
of unknown duration. Nothing else in Phase 0 depends on which model answers.

**Gemini on Agent Platform.** Same project, same `roles/aiplatform.user`, same platform
invocation logging, same data boundary — every governance argument in 0004
applies unchanged. Different SDK (`google-genai`), different caching model
(implicit, no breakpoints), thinking tokens billed as output, a `thinking_level`
knob instead of `effort`.

**Direct Anthropic API with a key.** Ruled out by the brief and by 0004; not
reconsidered.

## Decision

Phase 0 runs on **`gemini-3.1-pro-preview`** for `plan`, `score`, and `ideal`,
and the same model at `thinking_level: low` for `ask`. `gemini-3.8-flash` is
the documented cost step-down (a one-line `model_id` change). The only GA Pro
tier reachable today is the preview build; the `-preview` suffix is the reason
`model_id` is a Terraform variable and not a constant.

`llm/adapter.py` is rewritten for the Google Gen AI SDK. Its public surface —
`Model`, `Reply`, `Usage`, `ModelError`, `generate()`, `stream()` — is
unchanged, so the engine, prompts, rubric, API layer, tests, and frontend did
not change. That was the point of the adapter.

Claude returns when the quota does: a second adapter class behind the same
`Model` protocol, selected by configuration, so both families can be compared
on the same rubric with the same usage log.

## What this costs

- **Caching is implicit.** Anthropic's explicit `cache_control` breakpoint
  becomes Gemini's automatic prefix cache. It only engages above a
  model-dependent minimum prefix length and is reported, not controlled. The
  usage log's `cache_read` field shows whether it is happening; if a session's
  hit rate is poor, an explicit `caches.create` per session is the next step.
- **Thinking is billed as output and counts against `max_output_tokens`.** The
  adapter adds a per-effort allowance on top of the caller's answer budget, and
  logs `thinking_tokens` separately so the cost line item stays honest.
- **A preview model ID.** Google may rename or retire it. The variable makes
  that a plan, not a code change.
- **Two SDKs' worth of adapter knowledge to keep.** Accepted — the comparison
  is something the owner explicitly wants.
