# AnyView

Interview prep web app with a user-confirmed "second brain". Successor to
AnyPrep (AWS); this one is on GCP. Full brief: [BRIEF.md](BRIEF.md). Decisions:
[adr/](adr/) — read 0001–0005 before touching architecture.

## Who you're working with

Cloud/Solutions Architect, strong on infrastructure, limited Python (reads it,
writes simple scripts). So:

- Explain non-obvious Python as you write it. Narrate the code, don't dumb down
  the architecture.
- Boring, readable code. No metaclasses, no heavy abstraction layers.
- Every dependency gets a written justification (a comment line in
  `pyproject.toml` / `package.json` or an ADR). None without one.
- **When a real fork in the road appears, stop and ask.** Architectural calls
  belong to the owner.
- Portfolio piece: infrastructure quality matters as much as it working.

## Stack — decided, don't relitigate

| Layer | Choice | Why (ADR) |
|---|---|---|
| Cloud | GCP | 0001 |
| API | Python 3.12, FastAPI, Cloud Run | 0001 |
| LLM + embeddings | Claude on Vertex AI via `anthropic[vertex]`; IAM only, **no API key exists anywhere** | 0004 |
| Streaming | Hand-rolled SSE (`StreamingResponse`), no streaming-UI SDK | 0005 |
| Data | Cloud SQL Postgres (db-g1-small, single zone) + pgvector, Cloud SQL connector, small pool | 0002 |
| Retrieval | One embedding per confirmed entity; hybrid filter-then-vector in one SQL | 0003 |
| Frontend | Next.js App Router, TS, Tailwind v4, shadcn/ui, Framer Motion; static export → Firebase Hosting | brief |
| Files | Cloud Storage, signed URLs (never transit the API) | brief |
| Async | Cloud Tasks | brief |
| Auth | Identity Platform (Phase 1) | brief |
| Secrets | Secret Manager, Terraform provisions the *parameter*, never the value | brief |
| IaC | Terraform, everything; console-clicked resources do not exist | brief |
| CI/CD | GitHub Actions → WIF → GCP. No stored keys. | brief |

Out of scope (brief): LangChain/orchestration libs, any vector DB, chunking raw
docs, Firestore, scraping Glassdoor/Blind, GKE/HA/multi-region, API keys.

## Layout

```
backend/src/anyview/   FastAPI app. main.py is the entry point.
backend/tests/         pytest; pythonpath=src set in pyproject.
frontend/app/          Next.js App Router. output: "export" → frontend/out.
frontend/firebase.json Hosting config; rewrites /api/** → Cloud Run anyview-api.
infra/bootstrap/       State bucket only. Local state. Run once.
infra/                 Main stack. GCS backend, bucket via -backend-config.
adr/                   Decision records, numbered. Write one *as* a decision is made.
.github/workflows/     ci.yml (lint/test/validate), deploy.yml (WIF → Artifact Registry → Cloud Run → Hosting)
```

Planned modules (not yet written — add as the phase needs them):
- `anyview/llm/adapter.py` — the only file that imports `anthropic`. `generate()`, `stream()`, `tools=`. Returns plain Python types.
- `anyview/db/repository.py` — the only file that runs SQL. App-meaningful methods (`stories_for_competency`, `roles_for_user`, `search_brain`).
- `anyview/interview/engine.py` — state machine: intake → plan → ask → answer → probe(≤2) → next | wrap → score → report. Transport-agnostic.

## Commands

```sh
# backend (from backend/)
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format .
.venv/bin/uvicorn anyview.main:app --reload --port 8080

# frontend (from frontend/)
npm install && npm run dev
npx shadcn@latest init        # one-time, when the first component is needed

# infra
cd infra/bootstrap && terraform init && terraform apply         # once
cd infra && terraform init -backend-config="bucket=<project>-tfstate"
terraform plan                                                   # terraform.tfvars auto-loads
```

`python3` on this machine is 3.9. Always use `python3.12` (Homebrew) or the venv.

## Conventions

- Model access: only `llm/adapter.py` imports `anthropic`. Local dev uses ADC
  (`gcloud auth application-default login`), never a key.
- DB access: only `db/repository.py` runs SQL. Everything else calls its methods.
- Event log is the source of truth; brain state is a projection. No write
  bypasses the log.
- Every model call writes a usage row. No exceptions, including scoring calls.
- Scoring prompts use explicit rubric anchors. Per-dimension scores only; never
  a blended number.
- If the brain lacks material, the model says so. It never invents.
- Terraform: resource-scoped IAM wherever the API allows; a project-level
  binding needs a comment saying why nothing narrower exists.
- Commits: small, focused, real messages. Push regularly.
- Never read or write `.env`, `*.tfvars`, `*.tfstate`, `*-key.json`, or anything
  under `~/.ssh`.

## Current phase

**Phase 0** — single page, resume pasted as text, company/role/seniority, five
tailored questions one at a time, streaming interviewer, per-dimension report.
Real stack, minimum surface. Cloud SQL / Storage / Tasks / Identity Platform
Terraform is **not yet written** — it arrives with Phase 1, when data is first
stored.

## Gotchas

- Cloud Run service is created with a placeholder image; `lifecycle.ignore_changes`
  on the image means Terraform never fights CI. Don't remove that.
- Firebase Hosting rewrites call Cloud Run as `allUsers`; auth is app-level.
- `gcloud config get-value project` on this machine points at a *different*
  project. Always pass `--project` or rely on `terraform.tfvars`.
- Frontend is a static export: no server components that fetch at request time,
  no `next/headers`, no route handlers. Client calls the API directly.
