# AnyView

Interview preparation web app with a "second brain".

AnyView keeps a structured, user-confirmed knowledge base of everything a
job-seeker has done — roles, projects, STAR stories, skills, achievements —
built from free-text brain dumps and uploaded resumes. It runs mock interviews
(HR/screening or technical) tailored to a target company, role and seniority,
streams the interviewer live, scores each answer per rubric dimension, and
generates an ideal answer built only from the user's own brain so that gaps in
the brain are surfaced and fed back into it.

The full product brief is in [BRIEF.md](BRIEF.md). Architecture decisions are in
[adr/](adr/).

## Layout

```
backend/    Python 3.12 · FastAPI · runs on Cloud Run
frontend/   Next.js (App Router) · TypeScript · Tailwind · deploys to Firebase Hosting
infra/      Terraform — every GCP resource lives here
adr/        Architecture decision records
.github/    CI (lint + test) and deploy (Workload Identity Federation, no keys)
```

## Running locally

### Backend

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn anyview.main:app --reload --port 8080
```

Test and lint:

```sh
cd backend
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Model calls go to Vertex AI using your local `gcloud` Application Default
Credentials — there is no API key anywhere:

```sh
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>
```

### Frontend

```sh
cd frontend
npm install
npm run dev          # http://localhost:3000
```

### Infrastructure

One-time: create the Terraform state bucket (local state, run once).

```sh
cd infra/bootstrap
terraform init && terraform apply
```

Then the main stack:

```sh
cd infra
cp example.tfvars terraform.tfvars   # edit project_id, github_repo
terraform init -backend-config="bucket=<state bucket from bootstrap output>"
terraform plan
```

## Build order

Phase 0 (current): single page, resume pasted as text, target company/role/
seniority, five tailored questions asked one at a time, streaming interviewer,
per-dimension scored report. Real stack, minimum surface, nothing throwaway.

See [BRIEF.md](BRIEF.md#build-order) for Phases 1–5.
