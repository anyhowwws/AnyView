<a id="readme-top"></a>



<!-- PROJECT HEADER -->
<br />
<div align="center">

<h3 align="center">AnyView</h3>

  <p align="center">
    Grow your career into a Digital Garden, then practise interviews against it.
    <br />
    <a href="https://anyview.anyapps.cloud"><strong>Open the live app »</strong></a>
    <br />
    <br />
    <a href="BRIEF.md">Product brief</a>
    &middot;
    <a href="adr/">Decision records</a>
    &middot;
    <a href="docs/setup.md">Run it yourself</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#the-digital-garden">The Digital Garden</a></li>
    <li><a href="#practice-against-your-garden">Practice Against Your Garden</a></li>
    <li><a href="#harvey-a-bounded-agent-with-tools">Harvey: A Bounded Agent With Tools</a></li>
    <li><a href="#searching-the-garden-vectors-and-similarity">Searching The Garden: Vectors And Similarity</a></li>
    <li><a href="#how-it-meets-the-challenge">How It Meets The Challenge</a></li>
    <li><a href="#how-its-built">How It's Built</a>
      <ul>
        <li><a href="#models-and-why">Models And Why</a></li>
        <li><a href="#safeguards-and-operations">Safeguards And Operations</a></li>
        <li><a href="#decisions-we-changed-and-why">Decisions We Changed, And Why</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

What you know about your own career is scattered: an out-of-date CV, a
LinkedIn profile, old performance reviews, notes in a dozen places. When an
interview comes, you rebuild it from memory, under pressure, and the best
examples are the ones you forget.

AnyView gathers that knowledge into a **Digital Garden**: a structured,
connected record of your roles, projects, stories, skills and achievements.
Every entry is backed by a word-for-word quote from what you gave it, and
nothing gets in until you confirm it. You can see the whole garden at once, ask
it questions, and rehearse interviews with an interviewer who has read it. It
is a second brain for your career, but one you tend and can trust, because
every entry shows where it came from.

Two AI personas work in it. **Donna** tends the garden: she reads what you give
her, proposes entries and answers your questions about it. **Harvey** is the
interviewer.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- THE DIGITAL GARDEN -->
## The Digital Garden

**Planting.** Upload a resume (PDF or Word), paste a brain dump, or write a
**Freeform thought** ("write naturally; Donna will identify the useful
entries"). Donna reads it with Gemini and proposes entries of eight kinds:
roles, projects, stories, skills, achievements, education, languages and
feedback others have given you. Each comes with the quote it was drawn from. An
entry whose quote she can't find in your document is marked unverified, never
silently dropped or accepted. Near-duplicates ("GCP" and "Google Cloud") are
merged, and skills are linked to the roles, projects and credentials that show
them. If you'd rather type it yourself, each entry type has its own form (a
story asks for situation, task, action and result), and those entries skip the
model entirely.

**Tending.** Proposals wait in a review queue. You confirm, edit or discard each
one, and only confirmed entries join the garden. Uploading a newer resume
proposes only what changed. Every change is kept in a history, so the garden
can always be rebuilt from it.

**Seeing it whole.** The garden is drawn as a **constellation**: a graph of how
your work connects, built only from links you have confirmed. It has three
views. *Constellation* lets the connections alone decide where entries sit.
*By role* gives each job its own territory, so a skill used in two roles
settles between them. *By kind* clusters each entry type, so you can see which
skills have projects behind them and which stand alone. A **coverage heatmap**
shows which competencies have strong, weak or no evidence.

