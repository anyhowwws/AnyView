"use client";

import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { Practice } from "@/components/practice";
import { ReportView } from "@/components/report-view";
import { SetupForm } from "@/components/setup-form";
import { ApiError, getReport, startInterview, submitAnswer } from "@/lib/api";
import { EMPTY, clear, load, save, type Saved } from "@/lib/store";
import type { Setup } from "@/lib/types";

/** Top-level flow: setup → practice → report. Owns the session and persists it. */
export function App() {
  const [saved, setSaved] = useState<Saved>(EMPTY);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // sessionStorage only exists in the browser; read it after mount.
    setSaved(load());
    setHydrated(true);
  }, []);

  function update(next: Saved) {
    setSaved(next);
    save(next);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const onStart = (setup: Setup) =>
    run(async () => {
      const session = await startInterview(crypto.randomUUID(), setup);
      update({ phase: "practice", session, report: null, spoken: {} });
    });

  const onAnswer = (text: string) =>
    run(async () => {
      if (!saved.session) return;
      const q = saved.session.questions[saved.session.current];
      const session = await submitAnswer(saved.session, { question_id: q.id, text });
      if (session.state === "wrap") {
        update({ ...saved, session, phase: "report" });
        const report = await getReport(session);
        update({ ...saved, session, phase: "report", report });
      } else {
        update({ ...saved, session });
      }
    });

  const onRestart = () => {
    clear();
    setSaved(EMPTY);
    setError(null);
  };

  if (!hydrated) return null;

  return (
    // reducedMotion="user" turns every framer-motion animation into an instant
    // change when the OS "Reduce Motion" setting is on.
    <MotionConfig reducedMotion="user">
    <main className="min-h-screen px-4 py-10 sm:px-6 sm:py-16">
      {saved.phase === "setup" && <SetupForm onStart={onStart} error={error} busy={busy} />}

      {saved.phase === "practice" && saved.session && (
        <Practice
          key={saved.session.current}
          session={saved.session}
          spoken={saved.spoken[saved.session.questions[saved.session.current].id]}
          onSpoken={(id, text) => update({ ...saved, spoken: { ...saved.spoken, [id]: text } })}
          onAnswer={onAnswer}
          busy={busy}
          error={error}
        />
      )}

      {saved.phase === "report" && !saved.report && (
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-3 py-24 text-center">
          {error ? (
            <>
              <p className="text-sm text-destructive" role="alert">{error}</p>
              <button
                className="text-sm underline underline-offset-4"
                onClick={() => saved.session && run(async () => {
                  const report = await getReport(saved.session!);
                  update({ ...saved, report });
                })}
              >
                Try again
              </button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground" role="status">
              Scoring your five answers against the rubric. This takes about a minute.
            </p>
          )}
        </div>
      )}

      {saved.phase === "report" && saved.report && <ReportView report={saved.report} onRestart={onRestart} />}
    </main>
    </MotionConfig>
  );
}
