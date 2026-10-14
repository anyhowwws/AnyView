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
    <li><a href="#how-it-meets-the-challenge">How It Meets The Challenge</a></li>
    <li><a href="#how-its-built">How It's Built</a>
      <ul>
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

**Planting.** Upload a resume (PDF or Word) or paste a brain dump. Donna reads
it with Gemini and proposes entries of eight kinds: roles, projects, stories,
skills, achievements, education, languages and feedback others have given
you. Each comes with the quote it was drawn from. An entry whose quote she can't
find in your document is marked unverified, never silently dropped or accepted. Near-duplicates ("GCP" and "Google
Cloud") are merged, and skills are linked to the roles, projects and
credentials that show them.

**Tending.** Proposals wait in a review queue. You confirm, edit or discard each
one, and only confirmed entries join the garden. Uploading a newer resume
proposes only what changed. Every change is kept in a history, so the garden
can always be rebuilt from it.

**Seeing it whole.** The garden is drawn as a graph of how your work connects,
with a coverage heatmap showing which competencies you have evidence for and
which are thin.

**Asking it.** In Discover you ask Donna about your own career, typed or out
loud ("What have I done with Kubernetes?", "Which project best shows
leadership?"). Each answer cites the garden entries it came from, so you can
check it.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- PRACTICE -->
## Practice Against Your Garden

**Tailored to the job.** Give Harvey a job description as a file, a link or
pasted text. Three difficulty levels change what he knows: a recruiter screen
sees only your resume, a hiring manager also has the job description, and a
panel has your whole garden.

**Spoken, like the real thing.** Harvey asks each question out loud over
Gemini Live, listens, asks up to two follow-ups and keeps time, cutting in when
you stall or run long.

**A straight report.** Every answer is scored on each rubric dimension
separately, never as one blended number. Each comes with an ideal answer built
only from your own garden. When the garden has nothing to build it from, the
report says so instead of inventing an answer, which shows you exactly what to
add next.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CHALLENGE FIT -->
## How It Meets The Challenge

The challenge asks for AI that changes how people access knowledge, make
decisions and get everyday work done. AnyView does this for one person's
professional knowledge:

| Challenge direction | In AnyView |
|---|---|
| Document intelligence | Resumes and job descriptions (PDF, Word or a link) become typed, linked entries, each checked against a quote from the source. |
| Knowledge accessibility | Knowledge scattered across documents and memory becomes one garden you can browse, filter and see as a graph. |
| Intelligent search / research assistant | Discover answers questions about your career, with a citation for every claim. |
| AI copilot | Harvey runs a tailored mock interview and Donna keeps the garden up to date as you add more. |
| Decision-making | The coverage heatmap and the report show where your evidence is strong and where it is missing. |

**Google Cloud in use:** Gemini on Vertex AI (Gemini 3.1 Pro for planning and
scoring, Flash-Lite for fast calls, Gemini Live for the spoken interview, Gemini
text-to-speech), Cloud Run, Cloud Tasks, Cloud SQL for PostgreSQL with
pgvector, Cloud Storage, Identity Platform, Secret Manager and Firebase
Hosting.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- HOW IT'S BUILT -->
## How It's Built

* **No API keys anywhere.** Gemini is called on Vertex AI with IAM, and CI
  deploys through Workload Identity Federation. There is no stored key to leak.
* **Everything is Terraform.** Pull requests get a plan, and a merge to `main`
  applies it and then deploys. Nothing is created by hand in the console.
* **The garden is event-sourced.** Every confirm, edit and retire is appended to
  a log in Cloud SQL Postgres, and the garden is a projection that can be
  rebuilt from it.
* **Long work runs off the request path.** Reading a resume takes about 90
  seconds of model calls, so it runs on a private Cloud Run worker behind Cloud
  Tasks while the browser follows its progress.
* **Speech is native.** Harvey's questions and follow-ups run on Gemini Live,
  with Gemini text-to-speech as the fallback. There is no separate speech API.

The diagram is in [docs/architecture.drawio](docs/architecture.drawio) (open it
in [diagrams.net](https://app.diagrams.net/)), and the reasoning behind each
choice is in [adr/](adr/).

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

Phase 0 is done: one page, resume uploaded as PDF/DOCX (or pasted), target
company/role/seniority, five tailored questions asked one at a time, streaming
interviewer, per-dimension scored report. Phase 1 is done too: sign-in, the
Digital Garden and its database, the review queue, Discover, and ingestion queued on
Cloud Tasks. Spoken interviews on Gemini Live, with follow-ups, arrived ahead of
schedule.

- [x] Phase 0 — single-page mock interview with a scored report
- [x] Phase 1 — auth, Digital Garden capture, review queue, event log, repository module
- [ ] Phase 2 — embeddings (`gemini-embedding-2`), hybrid retrieval, golden retrieval test set
- [ ] Phase 3 — HR versus technical formats, deeper probing, gap loop from the report back into the garden
- [ ] Phase 4 — session history, trends, cost dashboard
- [ ] Phase 5 — voice for dumping, recording and playback of the user's own answers

See [BRIEF.md](BRIEF.md#build-order) for the detail of each phase, and the
[open issues][issues-url] for known bugs and smaller work.

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
[Gemini-url]: https://cloud.google.com/vertex-ai/generative-ai/docs
[Firebase.id]: https://img.shields.io/badge/Firebase_Hosting-DD2C00?style=for-the-badge&logo=firebase&logoColor=white
[Firebase-url]: https://firebase.google.com/docs/hosting
[Terraform.id]: https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white
[Terraform-url]: https://www.terraform.io/
[Actions.id]: https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white
[Actions-url]: https://github.com/features/actions
