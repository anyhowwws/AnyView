<a id="readme-top"></a>



<!-- PROJECT HEADER -->
<br />
<div align="center">

<h3 align="center">AnyView</h3>

  <p align="center">
    Interview preparation web app with a "second brain".
    <br />
    <a href="BRIEF.md"><strong>Read the brief »</strong></a>
    <br />
    <br />
    <a href="https://anyview.anyapps.cloud">Live app</a>
    &middot;
    <a href="adr/">Decision records</a>
    &middot;
    <a href="https://github.com/anyhowwws/AnyView/issues">Issues</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
        <li><a href="#layout">Layout</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#backend">Backend</a></li>
        <li><a href="#frontend">Frontend</a></li>
        <li><a href="#database">Database</a></li>
        <li><a href="#infrastructure">Infrastructure</a></li>
        <li><a href="#turning-sign-in-on-once">Turning sign-in on (once)</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

AnyView keeps a structured, user-confirmed knowledge base of everything a
job-seeker has done — roles, projects, STAR stories, skills, achievements —
built from free-text brain dumps and uploaded resumes. It runs mock interviews
(HR/screening or technical) tailored to a target company, role and seniority,
streams the interviewer live, scores each answer per rubric dimension, and
generates an ideal answer built only from the user's own brain so that gaps in
the brain are surfaced and fed back into it.

Two personas run it: **Donna** looks after the knowledge base (the Digital
Garden) — extraction, the review queue and Discover, where you ask questions
about your own career — and **Harvey** is the interviewer, who speaks each
question over Gemini Live and asks follow-ups.

The full product brief is in [BRIEF.md](BRIEF.md). Architecture decisions are in
[adr/](adr/).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Built With

* [![Python][Python.id]][Python-url]
* [![FastAPI][FastAPI.id]][FastAPI-url]
* [![Next.js][Next.js]][Next-url]
* [![React][React.js]][React-url]
* [![TypeScript][TypeScript.id]][TypeScript-url]
* [![Tailwind CSS][Tailwind.id]][Tailwind-url]
* [![PostgreSQL][PostgreSQL.id]][PostgreSQL-url]
* [![Google Cloud][GCP.id]][GCP-url]
* [![Gemini][Gemini.id]][Gemini-url]
* [![Firebase][Firebase.id]][Firebase-url]
* [![Terraform][Terraform.id]][Terraform-url]
* [![GitHub Actions][Actions.id]][Actions-url]

Gemini on Vertex AI for planning, scoring and speech, Cloud Run for the API and
the ingestion worker, Cloud Tasks between them, Cloud SQL Postgres with pgvector,
Identity Platform for Google sign-in, and Firebase Hosting for the static
frontend. The reasoning behind each choice is in [adr/](adr/).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Layout

```
backend/    Python 3.12 · FastAPI · runs on Cloud Run (API and ingestion worker, one image)
frontend/   Next.js (App Router) · TypeScript · Tailwind · static export to Firebase Hosting
infra/      Terraform — every GCP resource lives here; infra/dns holds the one Route 53 record
adr/        Architecture decision records
docs/       Architecture diagram and UX checkpoints
.github/    CI (lint + test + terraform plan) and deploy (Workload Identity Federation, no keys)
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Python 3.12 (`python3.12`; this repo does not run on older interpreters)
* Node.js with npm
* PostgreSQL 17 with pgvector, for the brain and the database tests
  ```sh
  brew install postgresql@17 pgvector && brew services start postgresql@17
  ```
* Terraform and the `gcloud` CLI, for infrastructure and real model calls

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

Checks, as CI runs them:

```sh
cd frontend
npm run lint && npm run typecheck && npm run test && npm run build
```

### Database

Create a test and a dev database once, then run the migrations into the dev one
(ADR 0011):

```sh
createdb anyview_test && createdb anyview_dev
cd backend
DATABASE_URL=postgresql+psycopg://localhost/anyview_dev .venv/bin/python -m anyview.db.migrate
```

Repository and brain tests skip without a database; point them at one to run them:

```sh
cd backend
TEST_DATABASE_URL=postgresql+psycopg://localhost/anyview_test .venv/bin/pytest
```

### Infrastructure

One-time: create the Terraform state bucket (local state, run once).

```sh
cd infra/bootstrap
terraform init && terraform apply
```

Then the main stack. It is pure GCP — only `gcloud auth application-default
login` needs to be live (ADR 0012).

```sh
cd infra
cp example.tfvars terraform.tfvars   # edit project_id, github_repo, billing
terraform init -backend-config="bucket=<state bucket from bootstrap output>"
terraform plan
```

This registers the custom domain (`anyview.anyapps.cloud`) on Firebase
Hosting and drives certificate provisioning. The DNS record that actually
points the domain there — a Route 53 CNAME — lives in a separate stack,
`infra/dns`, applied only when the domain itself changes and needing
`aws login` instead (ADR 0008, ADR 0012):

```sh
cd infra/dns
terraform init
terraform plan
```

Firebase verifies over HTTP through the CNAME and issues the certificate a
few minutes after the record exists; `terraform output firebase_dns_requests`
(main stack) shows anything it is still waiting for.

In normal work you don't apply by hand: pull requests get a `terraform plan`
comment, and a push to `main` applies it, then deploys the worker, the API and
Hosting (ADR 0024).

### Turning sign-in on (once)

Terraform creates the Identity Platform config and the Firebase web app; the
Google OAuth client is provisioned by the Firebase CLI so its secret never
enters state or the repository (ADR 0009):

```sh
npx firebase-tools@latest deploy --only auth --config firebase-auth.json --project anyapps-anyview
```

Then copy `terraform output firebase_web_config` into the GitHub repository
variables `FIREBASE_API_KEY` and `FIREBASE_AUTH_DOMAIN` (public values), and
put the Google accounts allowed in under `allowed_emails` in `terraform.tfvars`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

The whole app — sign-in, resume upload, the review queue, an interview with the
microphone, scoring — can be walked through locally with no Google account, no
bucket and no tokens. `ANYVIEW_FAKE_MODEL=1` swaps every model call for scripted
replies, keeps uploads in memory and accepts a fake sign-in; the frontend build
signs in as that fake user:

```sh
cd backend
ANYVIEW_FAKE_MODEL=1 GOOGLE_CLOUD_PROJECT=anyapps-anyview ALLOWED_EMAILS=dev@example.com \
  DATABASE_URL=postgresql+psycopg://localhost/anyview_dev \
  .venv/bin/uvicorn anyview.main:app --port 8080
