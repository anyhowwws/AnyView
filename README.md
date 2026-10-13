# AnyView

Interview preparation web app with a "second brain".

AnyView keeps a structured, user-confirmed knowledge base of a job-seeker's
career — roles, projects, STAR stories, skills, achievements, education,
languages and feedback from others — built from free-text brain dumps, uploaded
resumes and entries added by hand. Nothing the model extracts enters the brain
until the user confirms it, and every entry keeps the verbatim quote it came
from.

On top of that brain it runs spoken mock interviews with **Donna**, the
interviewer: tailored to a target job (company, role, seniority, or an uploaded
job description), at one of three difficulties, timed per question, then scored
per rubric dimension with an ideal answer built only from the user's own
material — so gaps in the brain show up instead of being invented.

The full product brief is in [BRIEF.md](BRIEF.md). Architecture decisions are in
[adr/](adr/) — start with 0001–0005.

## What it does today

**The brain** (`/brain`, the garden)

- **Capture** — paste a brain dump or upload a resume (PDF or DOCX). The
  resume is split into sections, each read in parallel, near-duplicate skills
  folded together ("GCP" / "Google Cloud"), and skills linked to the roles,
  projects and certifications that evidence them (ADR 0019–0021). Progress
  streams to the screen while it runs.
- **Review queue** — every extracted entry arrives as a draft with its source
  quote. The user confirms, edits or discards it; a draft whose quote cannot be
  found in the source is flagged, never silently dropped. Re-uploading a resume
  only queues what changed (ADR 0015).
- **Add by hand** — a form per entry kind; no model call, no review step
  (ADR 0022).
- **Coverage heatmap and graph** — which competencies the brain can back up,
  and how entries connect.
- **Discover** — ask Donna questions about your own garden; answers stream
  with citations to the entries they used (ADR 0017).

**The interview** (`/practice`)

- **Setup describes a situation** (ADR 0014): the target job, the resume on
  file, and a difficulty — *recruiter screen*, *hiring manager*, or *panel*.
  Difficulty decides what the interviewer knows; only a panel sees the garden.
- **Saved jobs** — a job description is uploaded once and practised again
  from a list (ADR 0025).
- **Voice first** (ADR 0013, 0016) — Donna speaks (Gemini TTS) and the answer
  is recorded in the browser and transcribed. She opens with "tell me about
  yourself"; each question has its own time budget, and ten seconds of silence
  makes her speak up. Text mode remains as a fallback.
- **Report** — five answers scored concurrently against explicit rubric
  anchors, per dimension only (never a blended number), each with an ideal
  answer drawn from the brain. Results stream in as each answer is scored.

**The account** (`/account`) — erase everything: files, then every row of the
user's event log (ADR 0018).

## Architecture

| Layer | Choice | ADR |
|---|---|---|
| Cloud | GCP | 0001 |
| API | Python 3.12, FastAPI, Cloud Run (one warm instance) | 0001, 0023 |
| Models | Gemini on Vertex AI via `google-genai`, IAM only — **no API key exists anywhere**. A Pro model plans and scores; a Flash-Lite model streams the interviewer's turns | 0004, 0007 |
| Voice | Gemini TTS on Vertex; answers transcribed by the same model family | 0013, 0016 |
| Streaming | Hand-rolled server-sent events; browser talks to Cloud Run directly | 0005, 0006 |
| Data | Cloud SQL Postgres + pgvector, IAM database auth. Brain state is a projection of an append-only event log the database itself enforces | 0002, 0011 |
| Files | Cloud Storage, V4 signed upload URLs — files never pass through the API | 0010 |
| Auth | Identity Platform, Google sign-in, email allow-list | 0009 |
| Frontend | Next.js App Router (static export), TypeScript, Tailwind, shadcn/ui → Firebase Hosting | — |
| IaC | Terraform for every resource; Route 53 DNS record in its own stack | 0008, 0012 |
| CI/CD | GitHub Actions → Workload Identity Federation → Artifact Registry / Cloud Run / Hosting. No stored keys | — |

Every model call writes one usage record (tokens, thinking tokens, latency).

## Layout

```
backend/     Python 3.12 · FastAPI · runs on Cloud Run
  src/anyview/llm/        the only code that imports google.genai (+ a scripted fake)
  src/anyview/interview/  state machine, prompts, rubric, voice
  src/anyview/brain/      extraction pipeline, evidence checks, Discover, manual entries
  src/anyview/db/         connection, migrations, and the only code that runs SQL
  src/anyview/api/        routes, sign-in gate, SSE writer
  migrations/             numbered SQL, additive only
  scripts/                db_bootstrap.py, extraction_recall.py
frontend/    Next.js · TypeScript · Tailwind · static export to Firebase Hosting
infra/       Terraform — main GCP stack; bootstrap/ (state bucket); dns/ (Route 53)
adr/         Architecture decision records
.github/     ci.yml — lint, test, validate; on main: build and deploy via WIF
```

