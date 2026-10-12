"use client";

import { useEffect, useRef, useState } from "react";
import { Practice } from "@/components/practice";
import { ReportView, type Slot } from "@/components/report-view";
import { SetupForm } from "@/components/setup-form";
import { ApiError, startInterview, streamReport, submitAnswer, uploadResume } from "@/lib/api";
import { signOut } from "@/lib/auth";
import { EMPTY, clear, load, save, type Saved } from "@/lib/store";
import type { QuestionReport, Report, Session, SetupInput } from "@/lib/types";

/** Top-level flow: setup → practice → report. Owns the session and persists it. */
export function App() {
  const [saved, setSaved] = useState<Saved>(EMPTY);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<"idle" | "uploading" | "starting">("idle");
  const [error, setError] = useState<string | null>(null);
  // The report as it streams in (null = not scored yet). Not persisted: a
  // reload re-scores, since the stream that was filling it is gone.
  const [header, setHeader] = useState<Report | null>(null);
  const [scored, setScored] = useState<(QuestionReport | null)[]>([]);
  const scoringStarted = useRef(false); // effects run twice in dev; score once

  useEffect(() => {
    // sessionStorage only exists in the browser; read it after mount.
    setSaved(load());
    setHydrated(true);
  }, []);

  function update(next: Saved) {
    setSaved(next);
    save(next);
  }

  /** Returns whether the action completed so callers can retain unsaved input on failure. */
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Token rejected: the session is over. Back to the gate with the reason.
        await signOut();
      }
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const onStart = (file: File | null, setup: Omit<SetupInput, "resume_object">) =>
    run(async () => {
      try {
        let input: SetupInput = setup;
        if (file) {
          setStage("uploading");
          input = { ...setup, resume_object: await uploadResume(file) };
        }
        setStage("starting");
        const session = await startInterview(crypto.randomUUID(), input);
        update({ phase: "practice", session, report: null, spoken: {} });
      } finally {
        setStage("idle");
      }
    });

  /** Stream the report in. Each question lands in `scored` as it finishes;
   *  only the whole report is saved. */
  async function score(session: Session, base: Saved) {
    scoringStarted.current = true;
    setScored(session.questions.map(() => null));
    const report = await streamReport(session, {
      onHeader: setHeader,
      onItem: (index, item) =>
        setScored((prev) => prev.map((existing, i) => (i === index ? item : existing))),
    });
    update({ ...base, session, phase: "report", report });
  }

  const onAnswer = (text: string) =>
    run(async () => {
      if (!saved.session) return;
      const q = saved.session.questions[saved.session.current];
      const session = await submitAnswer(saved.session, { question_id: q.id, text });
      if (session.state === "wrap") {
        const next: Saved = { ...saved, session, phase: "report" };
        update(next);
        await score(session, next);
      } else {
        update({ ...saved, session });
      }
    });

  // Reloaded mid-scoring: the stream died with the old page, so start again.
  useEffect(() => {
    if (!hydrated || scoringStarted.current) return;
    if (saved.phase === "report" && !saved.report && saved.session) {
      const { session } = saved;
      run(() => score(session, saved));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, after hydration
  }, [hydrated]);

  const onRestart = () => {
    clear();
    setSaved(EMPTY);
    setError(null);
    setHeader(null);
    setScored([]);
    scoringStarted.current = false;
  };

  if (!hydrated) return null;

  return (
    <>
      {saved.phase === "setup" && (
        <SetupForm onStart={async (file, setup) => { await onStart(file, setup); }} error={error} busy={busy} stage={stage} />
      )}

      {saved.phase === "practice" && saved.session && (
        <Practice
          key={saved.session.current}
          session={saved.session}
          spoken={saved.spoken[saved.session.questions[saved.session.current].id]}
          onSpoken={(id, text) => update({ ...saved, spoken: { ...saved.spoken, [id]: text } })}
          onAnswer={onAnswer}
          onEnd={onRestart}
          busy={busy}
          error={error}
        />
      )}

      {saved.phase === "report" && saved.session && (
        <ReportView
          header={saved.report ?? header ?? headerFrom(saved.session)}
          slots={slotsFor(saved.session, saved.report?.items ?? scored)}
          onRestart={onRestart}
          error={saved.report ? null : error}
          onRetry={() => saved.session && run(() => score(saved.session!, saved))}
        />
      )}
    </>
  );
}

/** The report's header before the server's arrives (it is the first frame, so
 *  this shows for moments). The server's says whether the garden was read. */
function headerFrom(session: Session): Omit<Report, "items"> {
  const { company, role, seniority, difficulty, garden } = session.setup;
  return { session_id: session.session_id, company, role, seniority, difficulty, garden_used: Boolean(garden) };
}

/** One slot per question, in question order, with its result once it has one. */
function slotsFor(session: Session, results: (QuestionReport | null)[]): Slot[] {
  return session.questions.map((question, i) => ({
    question,
    answer: session.answers[i]?.text ?? "",
    result: results[i] ?? null,
  }));
}
