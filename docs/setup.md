# Running AnyView

How to run AnyView on a laptop and how to stand up its infrastructure. For what the project is, see the [README](../README.md).

## Try it locally, with no Google account

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

The same pair is in [`.claude/launch.json`](../.claude/launch.json) as `api-fake` and
`web-fake`; `api-fake-slow` gives each fake call two seconds, so the resume
progress view can be watched step by step. Neither fake path exists in a
Agent Platform-backed build.

Then open http://localhost:3000: the Digital Garden is the home page, and
Practice runs an interview.

## Full setup

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

Model calls go to Gemini Enterprise Agent Platform using your local `gcloud` Application Default
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

