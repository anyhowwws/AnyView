# AnyView demo kit: a guide for judges

Everything here uses one fictional candidate, **Mike Rose**, a cloud solutions architect in
Singapore. You can follow it on the live app with any Google account, in about five minutes for
the short path or twenty for everything.

| File | What it is |
|---|---|
| [`mike-rose-resume.pdf`](mike-rose-resume.pdf) | The sample resume. Five pages: three roles, fifteen projects, fourteen "key moments" (stories), fourteen certifications, education and languages |
| [`mike-rose-feedback.pdf`](mike-rose-feedback.pdf) | Eighteen pieces of feedback from colleagues, reviewers and a client, each naming the role or project it is about |
| [`job-description.pdf`](job-description.pdf) / [`.docx`](job-description.docx) | A matching fictional posting: Senior Cloud Solutions Architect, Northstar Cloud Partners. [`job-description.md`](job-description.md) is its source |

Each account can start **ten interviews and ten uploads a day** ([ADR 0047](../../adr/0047-a-daily-limit-per-user.md)).
Everything below fits inside that.

## 1. Build the garden (about 5 minutes)

1. Open [anyview.anyapps.cloud](https://anyview.anyapps.cloud) and sign in with Google.
2. In **Digital Garden**, upload `mike-rose-resume.pdf`. Donna reads it as a background job and
   shows each step as it finishes. A one-page resume takes about 90 seconds; this one is five
   pages, so allow a few minutes. You can keep using the app meanwhile, or press **Cancel**.
3. Open the review queue. Every draft quotes the line of the resume it came from. Skills are linked
   to the projects and roles that show them, and certifications to the skills they attest to.
   Press **Confirm all** (or edit or discard any draft first).
4. Upload `mike-rose-feedback.pdf` the same way and confirm it. Feedback entries link to the role or
   project they concern.

**What to look for**

- **Evidence.** Open any skill (for example *Terraform*): the quote is from a project, never from the
  skills list alone. A draft whose quote cannot be found in the document is marked *unverified*
  rather than dropped or accepted.
- **Graph.** The *Constellation*, *By role* and *By kind* views show how the work connects, using
  only links you confirmed.
- **Coverage.** The heatmap shows which interview competencies have strong, weak or no evidence, role
  by role.
- **Re-upload.** Upload the resume again: entries already confirmed are not proposed a second time
  (ADR 0015).

The competency tags and the exact number of drafts are the model's call, so two runs can differ by
a tag or an entry.

## 2. Ask Donna (Discover)

Typed, or spoken with the microphone (a question asked out loud is answered out loud):

- "What's my best evidence for leadership?" The answer cites garden entries as chips, such as the
  six landing-zone workstreams he took over and the Databricks client session.
- "Which certifications back up my security skills?" (AWS Certified Security – Specialty.)
- "Have I ever worked with Kubernetes?" Amazon EKS on the file-transfer platform.
- **Honesty check:** "Have I ever worked with Oracle databases?" The garden has an Oracle *cloud*
  certification but no Oracle database work, so Donna should say there is nothing on it rather than
  invent something.

## 3. Practise an interview

Setup: the resume is already on file. For the job, upload `job-description.pdf` (or paste the text);
company, role and seniority fill in. Choose a difficulty:

| Difficulty | Harvey knows |
|---|---|
| Recruiter screen (Easy) | The resume only |
| Hiring manager (Medium) | The resume and the job description |
| Panel (Hard) | Both, plus the whole garden, which he can look up mid-answer |

Choose **Interview pace** to see the clock, or **Take your time** for none. A pre-flight checks the
microphone and speakers while Harvey plans five questions; press **Begin** when it's ready.
Question 1 is always a version of "tell me about yourself".

**How the clock works**

- The clock runs only while Harvey is quiet, and each question has its own budget (45 to 300 s, set
  when the interview is planned).
- Each follow-up adds the time Harvey judges a good answer needs (30 to 300 s; 90 s if he names
  none). At most two follow-ups per question.
- After **10 s** of silence Harvey nudges you (30 s when untimed). After **15 s** more he moves on,
  and the question is recorded as *(no answer given)*. Filler sounds ("umm") don't count as speaking.
- When the budget runs out he cuts in mid-sentence. You can interrupt him at any time; he never
  talks over you.

### Answers to try

**A strong opener (about 80 seconds):**

> I'm a cloud solutions architect, and for five years I've led cloud engagements end to end for
> customers on AWS, Google Cloud and Azure: from requirements and effort estimates through delivery
> and L3 support.
>
> At Accenture I built and ran landing zones. On one AWS renewal I was Service Delivery Manager for
> six enhancement workstreams, and when the team shrank I took over the hands-on build as well, so
> all six were delivered while I coordinated more than ten people offshore. When the offshore team
> for a Google Cloud landing zone was offboarded, I designed and built it myself in Terraform: ten
> projects and more than forty policies. I also cut deployment cycle time from a week to a day across
> a hundred CloudFormation stacks.
>
> Since April I've been a multi-cloud architect at Lenovo PCCW Solutions, where I architected an
> AI-powered assessment platform that checks 664 rules across AWS and Azure and writes remediation
> guidance with Amazon Bedrock.
>
> I'm looking for a role where I keep owning engagements end to end across clouds, and that's what
> this one is.

Expect high **specificity**, **quantified outcome** and **ownership**. **STAR completeness** may come
out lower: the rubric applies STAR to the opener too, and a career walkthrough is not one story.
This is a known limitation, listed on the roadmap (per-question rubrics).

**A weak opener, for contrast:**

> Hi, so I've been in cloud for a few years, mostly AWS but some Google and Azure. We did landing
> zones and migrations and that kind of thing, and it went pretty well. I like solving problems and
> working with customers, and I'm looking for a new challenge.

Harvey is likely to follow up on what *you* did or what the result was. Answer vaguely again and the
report scores **specificity**, **quantified outcome** and **ownership** low ("we", "pretty well"),
then shows an ideal answer built from the garden: what Mike *could* have said.

**A failure question, strong (about 60 seconds):**

> On my bill-splitting app, AnySplit, I merged and deployed multi-currency support, and a code
> review I ran afterwards found two data-corruption bugs I'd shipped. A Japanese yen price typed as
> "3,270" was saved as 3, and a client could store an invalid currency code that broke every later
> display of that bill. I fixed both the same day, verified them against the exact reproductions and
> all nine test receipts, and closed the review's seven other findings in follow-up changes. Every
> test receipt still reconciled exactly, and the fixes shipped within a day of finding the bugs.

**The same, flawed (no result, and "we" throughout):**

> We had a bug with currencies in one of the apps. Some prices were saved wrong. We fixed it after a
> review and added some tests.

Expect a follow-up such as "what was your part?" or "what happened afterwards?". If the answer stays
vague, the report marks STAR completeness, quantified outcome and ownership down.

For a **pushback or conflict** question, the garden's story about challenging the database
specialist's MariaDB configuration is the strong answer; "I told them it was wrong and we fixed it"
is the flawed one.

### Moments worth seeing

- **Silence.** Say nothing after a question for 10 seconds: Harvey nudges. Start answering and the
  silence timer starts again; stay quiet 15 seconds more and he moves on.
- **The hard stop.** With Interview pace on, keep talking past the countdown on a question where he
  hasn't asked a follow-up yet. He cuts in ("Let me stop you there. We've got a clock to beat."),
  and the next question opens without the usual thanks.
- **Barge-in.** Start talking while Harvey is still asking. He stops and listens.
- **The close.** When question 5 ends on the clock or on silence, Harvey closes with "That's all the
  time we have. Thanks for your time today — we'll be in touch."

## 4. The report

Each answer is scored on four rubric dimensions separately (never one blended number), with an ideal
answer built only from the garden. Where the garden has nothing to build from, the report says so.
A *(no answer given)* scores at the bottom. Download it as Markdown or save it as a PDF.

Once a garden passes 20,000 characters, the ideal answers find their material by vector search over
the garden instead of reading all of it.

## 5. Your data

The **Account** page erases every file and every row for your account in one step. Voice recordings
are deleted after 30 days regardless.
