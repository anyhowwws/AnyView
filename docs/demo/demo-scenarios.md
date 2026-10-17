# AnyView demo kit

Files in this folder:

| File | For |
|---|---|
| `mike-rose-resume.pdf` / `mike-rose-feedback.pdf` | The sample data named in the README and the submission deck: upload both into a fresh account's Digital Garden (resume, then feedback). Fictional candidate |
| `jordan-lee-resume.docx` / `.pdf` | The mock resume for judges to upload. Prefer the **.docx**: it is read as-is, with no transcription step |
| `job-description.docx` / `.pdf` | A matching fictional posting (Staff Platform Engineer, Northstar Wallet) for Hiring Manager and Panel difficulty |
| `*.md` | Editable sources. Rebuild the .docx with bullets written as literal `•` characters (see "Why the resume looks like this") |

## What the resume produces

Checked against the real pipeline on Agent Platform (`scripts/extraction_recall.py`, run three times, 110–210 s per run):

| Kind | Count | Notes |
|---|---|---|
| Roles | 3 | Kitebridge Payments (R1), Harbourline Logistics (R2), Meridian Health Group (R3), each with responsibilities |
| Projects | 5 | Data centre exit, Paved Road, Build pipeline consolidation, Warehouse telemetry, Appointment reminders, each linked to its role |
| Stories | 7 | All linked to a role, all with a result |
| Skills | ~22 | Each linked to the project/role it was used in, with a quote; nothing comes from the skills list alone |
| Achievements | 5 | 4 credentials (each linked to its skill: Google Cloud, Kubernetes, Terraform, AWS) + 1 award |
| Education / Languages / Feedback | 1 / 2 / 2 | Both feedback quotes linked to their roles |

No draft was flagged unverified. **Coverage: all 11 competencies are filled, and every filled cell is "strong"**:

| Story | Role | Competencies |
|---|---|---|
| Black Friday checkout slowdown | Kitebridge | failure, ownership, leadership |
| Pushing back on a six-week migration deadline | Kitebridge | influence, conflict, communication |
| Building the platform team | Kitebridge | leadership, ownership |
| Five warehouses, five different asks | Harbourline | customer focus, ambiguity, delivery, ownership |
| Getting security and developers onto one pipeline | Harbourline | collaboration, influence, communication, delivery |
| Reminders before flu season | Meridian | delivery, technical depth |
| Explaining a scheduling outage to clinic managers | Meridian | conflict, communication, customer focus |

Competency tags are the model's call, so a run may differ by a tag or two. Two skills are inferred from the text rather than named in it ("Cloud Migration", "Platform Engineering"); judges can untick them or leave them.

**Judges' flow:** upload the .docx in the Digital Garden → wait about 2 minutes → **Confirm all** in the review queue. No edits needed.

---

## Run sheet: interview scenarios

Setup for all of these: upload the resume, paste or upload the job description, choose **Panel** (Harvey has the garden) and **turn on the time limit**. Harvey asks 5 questions; question 1 is always some version of "tell me about yourself".

Timing rules worth knowing before you're on stage:

- **Silence**: after **10 s** of silence Harvey nudges you (30 s if the interview is untimed). After **15 s** more of silence he moves on.
- **The clock**: each question has its own budget (45–300 s, set by the model when it plans the interview), shown as the on-screen countdown. When it runs out, Harvey cuts in mid-sentence.
- **Each follow-up Harvey asks adds 90 s** to that question's clock. To show the hard stop, use a question where he hasn't asked a follow-up yet.
- Filler sounds ("umm", "uhh") don't count as speaking, so the silence timer keeps running through them.

### 1. The perfect opener (question 1)

About 220 words, **about 85–90 s** at a natural pace. Read it out loud once to check it fits inside the countdown.

> I'm a cloud platform engineer, and for nine years I've worked on the same problem in three industries: getting production systems onto the cloud without customers noticing, and making it easier for engineers to ship.
>
> I started at Meridian Health Group as a software engineer. There I built an SMS reminder service that cut outpatient no-shows from 18 percent to 11 percent across nine clinics.
>
> At Harbourline Logistics I moved into DevOps. I consolidated three build tools into GitLab CI/CD, which took builds from 38 minutes down to 11, and I built a streaming pipeline on Kinesis that got warehouse data onto dashboards in 30 seconds instead of 15 minutes.
>
> For the last three and a half years I've been at Kitebridge Payments, where I lead a platform team of four. My biggest piece of work there was our data centre exit. I designed the target architecture and led 42 payment services onto Kubernetes on Google Cloud, with zero customer-facing downtime, 31 percent lower infrastructure cost, and deploys going from two days to 25 minutes.
>
> Next, I want a bigger platform with more teams on it. That's why this role caught my eye: you're growing the platform team and building on Google Cloud, which is exactly where I've spent the last few years.

(For **Recruiter Screen** difficulty, with no job description, end with: "…so I'm looking for a staff-level platform role where I can do that at a larger scale.")

**What the report should show:** high **specificity** (named systems and companies), high **quantified outcome** (before/after numbers), high **ownership** ("I designed", "I led"). **STAR completeness may still come out at 2–3**: the rubric applies STAR to the opener too, and a walkthrough of a career isn't one story (a known limitation, CLAUDE.md "Gotchas"). Say this on stage before anyone else spots it. Harvey will probably not ask a follow-up, or ask only one.

### 2. The weak opener (a contrast for the same question)

