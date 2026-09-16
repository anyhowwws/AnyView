# Project Brief

## Required
- **What it does:** AnyView is a web app that helps a job-seeker prepare for interviews. It holds a "second brain": a structured, user-confirmed knowledge base of everything the user has done (roles, projects, stories, skills, achievements) built from free-text brain dumps and uploaded resumes. It runs mock interviews, HR/screening or technical, tailored to a target company, role and seniority, streams the interviewer's responses live, scores answers per rubric dimension, and generates an ideal answer built only from the user's own brain so gaps in the brain are surfaced and fed back into it.
- **UI:** Yes — web app
- **Cloud:** GCP
- **Repository:** Private

## Core Features
- Brain capture: a persistent free-text "dump something" box; the model extracts structured entities and proposes them as a patch; nothing is committed until the user confirms in a review queue
- Resume ingestion: PDF and DOCX upload via signed URL; PDF read by the model natively, DOCX converted to text first; output goes through the same review queue
- Structured brain: Role (company, title, start/end dates, level), Project (linked to role; problem/action/result, tech, metrics), Story (STAR-shaped narrative tagged to competencies such as ownership, ambiguity, conflict, failure, influence), Skill (name, self-rated depth, evidence links to projects), Achievement/Credential, RawDump (the unedited original in object storage)
- Provenance: every extracted fact stores a foreign-key pointer to the raw dump it came from; enforced by the database, not by convention
- Append-only event log of confirmed patches is the source of truth; current brain state is a materialized projection rebuilt from the log; no write may mutate state without going through the log
- Coverage map: which competencies have strong, weak, or no evidence in the brain
- Mock interview setup: choose format (HR/screening or technical), company, role, seniority, optional pasted job description
- HR/screening format: questions from published company values, competency frameworks and the JD's soft requirements; rubric dimensions are STAR completeness, specificity, quantified outcome, ownership language; interviewer persona is a warm recruiter
- Technical format: questions from the JD and role level in three shapes (conceptual, scenario/design, troubleshooting); rubric dimensions are correctness, depth, tradeoff articulation, clarity, honesty about unknowns; interviewer persona is a senior engineer who probes vague answers
- Interview engine is a state machine over turns: intake → plan → ask → answer → probe (max 2 follow-ups) → next | wrap → score → report; interview logic is independent of how text arrives so voice can replace the transport later
- Scoring prompts use explicit rubric anchors ("a 2 means the answer described a situation but no action taken by the candidate") because LLM judges inflate grades by default
- Report: per-dimension scores (never one blended number), the user's answer beside a brain-grounded ideal answer that cites entity IDs, and gaps with a one-click "add to brain" action; if the brain lacks material the model must say so, never invent
- Retrieval: one embedding per confirmed Story/Project/Achievement generated from a canonical text rendering (no chunking of raw dumps); hybrid query in one SQL statement, structured filters first (competency tags, entity type, date range, employer) then vector similarity; a compact one-line-per-entity brain index is always loaded into the prompt and cached so the model can reason about what does not exist
- Golden retrieval test set: twenty question→expected-story pairs run as an automated test
- Live streaming of interviewer tokens to the browser over server-sent events
- Cost tracking: every model call writes a usage row (session, tokens in/out, cached tokens, model); a daily rollup gives monthly run rate and cost per interview session
- Session history and progress trends over time
- Auth with per-user isolation from the first phase that stores brain data

