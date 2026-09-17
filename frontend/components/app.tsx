"use client";

import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { Practice } from "@/components/practice";
import { ReportView } from "@/components/report-view";
import { SetupForm } from "@/components/setup-form";
import { SignIn } from "@/components/sign-in";
import { Button } from "@/components/ui/button";
import { ApiError, getReport, startInterview, submitAnswer, uploadResume } from "@/lib/api";
import { signOut, useAuth } from "@/lib/auth";
import { EMPTY, clear, load, save, type Saved } from "@/lib/store";
import type { SetupInput } from "@/lib/types";

/** Top-level flow: setup → practice → report. Owns the session and persists it. */
export function App() {
  const { user, configured } = useAuth();
  const [saved, setSaved] = useState<Saved>(EMPTY);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<"idle" | "uploading" | "starting">("idle");
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
      if (err instanceof ApiError && err.status === 401) {
        // Token rejected: the session is over. Back to the gate with the reason.
        await signOut();
      }
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
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

  if (!hydrated || user === undefined) return null;

  if (!user) {
    return (
      <main className="min-h-screen px-4 py-10 sm:px-6 sm:py-16">
        <SignIn configured={configured} />
      </main>
    );
  }

  return (
    // reducedMotion="user" turns every framer-motion animation into an instant
    // change when the OS "Reduce Motion" setting is on.
    <MotionConfig reducedMotion="user">
    <main className="min-h-screen px-4 py-10 sm:px-6 sm:py-16">
      <div className="mx-auto mb-6 flex w-full max-w-4xl items-center justify-end gap-3 text-xs text-muted-foreground">
        <span>{user.email}</span>
        <Button variant="ghost" size="sm" onClick={() => void signOut().then(onRestart)}>
          Sign out
        </Button>
      </div>
      {saved.phase === "setup" && (
        <SetupForm onStart={onStart} error={error} busy={busy} stage={stage} />
      )}

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
              Scoring your five answers against the rubric. This usually takes under a minute.
            </p>
          )}
        </div>
      )}

      {saved.phase === "report" && saved.report && <ReportView report={saved.report} onRestart={onRestart} />}
    </main>
    </MotionConfig>
  );
}