> Hi, yeah, so I've been working in tech for a while now, mostly on the cloud side. We did a lot of migrations and DevOps stuff, worked with Kubernetes, Terraform, the usual. At my current company we moved a bunch of things to the cloud and it went pretty well. I like working with people and solving problems, and I'm looking for a new challenge where I can grow.

**What should happen:** Harvey follows up, probably asking what *you* did or what the result was. If you answer the follow-up vaguely as well, the report shows **specificity 0–1** (nothing a listener could retell), **quantified outcome 0–1** ("went pretty well" has no measure), **ownership 0–1** (only "we") and **STAR 0–1**. The ideal answer under it draws on the garden (the data centre exit, 42 services, 31%), so the report shows what Jordan *could* have said. That is a good moment to show on screen.

### 3. A good answer missing one thing (behavioural)

Panel-level Harvey reads the garden, so expect questions that lead into the Black Friday or deadline stories. If the question is about **a mistake or failure**:

**Strong version (about 60 s):**
> At Kitebridge, before Black Friday 2022, I approved an autoscaling change that set our payment gateway's scale-up threshold too high. On the day, traffic hit four times normal and checkout was degraded for 18 minutes. I took incident command, rolled the change back, and then wrote and presented the postmortem myself, naming my own approval as the root cause. I also made a load test at five times peak a required gate before any scaling change. Through the next two peak seasons we had no repeat, and p99 checkout latency stayed under 300 milliseconds at four times traffic.

**Flawed version: no result, and "we" throughout:**
> At Kitebridge we had a problem on Black Friday. An autoscaling change went in with the wrong threshold and checkout got slow. We jumped on the incident, rolled it back, did a postmortem, and we added load testing to the process after that.

**Report on the flawed version:** STAR **2–3** (no result), quantified outcome **0–1** (no numbers, not even the 18 minutes), ownership **0–1** ("we" throughout, and the candidate's own approval is never mentioned). Specificity stays around 2, because it does name a system and a decision. Harvey will likely ask "what happened afterwards?" or "what was your part?". **Don't answer with the result** if you want the gap to show in the report.

If the question is about **disagreeing with someone more senior / pushing back**, the strong answer is the "Pushing back on a six-week migration deadline" story in the resume; the flawed version is "I told the VP it was too risky and in the end we did it in phases": no risk model, no numbers, no outcome.

### 4. Silence: Harvey prompts (any question)

When the question finishes, **say nothing for 10 seconds**. Harvey cuts in with one of his nudges ("Take a moment if you need it. Or shall we move on to the next one?"). Then either:

- **start answering**: the nudge counts as answered, and the silence timer starts from zero; or
- **stay silent for 15 more seconds**: Harvey says "let's leave that one there and move on", and the question is recorded as *(no answer given)*. The report scores it at the bottom, which is a quick way to show that a non-answer scores honestly.

Good choice for question 2 or 3, after the opener has gone well.

### 5. The hard stop (time limit)

Pick a question where Harvey **hasn't asked a follow-up yet**, and keep talking past the on-screen countdown: repeat the story, add detail, don't wrap up. At zero, Harvey cuts in mid-sentence ("Let me stop you there. We've got a clock to beat."), whatever you're saying. The answer is marked as cut off, and the next question opens without the usual "thanks".

Fastest way to get there: the opener with the perfect answer read twice, or the weak opener padded out. Or say nothing for 9 seconds, speak one sentence, and repeat, which keeps the nudge away while the clock runs.

### 6. Interrupting Harvey (barge-in)

Start talking while Harvey is still asking a question. He stops and listens. It only works one way: you can interrupt Harvey, but he never talks over you (except when the clock runs out).

### 7. The last question

Let question 5 end on the clock or on silence. Harvey closes with "That's all the time we have. Thanks for your time today — we'll be in touch." instead of "let's move on".

---

## Garden scenarios (Donna)

- **Review queue**: after upload, open a skill such as Kubernetes. It shows the quote from the data centre exit and its link to the CKA credential. Point out that every card quotes the resume word for word.
- **Coverage heatmap**: all 11 competencies, with a strong cell in at least one role each. Most of the stronger stories are under Kitebridge.
- **Upload the same resume again**: Donna finds nothing new and nothing is queued (confirmed entries aren't proposed twice, ADR 0015).
- **Discover, typed**: "What's my best evidence for leadership?" The answer cites the platform team and Black Friday stories as chips.
- **Discover, spoken**: ask out loud "Which certifications back up my Kubernetes and Terraform skills?" Donna answers out loud (CKA, Terraform Associate), and the label chips appear on screen without being spoken.
- **Discover honesty check**: "Have I ever worked with Azure?" Donna should say the garden has nothing on it rather than invent something.

## Why the resume looks like this

Rules to keep if you edit it, each learned from a run:

1. **Stories ("Key moments") and feedback sit inside each job.** Each job is read in its own model call; a story in a separate section at the end can't be linked to a role, and the coverage heatmap counts stories by role.
2. **Every story ends with "Result: …".** A story without a result shows as *weak* on the heatmap.
3. **Skills and Certifications come before Experience.** A role's text runs on until the next role starts, so a skills list after the last job was counted as evidence for that job.
4. **Bullets are literal `•` characters**, not Word's list style. Word's bullets vanish when the text is extracted, so the end of a project can't be found and its text runs into the next one.
5. **Skill names in the skills list match the wording in the jobs** ("Kubernetes", "Google Cloud", "GitLab CI/CD"), and each certification title contains its skill's name, which is how certifications get linked.
6. Avoid stray words that the model takes for skills: "CI/CD" on its own (it became a separate skill from GitLab CI/CD), and "SQL" (it matched "Cloud SQL").
