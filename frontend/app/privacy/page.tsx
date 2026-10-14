import type { Metadata } from "next";
import Link from "next/link";
import { Brain } from "lucide-react";

export const metadata: Metadata = {
  title: "Privacy · AnyView",
  description: "What AnyView collects, why, where it is kept and how to erase it.",
};

const UPDATED = "15 October 2026";
const CONTACT = "anyview@anyapps.cloud";

/** The privacy policy. Public, outside the sign-in gate, so it can be read
 *  before signing in. Every claim here is checked against what the code and
 *  Terraform actually do; change one, change the other. */
export default function Privacy() {
  return (
    <>
      <header className="workspace-header">
        <Link href="/" className="wordmark" aria-label="AnyView home"><span className="brand-mark"><Brain size={20} aria-hidden /></span>anyview<span className="brand-dot">.</span></Link>
      </header>
      <main id="main-content" className="workspace-main">
        <article className="policy mx-auto w-full max-w-3xl">
          <header className="page-heading">
            <div>
              <p className="eyebrow">Privacy policy</p>
              <h1>Your data<span className="text-primary">.</span></h1>
              <p>
                AnyView is run by AnyApps. This page says what AnyView collects, why, where it is
                kept and how you can erase it. Last updated {UPDATED}.
              </p>
            </div>
          </header>

          <section>
            <h2>What we collect</h2>
            <ul>
              <li><strong>Your Google account email</strong>, when you sign in, to keep your Digital Garden yours.</li>
              <li><strong>What you give Donna:</strong> resumes and job descriptions you upload (PDF or Word), text you paste, and job postings fetched from links you paste.</li>
              <li><strong>Your Digital Garden:</strong> the entries you confirm, with the quote each one came from, and a history of every change you make.</li>
              <li><strong>Jobs you practise for</strong>, saved so you can pick them again.</li>
              <li><strong>Your voice</strong>, when you speak an answer or a question. The microphone is only on during an interview or while you ask Donna something out loud.</li>
              <li><strong>Usage records:</strong> for each AI call, which model ran and how many tokens it used. These never contain what you said or wrote.</li>
              <li><strong>Server logs</strong> of requests, including IP address, kept for up to 30 days to keep the service running and secure.</li>
            </ul>
            <p>
              Interview questions, your answers and reports are not stored on our servers. They live in
              your browser tab and are gone when you close it.
            </p>
          </section>

          <section>
            <h2>How we use it</h2>
            <p>
              Only to run AnyView for you: to build and show your Digital Garden, answer your questions
              about it, plan and run practice interviews, and score them. We do not sell your data, show
              ads, or share it with anyone except the service provider below.
            </p>
          </section>

          <section>
            <h2>Who processes it</h2>
            <p>
              AnyView runs entirely on Google Cloud, in the United States (us-central1). Your documents,
              Digital Garden, recordings and the text of your answers are sent to Gemini on Google&apos;s
              Vertex AI to read, transcribe, plan and score. Google states that it does not use this data
              to train its models without permission. It may cache it for up to 24 hours to answer
              faster, and may log prompts to detect abuse. Sign-in uses Google Identity Platform, and the
              site is served by Firebase Hosting.
            </p>
          </section>

          <section>
            <h2>How long we keep it</h2>
            <ul>
              <li>Recordings of your voice are deleted automatically after 30 days.</li>
              <li>Everything else is kept until you erase it.</li>
            </ul>
          </section>

          <section>
            <h2>Erasing your data</h2>
            <p>
              On your <Link href="/account">Account</Link> page you can erase everything at once: every
              uploaded file, every garden entry and its history, saved jobs, usage records and your
              sign-in. It cannot be undone.
            </p>
          </section>

          <section>
            <h2>In your browser</h2>
            <p>
              AnyView uses no cookies for tracking and no analytics. Your browser keeps your sign-in, the
              interview in progress (until you close the tab) and whether you prefer to speak or type.
            </p>
          </section>

          <section>
            <h2>Who can use AnyView</h2>
            <p>
              Access is by invitation. AnyView is not meant for anyone under 16. Please only upload
              material about yourself.
            </p>
          </section>

          <section>
            <h2>Changes and contact</h2>
            <p>
              If this policy changes, the date at the top changes with it. Questions, or a request about
              your data: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
            </p>
          </section>
        </article>
      </main>
    </>
  );
}
