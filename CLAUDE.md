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
| LLM | **Gemini 3.1 Pro (preview)** for plan/score/ideal, **Gemini 3.5 Flash-Lite** for streamed `ask` turns (0.8–1.2 s to first token; 3.8 Flash and Pro both think for 4–6 s first); Vertex AI (location `global`) via `google-genai`; IAM only, **no API key exists anywhere**. Claude returns as a second adapter once its quota is granted | 0004, 0007 |
| Embeddings (Phase 2) | Vertex `gemini-embedding-2` (listed for this project). Same project, same IAM, same identity | 0003 |
| Streaming | Hand-rolled SSE (`StreamingResponse`), no streaming-UI SDK. Browser → Cloud Run **direct** with CORS; Firebase Hosting rewrites buffer and must not carry the API | 0005, 0006 |
| Data | Cloud SQL Postgres (db-g1-small, single zone) + pgvector, Cloud SQL connector, small pool | 0002 |
| Retrieval | One embedding per confirmed entity; hybrid filter-then-vector in one SQL | 0003 |
| Frontend | Next.js App Router, TS, Tailwind v4, shadcn/ui, Framer Motion; static export → Firebase Hosting (static files only) | brief |
| Files | Cloud Storage bucket `<project>-uploads`, `uploads/<uid>/…`, V4 signed PUT URLs (never transit the API); PDF read by the model, DOCX by `python-docx` | 0010 |
| Async | Cloud Tasks | brief |
| Auth | Identity Platform: Google sign-in only, email allow-list (`ALLOWED_EMAILS`), Firebase ID token verified by `google-auth` on every `/interview/*` route | 0009 |
| Secrets | Secret Manager, Terraform provisions the *parameter*, never the value | brief |
| IaC | Terraform, everything; console-clicked resources do not exist. The `aws` provider manages **only** Route 53 records for `anyview.anyapps.cloud` | brief, 0008 |
| CI/CD | GitHub Actions → WIF → GCP. No stored keys. | brief |

Out of scope (brief): LangChain/orchestration libs, any vector DB, chunking raw
docs, Firestore, scraping Glassdoor/Blind, GKE/HA/multi-region, API keys.

## Layout

```
backend/src/anyview/   FastAPI app. main.py is the entry point.
backend/tests/         pytest; pythonpath=src set in pyproject.
frontend/app/          Next.js App Router. output: "export" → frontend/out.
frontend/firebase.json Hosting config: static files + SPA fallback only. No API rewrite (ADR 0006).
infra/bootstrap/       State bucket only. Local state. Run once.
infra/                 Main GCP stack. GCS backend, bucket via -backend-config. No AWS credentials needed (ADR 0012).
infra/dns/              The one AWS resource (Route 53 CNAME). Own state, own `aws login`. Applied rarely (ADR 0012).
adr/                   Decision records, numbered. Write one *as* a decision is made.
.github/workflows/     ci.yml (lint/test/validate), deploy.yml (WIF → Artifact Registry → Cloud Run → Hosting)
```

Backend modules:
- `anyview/config.py` — `Settings` from env vars. Plain `os.environ`, no settings library.
- `anyview/llm/adapter.py` — the only file that imports `google.genai`. `generate()` (optionally with `output_schema=` → parsed dict), `stream()`. Returns plain Python types. Every call logs one `anyview.usage` JSON line.
- `anyview/llm/fake.py` — `FakeModel`, same surface, scripted replies. Used by tests and by `ANYVIEW_FAKE_MODEL=1`.
- `anyview/interview/{models,rubric,prompts,engine}.py` — Pydantic models; rubric anchors as data; prompt builders; the state machine (intake → plan → ask → answer → probe(≤2) → next | wrap → score → report). Transport-agnostic; Phase 0 has `max_probes = 0`.
- `anyview/api/{auth,interview,uploads,sse}.py` — the sign-in gate (`current_user`), interview routes, upload tickets, and the SSE frame writer.
- `anyview/uploads/{store,extract}.py` — the upload store (GCS or in-memory) and resume → text extraction.
- `anyview/db/{connection,migrate,repository}.py` — engine (connector + IAM auth, or DATABASE_URL), numbered SQL migrations run at startup, and **the only file that runs SQL**: app-meaningful methods over an event log + projection (ADR 0011).
- `anyview/brain/{models,extract}.py` — Patch drafts with verbatim evidence, the brain as read, coverage; the dump → Patch extraction call with the evidence check.
- `backend/migrations/NNN_*.sql` — the schema. Additive only; the DB enforces provenance, append-only events, the competency taxonomy, one live skill per name.

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

# database (ADR 0011)
brew install postgresql@17 pgvector && brew services start postgresql@17   # once, for tests
createdb anyview_test && createdb anyview_dev                               # once
TEST_DATABASE_URL=postgresql+psycopg://localhost/anyview_test .venv/bin/pytest   # DB tests run instead of skipping
DATABASE_URL=postgresql+psycopg://localhost/anyview_dev .venv/bin/python -m anyview.db.migrate
GOOGLE_CLOUD_PROJECT=anyapps-anyview DB_OWNER_IAM_USER=<you> .venv/bin/python scripts/db_bootstrap.py  # once per Cloud SQL instance

