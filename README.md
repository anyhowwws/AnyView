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
    <a href="docs/setup.md">Run it yourself</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#what-it-does">What It Does</a></li>
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



<!-- WHAT IT DOES -->
## What It Does

**Build the Digital Garden.** Upload a resume (PDF or Word) or paste a brain
dump. Donna turns it into roles, projects, stories, skills, achievements,
education, languages and feedback. Each one carries a word-for-word quote from
what you gave her, and nothing enters the garden until you confirm it in the
review queue. The garden is shown as a graph, with a heatmap of which
competencies you have evidence for.

**Ask Donna about it.** In Discover you ask questions about your own career,
typed or out loud, and every answer cites the garden entries it came from.

**Practise with Harvey.** Give him a job, as a file, a pasted link or text, and
pick a difficulty. Recruiter screen, hiring manager and panel differ in what
Harvey knows: your resume only, then the job description, then your whole
garden. He asks each question out loud, listens, asks up to two follow-ups and
keeps time, cutting in when you stall or run long.

**Get a straight report.** Every answer is scored on each rubric dimension
separately, never as one blended number. Each comes with an ideal answer built
only from your own garden, and when the garden has nothing to build it from,
the report says so instead of inventing it.

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
in [diagrams.net](https://app.diagrams.net/)).

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