**Asking it.** In **Discover** you ask Donna about your own career, typed or out
loud ("What have I done with Kubernetes?", "Which project best shows
leadership?"). A question asked out loud is answered out loud. Each answer
cites the garden entries it came from, so you can check it.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- PRACTICE -->
## Practice Against Your Garden

**Tailored to the job.** Give Harvey a job description as a file, a link or
pasted text. Three difficulty levels change what he knows: a recruiter screen
sees only your resume, a hiring manager also has the job description, and a
panel has your whole garden.

**Spoken, like the real thing.** A short pre-flight checks your microphone and
speakers while Harvey plans the interview. He then asks each question out loud
over Gemini Live, listens, asks up to two follow-ups and keeps time. Each
question has its own time budget, and each follow-up adds 90 seconds to it. He
cuts in when you stall or run long.

**A straight report.** Every answer is scored on each rubric dimension
separately, never as one blended number. Each comes with an ideal answer built
only from your own garden. When the garden has nothing to build it from, the
report says so instead of inventing an answer, which shows you exactly what to
add next.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- AGENT -->
## Harvey: A Bounded Agent With Tools

Harvey works as an agent, but a bounded one: the model decides what to say and
when to dig deeper, and the API decides what it is allowed to do.

* **Plans.** Gemini 3.1 Pro writes five questions for the job and situation,
  each with its own time budget (45–300 seconds).
* **Uses tools on Gemini Live.** Harvey has two tools. `ask_follow_up` asks
  for permission to probe; the API approves at most two per question and
  refuses once the clock has ended it. `finish_question` closes the question
  when the answer is complete.
* **Looks things up.** At Panel, Harvey reads a one-line index of your garden
  rather than all of it. When a follow-up needs detail, `ask_follow_up` names up
  to three entries, and the API looks them up and hands them back mid-answer.
* **Adapts between questions.** One fast call rewrites his carry-over notes and
  may reword the next question. It has a 6-second deadline; if it is late or
  fails, he asks the question as planned.

**Why not a fully agentic loop?** We considered one, where the model decides
everything every turn. In testing, each model decision added 2–6 seconds to a
spoken turn and made Harvey harder to predict. The bounded version keeps the
judgement calls with the model and the rules (follow-up budget, clock, which
entries exist) in code that can be tested.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- SEARCH -->
## Searching The Garden: Vectors And Similarity

* **Vectors.** Every confirmed project, story, achievement and feedback entry
  gets one 768-dimension vector from Gemini Embedding 2. It is made before the
  change is saved, so the garden and its vectors never disagree.
* **Similarity.** One SQL query in Cloud SQL Postgres with pgvector filters
  first (this user, these entry kinds, live entries only), then ranks what is
  left by cosine distance. No separate vector database.
* **When search is used.** While a garden is small, the whole of it goes into
  the prompt, so nothing can be missed. The report switches to search
  once a garden passes 20,000 characters. Discover still reads the whole
  garden today; searching past the same threshold is next on the roadmap.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CHALLENGE FIT -->
## How It Meets The Challenge

The challenge asks for AI that changes how people access knowledge, make
decisions and get everyday work done. AnyView does this for one person's
professional knowledge:

| Challenge direction | In AnyView |
|---|---|
| Document intelligence | Resumes and job descriptions (PDF, Word or a link) become typed, linked entries, each checked against a quote from the source. |
| Knowledge accessibility | Knowledge scattered across documents and memory becomes one garden you can browse, filter and see as a constellation. |
| Intelligent search / research assistant | Discover answers questions about your career, with a citation for every claim; vector search backs the report. |
| AI copilot | Harvey runs a tailored mock interview as a bounded agent, and Donna keeps the garden up to date as you add more. |
| Decision-making | The coverage heatmap and the report show where your evidence is strong and where it is missing. |

**Google Cloud in use:** Gemini models on Gemini Enterprise Agent Platform
(Gemini 3.1 Pro, Gemini 3.5 Flash-Lite, Gemini 3.8 Flash as a fallback, Gemini
Live, Gemini text-to-speech and Gemini Embedding 2), Cloud Run, Cloud Tasks,
Cloud SQL for PostgreSQL with pgvector, Cloud Storage, Identity Platform,
Secret Manager, Cloud Logging and Monitoring, and Firebase Hosting.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- HOW IT'S BUILT -->
## How It's Built

* **No API keys anywhere.** Every model is called on Gemini Enterprise Agent
  Platform with IAM, and CI deploys through Workload Identity Federation. There
  is no stored key to leak.
* **Everything is Terraform.** Pull requests get a plan, and a merge to `main`
  applies it and then deploys. Nothing is created by hand in the console.
* **The garden is event-sourced.** Every confirm, edit and retire is appended to
  a log in Cloud SQL Postgres, and the garden is a projection that can be
  rebuilt from it. A test checks that replaying the log gives the same garden.
* **Long work runs off the request path.** Reading a resume takes about 90
  seconds of model calls, so it runs on a private Cloud Run worker behind Cloud
  Tasks while the browser follows its progress.
* **Speech is native.** Harvey's questions and follow-ups run on Gemini Live,
  with Gemini text-to-speech as the fallback. There is no separate speech API.
* **The browser talks to Cloud Run directly.** The site is static files on
  Firebase Hosting; the API streams to the browser over server-sent events and
  a WebSocket, with no proxy in between to buffer them.

The diagram is in [docs/architecture.drawio](docs/architecture.drawio) (open it
in [diagrams.net](https://app.diagrams.net/)), and the reasoning behind each
choice is in [adr/](adr/), 43 records written as each decision was made.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Models And Why

| Model | Used for | Why this one |
|---|---|---|
| Gemini 3.1 Pro (preview) | Planning the interview, scoring, ideal answers | Judgement calls, where depth matters more than speed |
| Gemini 3.5 Flash-Lite | Resume extraction, Discover, adapting between questions, transcription | 0.8–1.2 s to first token against 5.6 s for Pro, with the same output quality on these tasks |
| Gemini 3.8 Flash | The report's fallback, at low effort | 5–10 s at low effort; Pro's preview build sometimes throttles |
| Gemini Live | The spoken interview, with follow-ups | A real conversation, with barge-in and tool calls, instead of turn-by-turn audio |
| Gemini TTS | Harvey's voice on the turn-based fallback; Donna's voice in Discover | Same platform and identity, so no separate speech API |
| Gemini Embedding 2 | One vector per garden entry | Same project, same IAM, same identity as the chat models |

Asking the next question makes no model call at all: it is a fixed lead-in plus
the planned question, word for word. Asked for "one sentence", the fast model
kept repeating the question.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Safeguards And Operations

* **Fallbacks.** If Gemini Live fails, the interview carries on turn by turn
  with text-to-speech; if speech fails, it carries on as text. Report calls get
  two 75-second tries on Pro, then one on Gemini 3.8 Flash, so the worst case
  is about 3.5 minutes rather than 8 or more.
* **Errors.** Unknown pages get a custom 404 page with a real 404 status. Page
  loads retry for about 75 seconds, which covers deploys and instance
  replacement, and one warm API instance avoids the ~66-second cold start.
* **Monitoring.** The app writes one log line per activity (sign-ups,
  interviews started and completed, Discover questions, garden uploads) and one
  per model call. Log-based metrics feed an "AnyView usage" dashboard in Cloud
  Monitoring, and each sign-up sends the owner an email.
* **Privacy.** A [privacy page](https://anyview.anyapps.cloud/privacy) says what
  is collected, why, where it is kept and for how long. Voice recordings are
  deleted after 30 days, and one click on the Account page erases every file
  and every row.
* **Access.** Sign-in is Google only, open to any verified Google account, with
  the Firebase ID token checked on every signed-in request to the API.
* **Custom domain.** The `anyapps.cloud` zone lives in AWS Route 53. Terraform
  writes one CNAME, `anyview.anyapps.cloud` to Firebase Hosting, in its own
  small stack so a stale AWS session can never block a GCP deploy. Firebase
  provisions the certificate.
* **Cost.** A budget alert is provisioned in Terraform from day one, and every
  model call records its tokens (in, out, cached and thinking).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Decisions We Changed, And Why

| Area | Started with | Now | Why (ADR) |
|---|---|---|---|
| Model | Claude on Gemini Enterprise Agent Platform (the brief) | Gemini 3.1 Pro and 3.5 Flash-Lite | Claude's quota in the project stayed at zero; Gemini had a default quota (0004 → 0007) |
| Fast calls | Pro for every call | Flash-Lite for extraction, Discover and adapting | 0.8–1.2 s to first token against 5.6 s on Pro, same output quality (0007) |
| Interviewer | An agentic loop, considered; text-to-speech turn by turn | Gemini Live with two bounded tools | A model decision every turn added 2–6 s; Live gives real follow-ups, and TTS stays as the fallback (0028, 0031) |
| Retrieval | The whole garden in every prompt | Embeddings and filter-then-similarity SQL | A garden grows without bound; the report searches once it passes 20,000 characters (0017, 0038) |
| Ingestion | Inside the browser's request | Cloud Tasks and a private worker | A resume takes ~90 s; the queue adds retries, and a lease stops duplicate runs (0034) |
| Scaling | Scale to zero | One warm API instance | A cold start took ~66 s, and Cloud Run refused requests meanwhile (0023) |
| Report | Pro only, 120 s × 4 attempts | Pro 75 s × 2, then 3.8 Flash at low effort | The throttled preview Pro made reports take 8+ minutes; the worst case is now ~3.5 (0039) |
| Follow-up time | One fixed clock per question | +90 s for each follow-up | Two follow-ups inside the planned time cut candidates off (0040) |
| Access | Email allow-list | Any verified Google account | The app went live; a usage dashboard and a sign-up email keep watch (0041, 0042) |

Ruled out from the start: AWS (0001); Firestore (0002), because confirming a
change must be one transaction over an event log with relational links; and
LangChain or a dedicated vector database (the brief).

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

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

The build follows six phases from the [brief](BRIEF.md#build-order). Spoken
interviews on Gemini Live, with follow-ups, arrived ahead of schedule.

- [x] **Phase 0: mock interview MVP.** One page, five tailored questions asked
  one at a time, a streamed interviewer, a per-dimension scored report.
- [x] **Phase 1: auth and the Digital Garden.** Sign-in, capture, the review
  queue, the event log, Discover, and ingestion on Cloud Tasks.
- [ ] **Phase 2: retrieval (in progress).** Done: embeddings, hybrid search,
  and search for the report. Left: Discover's search past its threshold, and a
  golden retrieval test set (question → expected story pairs run as a test).
- [ ] **Phase 3: formats and probing (partly done).** Done: follow-ups on Live
  and adaptive planning. Left: HR versus technical formats with per-question
  rubrics, and one click from a gap in the report to a new garden entry.
- [ ] **Phase 4: history and cost (partly done).** Done: the usage dashboard
  and sign-up alerts. Left: session history, trends and cost per interview.
- [ ] **Phase 5: voice (mostly done).** Done: spoken interviews, spoken
  Discover questions and read-aloud answers. Left: voice brain dumps, and
  replaying your own recorded answers.

See the [open issues][issues-url] for known bugs and smaller work.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Copyright © 2026 AnyApps. All rights reserved. The source is public for the
hackathon's judging only; it may not be used, copied, modified or distributed
without permission. See [LICENSE](LICENSE), and contact
[anyview@anyapps.cloud](mailto:anyview@anyapps.cloud) for permission.

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
[Gemini-url]: https://docs.cloud.google.com/gemini-enterprise-agent-platform
[Firebase.id]: https://img.shields.io/badge/Firebase_Hosting-DD2C00?style=for-the-badge&logo=firebase&logoColor=white
[Firebase-url]: https://firebase.google.com/docs/hosting
[Terraform.id]: https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white
[Terraform-url]: https://www.terraform.io/
[Actions.id]: https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white
[Actions-url]: https://github.com/features/actions