## Running locally

### Prerequisites

Python 3.12, Node, and Postgres 17 with pgvector (for the brain and the
database tests):

```sh
brew install postgresql@17 pgvector && brew services start postgresql@17
createdb anyview_test && createdb anyview_dev
```

### Backend

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
DATABASE_URL=postgresql+psycopg://localhost/anyview_dev .venv/bin/python -m anyview.db.migrate
```

Test and lint (database tests skip without `TEST_DATABASE_URL`; CI always runs
them):

```sh
TEST_DATABASE_URL=postgresql+psycopg://localhost/anyview_test .venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

### Walk through it without Google

`ANYVIEW_FAKE_MODEL=1` swaps every model call for scripted replies, uses an
in-memory file store, makes TTS return silence of a realistic length, and
accepts a fake sign-in token. No bucket, no tokens, no Google account:

```sh
# backend
cd backend && ANYVIEW_FAKE_MODEL=1 GOOGLE_CLOUD_PROJECT=anyapps-anyview \
  ALLOWED_EMAILS=dev@example.com \
  DATABASE_URL=postgresql+psycopg://localhost/anyview_dev \
  .venv/bin/uvicorn anyview.main:app --port 8080

# frontend
cd frontend && npm install && NEXT_PUBLIC_API_BASE_URL=http://localhost:8080 \
  NEXT_PUBLIC_FAKE_AUTH=dev@example.com npm run dev    # http://localhost:3000
```

Add `ANYVIEW_FAKE_DELAY_S=2` to the backend to slow each fake call down so the
progress views can be seen. These are also the `api-fake`, `api-fake-slow` and
`web-fake` configurations in `.claude/launch.json`.

### Against real Vertex AI

Model calls use your Application Default Credentials — there is no API key:

```sh
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>
```

Issuing signed upload URLs from a laptop needs `local_signers =
["user:you@…"]` in `terraform.tfvars` (`roles/owner` does not include
`signBlob`). The `api-vertex` launch configuration connects to Cloud SQL
through the connector with IAM auth.

## Infrastructure

One-time: create the Terraform state bucket (local state, run once).

```sh
cd infra/bootstrap
terraform init && terraform apply
```

Then the main stack. It is pure GCP — only `gcloud auth application-default
login` needs to be live (ADR 0012).

```sh
cd infra
cp example.tfvars terraform.tfvars   # edit project_id, github_repo, billing, allowed_emails
terraform init -backend-config="bucket=<state bucket from bootstrap output>"
terraform plan
```

Once per Cloud SQL instance, after the first apply: enable pgvector and hand the
database to the API's IAM user (ADR 0011). The postgres password is read from
Secret Manager; nothing is written to disk.

```sh
cd backend
GOOGLE_CLOUD_PROJECT=<project> DB_OWNER_IAM_USER=<you> .venv/bin/python scripts/db_bootstrap.py
```

The custom domain (`anyview.anyapps.cloud`) is registered on Firebase Hosting
by the main stack. The DNS record that points it there — a Route 53 CNAME —
lives in a separate stack, `infra/dns`, applied only when the domain itself
changes and needing `aws login` instead (ADR 0008, ADR 0012):

```sh
cd infra/dns
terraform init
terraform plan
```

Firebase verifies over HTTP through the CNAME and issues the certificate a
few minutes after the record exists; `terraform output firebase_dns_requests`
(main stack) shows anything it is still waiting for.

## Turning sign-in on (once)

Terraform creates the Identity Platform config and the Firebase web app; the
Google OAuth client is provisioned by the Firebase CLI so its secret never
enters state or the repository (ADR 0009):

```sh
npx firebase-tools@latest deploy --only auth --config firebase-auth.json --project anyapps-anyview
```

Then copy `terraform output firebase_web_config` into the GitHub repository
variables `FIREBASE_API_KEY` and `FIREBASE_AUTH_DOMAIN` (public values), and
put the Google accounts allowed in under `allowed_emails` in `terraform.tfvars`.
An empty list lets nobody in.

## Build order

- **Phase 0 — done.** One page, resume upload, target job, five tailored
  questions, streaming interviewer, per-dimension scored report.
- **Phase 1 — done, being polished.** Sign-in, Cloud SQL and the event-sourced
  brain: capture from text and resumes, the review queue, entries by hand,
  coverage, Discover, account erasure, and the brain as an interview source.
  Voice mode, difficulties, the per-question clock and saved jobs were pulled
  forward from later phases.
- **Phase 2 — next.** Embeddings (`gemini-embedding-2`), hybrid
  filter-then-vector retrieval in one SQL query, Cloud Tasks for ingestion, a
  golden retrieval test set.
- **Phases 3–5** — follow-up probing and per-question rubrics, session history
  and a cost dashboard, voice brain dumps. See [BRIEF.md](BRIEF.md#build-order).