# infra
cd infra/bootstrap && terraform init && terraform apply         # once
cd infra && terraform init -backend-config="bucket=<project>-tfstate"
terraform plan                                                   # terraform.tfvars auto-loads
```

`python3` on this machine is 3.9. Always use `python3.12` (Homebrew) or the venv.

## Conventions

- Model access: only `llm/adapter.py` imports `google.genai`. Local dev uses ADC
  (`gcloud auth application-default login`), never a key.
- DB access: only `db/repository.py` runs SQL. Everything else calls its methods.
- Event log is the source of truth; brain state is a projection. No write
  bypasses the log: `confirm_proposal`, `edit_entity`, `retire_entity` append an event
  and apply it in one transaction via `_apply`; `rebuild(uid)` replays with the same
  function and a test asserts equality.
- Entity labels (R1, P2, S3, K1, A1) are computed per read from creation order, never
  stored. Prompts use them; the review queue resolves them back to ids at confirmation.
- Every model call writes a usage row. No exceptions, including scoring calls.
- `finish()` scores the five answers concurrently (thread pool; the SDK client is
  thread-safe). Keep new per-answer work inside `_score_one` so it stays parallel.
- Scoring prompts use explicit rubric anchors. Per-dimension scores only; never
  a blended number.
- If the brain lacks material, the model says so. It never invents.
- Terraform: resource-scoped IAM wherever the API allows; a project-level
  binding needs a comment saying why nothing narrower exists.
- Commits: small, focused, real messages. Push regularly.
- Never read or write `.env`, `*.tfvars`, `*.tfstate`, `*-key.json`, or anything
  under `~/.ssh`.

## Current phase

**Phase 1** — auth (0009), resume upload (0010), Cloud SQL + the second brain
(0011): capture, review queue, event-sourced projection, coverage heatmap,
`/brain` screen, and the brain as an interview source. Phase 2 next: embeddings
(`gemini-embedding-2`), hybrid retrieval, Cloud Tasks for ingestion, golden
retrieval test set.

## Gotchas

- Cloud Run service is created with a placeholder image; `lifecycle.ignore_changes`
  on the image means Terraform never fights CI. Don't remove that.
- Cloud Run is publicly invokable; the sign-in gate is app-level (ADR 0009). An empty
  `ALLOWED_EMAILS` lets nobody in — check tfvars before assuming auth is broken.
- Signed URLs are signed via IAM `signBlob` as `anyview-api@…`. **`roles/owner` does not
  include `signBlob`** — a laptop needs `local_signers = ["user:you@…"]` in tfvars (grants
  `tokenCreator` on the SA) before the real API can issue upload URLs locally. `ANYVIEW_FAKE_MODEL=1`
  uses an in-memory store instead, so no bucket is needed for a local walk-through.
- Local dev without Google: `ANYVIEW_FAKE_MODEL=1` also switches the API to accept
  `Authorization: Bearer fake:<email>` (allow-list still applies), and the `web-fake` launch
  config builds the frontend with `NEXT_PUBLIC_FAKE_AUTH=dev@example.com`. Neither exists in
  a Vertex-backed build.
- Tests never call Google: `signed_in` fixture in `tests/conftest.py` swaps the verifier.
  The real one needs `GOOGLE_CLOUD_PROJECT` set (token audience).
- The Google provider is provisioned by the Firebase CLI from `firebase-auth.json`, not
  Terraform. `authDomain` is the custom domain in production.
- Phase 0 is **stateless**: the browser carries the whole session and posts it on each turn.
  No in-memory session store — Cloud Run instances don't share memory.
- Usage rows in Phase 0 are JSON log lines (`anyview.usage` logger), one per model call.
  Phase 1 moves them to a table with the same fields.
- `gcloud config get-value project` on this machine points at a *different*
  project. Always pass `--project` or rely on `terraform.tfvars`.
- Frontend is a static export: no server components that fetch at request time,
  no `next/headers`, no route handlers. Client calls the API directly.
- Repository and brain tests need `TEST_DATABASE_URL`; without it they skip (visible as
  `-rs` output), they do not fail. CI always has the pgvector service container.
- Don't run `next build` while `next dev` is up — both use `frontend/.next/` and the
  dev server then throws `__webpack_modules__[moduleId] is not a function`. Stop
  dev, build, restart dev (or `rm -rf frontend/.next`).
- Claude on Vertex needs the models enabled in Model Garden and a non-zero
  `global_online_prediction_requests_per_base_model` quota; a fresh project returns
  429 "Quota exceeded" until then (that is why Phase 0 runs Gemini — ADR 0007).
  Gemini has a default quota. The app maps a 429 to a 503 either way.
- Gemini counts thinking tokens against `max_output_tokens`; the adapter adds a
  per-effort allowance. The usage log's `thinking_tokens` shows the real spend.
- Only the `-preview` build of Gemini 3.1 Pro is reachable; bare `gemini-3.1-pro`
  is a 404. `gemini-3.8-flash` is the GA step-down for judgement calls; it cannot disable thinking, so it is not a fit for `ask`.