```

```sh
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080 NEXT_PUBLIC_FAKE_AUTH=dev@example.com npm run dev
```

The same pair is in [`.claude/launch.json`](.claude/launch.json) as `api-fake` and
`web-fake`; `api-fake-slow` gives each fake call two seconds, so the resume
progress view can be watched step by step. Neither fake path exists in a
Vertex-backed build.

Then open http://localhost:3000: the Digital Garden is the home page, and
Practice runs an interview.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

Phase 0 is done: one page, resume uploaded as PDF/DOCX (or pasted), target
company/role/seniority, five tailored questions asked one at a time, streaming
interviewer, per-dimension scored report. Phase 1 is done too: sign-in, the
brain and its database, the review queue, Discover, and ingestion queued on
Cloud Tasks. Spoken interviews on Gemini Live, with follow-ups, arrived ahead of
schedule.

- [x] Phase 0 — single-page mock interview with a scored report
- [x] Phase 1 — auth, brain capture, review queue, event log, repository module
- [ ] Phase 2 — embeddings (`gemini-embedding-2`), hybrid retrieval, golden retrieval test set
- [ ] Phase 3 — HR versus technical formats, deeper probing, gap loop from report back into the brain
- [ ] Phase 4 — session history, trends, cost dashboard
- [ ] Phase 5 — voice for dumping, recording and playback of the user's own answers

See [BRIEF.md](BRIEF.md#build-order) for the detail of each phase, and the
[open issues][issues-url] for known bugs and smaller work.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

No license has been chosen; the repository is private.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[issues-url]: https://github.com/anyhowwws/AnyView/issues
[Python.id]: https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[FastAPI.id]: https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white
[FastAPI-url]: https://fastapi.tiangolo.com/
[Next.js]: https://img.shields.io/badge/next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white
[Next-url]: https://nextjs.org/
[React.js]: https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB
[React-url]: https://react.dev/
[TypeScript.id]: https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white
[TypeScript-url]: https://www.typescriptlang.org/
[Tailwind.id]: https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white
[Tailwind-url]: https://tailwindcss.com/
[PostgreSQL.id]: https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white
[PostgreSQL-url]: https://www.postgresql.org/
[GCP.id]: https://img.shields.io/badge/Google_Cloud-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white
[GCP-url]: https://cloud.google.com/
[Gemini.id]: https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white
[Gemini-url]: https://cloud.google.com/vertex-ai/generative-ai/docs
[Firebase.id]: https://img.shields.io/badge/Firebase_Hosting-DD2C00?style=for-the-badge&logo=firebase&logoColor=white
[Firebase-url]: https://firebase.google.com/docs/hosting
[Terraform.id]: https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white
[Terraform-url]: https://www.terraform.io/
[Actions.id]: https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white
[Actions-url]: https://github.com/features/actions