## Preferences
- **Project name:** AnyView
- **Stack:** Backend Python 3.12 on Cloud Run with FastAPI, streaming via hand-rolled server-sent events (no streaming-UI SDK). Frontend Next.js App Router, TypeScript, Tailwind, shadcn/ui, Framer Motion, deployed to Firebase Hosting. LLM and embeddings via Vertex AI Claude models using the official Anthropic Python SDK's Vertex client. Infrastructure entirely in Terraform from the first commit. CI/CD via GitHub Actions authenticating to GCP through Workload Identity Federation with no stored keys.
- **Data / storage:** Cloud SQL for PostgreSQL (db-g1-small, single zone, no HA) with the pgvector extension in the same database; accessed from Cloud Run through the Cloud SQL connector with a deliberately small connection pool. Cloud Storage with signed URLs for uploads and raw dumps so files never transit the API. Cloud Tasks for asynchronous ingestion. Secret Manager for any secret, provisioned by Terraform (the parameter, never the value).
- **Auth:** Identity Platform
- **Model access:** All model interaction sits behind one thin adapter module exposing generate(), stream() and a tools parameter, returning plain Python types; no SDK objects leak into application code. The adapter is an indirection layer, not a framework. No API key exists anywhere: model access is governed by the Cloud Run service account's IAM role.
- **Data access:** All database access sits behind one repository module with app-meaningful methods (stories_for_competency, roles_for_user, search_brain), not a generic query interface.
- **Least privilege:** Every service account gets only the roles it needs, scoped as narrowly as the API allows; the scoping must be readable in the .tf files.
- **Cost:** GCP budget alert at USD 50 on day one. Vertex token spend tracked as its own line item.
- **Architecture records:** Keep an adr/ directory. Write a short ADR (context, options considered, decision, tradeoffs) for every significant choice as it is made, not retroactively. The first five, before any application code: cloud selection (GCP over AWS, documenting the AWS alternative and that direct Claude access on Vertex removed the ungoverned API-key problem, Python streaming without an adapter layer, and embeddings from the same provider); datastore (Postgres over Firestore, noting Firestore vector pre-filtering does not support inequality filters, the join/denormalization cost, and that Postgres→Firestore is the cheap migration direction); retrieval (explicitly superseding the earlier no-RAG decision now that the corpus is unbounded and user-authored); LLM access via Vertex (IAM-governed access, platform invocation logging, data inside the project boundary); streaming (hand-rolled SSE over an SDK, because the adapter already provides provider abstraction).
- **Commits:** Small, focused, real messages; pushed regularly, not in one batch. .env in .gitignore from the first commit. Secret values never in Terraform files, environment variables in plaintext, git history, or anything committed.
- **Working style:** The owner is a Cloud/Solutions Architect, strong on infrastructure, with limited Python fluency: can read it and write simple scripts. Explain non-obvious Python as it is written. Prefer boring, readable code over clever code: no metaclasses, no heavy abstraction layers, minimal dependencies, every dependency justified in writing. Do not dumb down the architecture. When a real fork in the road appears, stop and ask rather than picking. This project is a portfolio piece; infrastructure quality matters as much as it working.
- **Visual design:** Three surfaces. Brain: capture box pinned at the top, entities grouped by role, review queue with a badge count, competency coverage heatmap as the hero visual. Practice: deliberately sparse; one question centred, streaming text, typing indicator, subtle progress rail, nothing else on screen. Report: side-by-side answer versus brain-grounded ideal, per-dimension scores, gap list with add-to-brain buttons, trend view across sessions. Polished, modern, motion used for small transitions only.

## Build Order
- Phase 0: single page, resume pasted as text, target company/role/seniority, five tailored questions asked one at a time, streaming interviewer, per-dimension scored report. Real stack, minimum surface, nothing throwaway.
- Phase 1: auth, brain capture from text, review queue, event log, repository module.
- Phase 2: PDF/DOCX ingestion, embeddings, hybrid retrieval, brain-grounded ideal answers, golden retrieval test set.
- Phase 3: HR versus technical formats, follow-up probing, gap loop from report back into brain.
- Phase 4: session history, trends, cost dashboard.
- Phase 5: voice for both dumping and interviewing, with recording and playback of the user's own answers.

## Out of Scope
- Live coding exercises in technical interviews
- Kubernetes, GKE, service mesh, multi-region, high availability
- LangChain or any orchestration library; direct SDK calls only
- Any dedicated vector database or managed vector search service; vectors live in Postgres
- Chunking raw documents for retrieval; raw documents are read once at ingestion and are never a retrieval target
- Scraping Glassdoor, Blind or similar; questions are generated from public durable sources only
- Any API key for model access; no direct Anthropic API path
- Third-party hosted Postgres outside the GCP project
- Firestore
- Framework sprawl; no dependency without a written justification
- Console-clicked resources; if it exists, it exists in .tf
