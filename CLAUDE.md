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
| LLM | **Gemini 3.1 Pro (preview)** for plan/score/ideal, **Gemini 3.5 Flash-Lite** for streamed `ask` turns (0.8–1.2 s to first token; 3.8 Flash and Pro both think for 4–6 s first); Vertex AI (location `global`) via `google-genai`; IAM only, **no API key exists anywhere**. The second adapter (ADR 0004, on hold per ADR 0007) returns once its quota is granted | 0004, 0007 |
| Embeddings (Phase 2) | Vertex `gemini-embedding-2` (listed for this project). Same project, same IAM, same identity | 0003 |
| Voice | **Gemini TTS on Vertex** for Donna (prebuilt voice, `DONNA_VOICE`, default `Kore`); answers recorded in the browser and transcribed by the same model through the adapter's `attachment=` path. No speech API, no new dependency. **Speaking is the default**; her interruptions are fixed lines fetched once per run from `/interview/say` | 0013, 0016 |
| Streaming | Hand-rolled SSE (`StreamingResponse`), no streaming-UI SDK. Browser → Cloud Run **direct** with CORS; Firebase Hosting rewrites buffer and must not carry the API | 0005, 0006 |
| Data | Cloud SQL Postgres (db-g1-small, single zone) + pgvector, Cloud SQL connector, small pool | 0002 |
| Retrieval | One embedding per confirmed entity; hybrid filter-then-vector in one SQL | 0003 |
| Frontend | Next.js App Router, TS, Tailwind v4, shadcn/ui, Framer Motion; static export → Firebase Hosting (static files only) | brief |
| Files | Cloud Storage bucket `<project>-uploads`, `uploads/<uid>/…`, V4 signed PUT URLs (never transit the API); PDF read by the model, DOCX by `python-docx`. Resumes **and** job descriptions take the same path | 0010, 0014 |
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
frontend/firebase.json Hosting config: static files + SPA fallback + cache headers only. No API rewrite (ADR 0006).
infra/bootstrap/       State bucket only. Local state. Run once.
infra/                 Main GCP stack. GCS backend, bucket via -backend-config. No AWS credentials needed (ADR 0012).
infra/dns/              The one AWS resource (Route 53 CNAME). Own state, own `aws login`. Applied rarely (ADR 0012).
adr/                   Decision records, numbered. Write one *as* a decision is made.
.github/workflows/     ci.yml — lint/test/validate, then (push to main only, after those pass) WIF → Artifact Registry → Cloud Run → Hosting
```

Backend modules:
- `anyview/config.py` — `Settings` from env vars. Plain `os.environ`, no settings library.
- `anyview/llm/adapter.py` — the only file that imports `google.genai`. `generate()` (optionally with `output_schema=` → parsed dict), `stream()`. Returns plain Python types. Every call logs one `anyview.usage` JSON line.
- `anyview/llm/fake.py` — `FakeModel`, same surface, scripted replies. Used by tests and by `ANYVIEW_FAKE_MODEL=1`.
- `anyview/interview/voice.py` — splits the `ask` stream into sentences and synthesises each
  one while the next arrives; emits `audio` / `voice_off` frames beside the token frames.
- `anyview/interview/{models,rubric,prompts,engine}.py` — Pydantic models; rubric anchors as data; prompt builders; the state machine (intake → plan → ask → answer → probe(≤2) → next | wrap → score → report). Transport-agnostic; Phase 0 has `max_probes = 0`.
  `prompts.py` also owns **difficulty** (ADR 0014): `recruiter_screen` / `hiring_manager` / `panel` decide what the interviewer knows, and the garden reaches `session_system` at `panel` only.
  It also owns `INTERJECTIONS` — the fixed lines Donna says when she has to cut in (ADR 0016) — and
  tells the model to open with "tell me about yourself" and to set each question's `seconds`.
- `anyview/api/{auth,interview,uploads,sse}.py` — the sign-in gate (`current_user`), interview routes, upload tickets, and the SSE frame writer.
  `account.py` serves `POST /account/erase` (ADR 0018): deletes the user's files, then every row, via `Repository.erase_user`.
  `interview.py` also serves `GET /interview/resume` (the resume on file), `POST /interview/job/parse` (an uploaded JD → text + pre-filled fields) and `POST /interview/say` (one of Donna's fixed interjections, by key — never free text).
- `anyview/uploads/{store,extract}.py` — the upload store (GCS or in-memory), resume → text
  extraction, and recorded answer → transcript (`audio_to_text`).
- `anyview/db/{connection,migrate,repository}.py` — engine (connector + IAM auth, or DATABASE_URL), numbered SQL migrations run at startup, and **the only file that runs SQL**: app-meaningful methods over an event log + projection (ADR 0011).
  `active_resume` / `set_active_resume` are the resume on file; `dump_with_text` is the re-upload no-op check.
- `anyview/brain/{models,extract}.py` — Patch drafts with verbatim evidence, the brain as read, coverage; the dump → Patch pipeline
  (ADR 0019): segment → extract per section in parallel → `merge` → flag drafts whose quote is missing as `unverified`
  (never dropped silently) → link skills. `drop_unchanged` keeps drafts restating already-confirmed entities out of the
  review queue (ADR 0015), and a confirmed skill keeps links a re-upload did not show again.
- `anyview/brain/sections.py` — the fast model returns a long dump's sections as **line ranges only** (never rewritten
  text); `from_ranges` makes them overlap-free and loses no line. Under 2,000 characters, or fewer than two real
  sections, the dump is read in one call.
- `anyview/brain/dedupe.py` — one call proposes groups of near-duplicate skills ("GCP"/"Google Cloud"); `checked()`
  refuses unknown or reused keys and any group joining two garden entries; `extract.fold_duplicates` applies them,
  recording absorbed names in `merged_from` (ADR 0021). Runs before linking.
- `anyview/brain/link.py` — one call links skills to roles and projects; each link's quote must sit inside the
  target's own stretch of the dump (`brain/evidence.py:spans`), so a skills-list line justifies nothing.
- `anyview/brain/evidence.py` — `fold()`/`normalise()`: the one definition of "the same quote" (NFKC, dashes,
  bullets, curly quotes, case, whitespace). Every evidence check goes through it.
- Roles carry `responsibilities` (ongoing work); bounded work with an outcome is a project; a story is a moment of
  behaviour (ADR 0019). Skills link to projects (`skill_evidence`), to roles (`skill_roles`) and to the
  credentials that attest to them (`skill_achievements`, ADR 0020). A credential link's quote must also share a
  distinctive word with its title (`link.names_credential`), because one list line is evidence for every
  credential on it.
  Entity kinds: role, project, story, skill, achievement, education, language, **feedback** (label prefix `F`) —
  a quote or close paraphrase of what someone else said about the candidate's work, optionally linked to the
  role or project it concerns. Adding a kind touches `EntityKind`/`KINDS`/`LABEL_PREFIX`/`EDITABLE` in
  `brain/models.py`, `TABLE` + every `_entities()` caller in `db/repository.py`, the extraction schema and
  prompt in `brain/extract.py`, and on the frontend `types.ts`, `capture-templates.ts` (the dropdown),
  `lib/brain-graph.ts` (nodes/edges) and `components/brain/{entities,review-queue,brain-graph,discover}.tsx`.
- `anyview/brain/manual.py` — entries added by hand (ADR 0022): `POST /brain/entities/{kind}` turns a form into a
  one-draft Patch and a `text` dump holding the form (its provenance), confirmed at once by `Repository.add_entry`
  through the same `_resolve`/`_apply` path. No model call, no proposal.
- Frontend form fields live in `frontend/lib/entry-fields.ts` (labels, hints, required, max lengths, month-precision
  dates, start ≤ end) and render through `components/brain/entry-form.tsx`; the editor, the add form and the review
  queue all use them. A new editable field goes there, not in a component.
- `anyview/brain/discover.py` — Discover (ADR 0017): Donna answers questions about the confirmed
  garden over `POST /brain/discover` (SSE: tokens, then one `citations` frame). Whole garden in the
  system prompt, no retrieval yet; `discover_context()` is the seam Phase 2 retrieval replaces.
  Read-only, stateless, fast model. Cited labels are checked against the user's label map.
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
  The one exception is `erase_user` (ADR 0018): it deletes a whole user's stream in a
  transaction that first sets `anyview.erasing_user`, the only delete the trigger allows.
  A new table with a `user_id` column must be added to `ERASE_ORDER`; a test enforces it.
- Entity labels (R1, P2, S3, K1, A1) are computed per read from creation order, never
  stored. Prompts use them; the review queue resolves them back to ids at confirmation.
- Every model call writes a usage row. No exceptions, including scoring and `speak` calls.
- A resume upload is 4 + *n* calls: transcribe (fast model), `segment` (fast model, `generate(fast=True)`), one
  `propose` per section (each job of the experience section is its own; list sections think at `medium`), one
  `dedupe`, one `link`. About 90 s for a one-page resume. `POST /brain/dumps/stream` and
  `/brain/dumps/from-upload/stream` send `progress` frames, then `proposal`; the capture box uses them.
  `api-fake-slow` (launch.json) gives each fake call 2 s so the progress view can be walked through locally. `scripts/extraction_recall.py <file> --expect achievements=14` runs the real
  pipeline on a document you know the answer for; keep real resumes out of the repo.
- Each question carries its own `seconds` (ADR 0016), chosen by the model when it plans and
  clamped by `engine.start` into 45–300. The clock only runs when `setup.time_bounded`.
- Scoring is concurrent twice over: the five answers in a thread pool, and each answer's `score`
  and `ideal` calls side by side inside `_score_one` (the SDK client is thread-safe). Keep new
  per-answer work inside `_score_one` so it stays parallel. `POST /interview/report/stream` sends
  the header, then one `item` frame per answer in finishing order (`score_as_ready`); the report
  screen counts them under a loader and shows the whole report, in question order, once all are in. `/interview/report` (`finish()`) is the same, collected.
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
`/brain` screen, Discover (0017), and the brain as an interview source. Setup now describes a
situation rather than a set of sources (0014), and a replaced resume queues
only what changed (0015). Phase 2 next: embeddings
(`gemini-embedding-2`), hybrid retrieval, Cloud Tasks for ingestion, golden
retrieval test set.

## Gotchas

- The API keeps one warm instance (`min_instance_count = 1`, ADR 0023): a cold start took ~66 s and
  Cloud Run refused requests outright while it booted. GETs in `frontend/lib/api.ts` also retry for
  ~75 s, which covers deploys and instance replacement. Don't put it back to zero without reading 0023.
- Cloud Run service is created with a placeholder image; `lifecycle.ignore_changes`
  on the image means Terraform never fights CI. Don't remove that.
- Voice mode needs the TTS model enabled in Model Garden. It is a different model family
  from the chat models, with its own id (`TTS_MODEL_ID`, default `gemini-2.5-flash-preview-tts`) —
  confirm what the project actually has before the first real run. A failure there is not fatal:
  the stream sends one `voice_off` frame and the interview carries on as text.
- The clock is enforced in the browser, by the same `AnalyserNode` that drives the level meter:
  ten seconds of dead air makes Donna speak up (the mic stays open), and the question's budget
  ends the turn mid-sentence. Nothing about timing is enforced server-side.
- An answer of `(no answer given)` is what the clock running out on silence records. It keeps
  `finish()`'s "every question needs an answer" rule intact, and skips the upload and transcription.
- The rubric's four dimensions are applied to the opener too, so question one ("tell me about
  yourself") scores harsher than it deserves — STAR does not fit a background walkthrough.
  Per-question rubrics belong with the Phase 3 probing work (ADR 0016).
- Recorded answers live under `audio/<uid>/` in the uploads bucket, not `uploads/<uid>/`, because
  a GCS lifecycle rule matches a literal prefix and cannot wildcard the uid. They expire after 30
  days (`answer_audio_retention_days`); resumes never do.
- `ANYVIEW_FAKE_MODEL=1` makes `speak()` return silence of a realistic length and points the
  "signed" upload URL back at `PUT /uploads/memory/...`, so the whole voice loop — mic, silence
  detection, upload, transcript — can be walked through locally with no bucket and no tokens.
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
- Hosting cache headers (`firebase.json`): everything outside `/_next/` is `no-cache` (revalidated each load),
  `/_next/static/**` is `immutable` for a year (hashed names). Firebase's default is `max-age=3600` on
  everything, which kept the old page in browsers for up to an hour after a deploy.
- The static export writes each route as a flat file (`out/practice.html`). `cleanUrls: true` in
  `firebase.json` is what maps `/practice` to it; without it a refresh or a pasted link falls
  through the `**` rewrite to `index.html` (the garden) while the URL still says `/practice`.
- Don't run `next build` while `next dev` is up — both use `frontend/.next/` and the
  dev server then throws `__webpack_modules__[moduleId] is not a function`. Stop
  dev, build, restart dev (or `rm -rf frontend/.next`).
- The second adapter's model (ADR 0004) on Vertex needs the models enabled in Model
  Garden and a non-zero `global_online_prediction_requests_per_base_model` quota; a
  fresh project returns 429 "Quota exceeded" until then (that is why Phase 0 runs
  Gemini — ADR 0007). Gemini has a default quota. The app maps a 429 to a 503 either way.
- Gemini counts thinking tokens against `max_output_tokens`; the adapter adds a
  per-effort allowance. The usage log's `thinking_tokens` shows the real spend.
- The resume is a **property of the user**, not a per-interview choice (ADR 0014):
  `users.resume_dump_id` points at a `raw_dumps` row, `/interview/start` with no
  `resume`/`resume_object` uses it, and the stored text means a second interview
  does not re-extract the PDF. Without a database the flow still works — it asks
  for the file every time.
- Difficulty gates *sourcing only*. `MAX_PROBES` stays 0 until Phase 3, so Panel
  is harder because of what it asks, not because it interrupts. A Panel interview
  with an empty garden uses `PANEL_WITHOUT_GARDEN`: never point the model at a
  `<digital_garden>` block that is not in the prompt.
- The report reads the garden at *every* difficulty, but below Panel it rides in
  `ideal_user`'s user turn — after the cache breakpoint, where it cannot reach
  the questions. Putting it in `session_system` instead would leak it to the
  interviewer.
- A role that vanishes from a re-uploaded resume is **not** retired. Absence is
  not evidence; trimming a CV for one application is the normal reason. Retiring
  stays a manual act in `/brain`.
- Only the `-preview` build of Gemini 3.1 Pro is reachable; bare `gemini-3.1-pro`
  is a 404. `gemini-3.8-flash` is the GA step-down for judgement calls; it cannot disable thinking, so it is not a fit for `ask`.
