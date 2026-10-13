"use client";

import { useEffect, useRef, useState } from "react";
import { Practice } from "@/components/practice";
import { Preflight } from "@/components/preflight";
import { ReportView } from "@/components/report-view";
import { ScoringWait } from "@/components/scoring-wait";
import { SetupForm } from "@/components/setup-form";
import { ApiError, startInterview, streamReport, submitAnswer, uploadResume } from "@/lib/api";
import { signOut } from "@/lib/auth";
import { EMPTY, clear, load, save, type Saved } from "@/lib/store";
import { releaseMicrophone } from "@/lib/voice";
import type { Session, SetupInput } from "@/lib/types";

/** Top-level flow: setup → practice → report. Owns the session and persists it. */
export function App() {
  const [saved, setSaved] = useState<Saved>(EMPTY);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<"idle" | "uploading" | "starting">("idle");
  // Between Start and Begin (ADR 0028): the questions are being planned while
  // the pre-flight checks the microphone and speaker. Not persisted — a reload
  // here goes back to setup, and nothing has been asked yet.
  const [preparing, setPreparing] = useState<{ sessionId: string; session: Session | null } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  // How many answers are scored so far, from the stream. Not persisted: a
  // reload re-scores, since the stream that was counting is gone.
  const [scoredCount, setScoredCount] = useState(0);
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

  const onStart = (file: File | null, setup: Omit<SetupInput, "resume_object">) => {
    // The pre-flight shows at once; planning runs behind it.
    const sessionId = crypto.randomUUID();
    setPreparing({ sessionId, session: null });
    return run(async () => {
      try {
        let input: SetupInput = setup;
        if (file) {
          setStage("uploading");
          input = { ...setup, resume_object: await uploadResume(file) };
        }
        setStage("starting");
        const session = await startInterview(sessionId, input);
        // Ignore a plan that lands after "Back to setup".
        setPreparing((p) => (p?.sessionId === sessionId ? { ...p, session } : p));
      } finally {
        setStage("idle");
      }
    });
  };

  // The microphone stays open for the whole interview and no longer than that.
  useEffect(() => {
    if (!preparing && saved.phase !== "practice") releaseMicrophone();
  }, [preparing, saved.phase]);

  /** Stream the report in, counting answers as they are scored; the report
   *  itself is shown and saved only once it is whole. */
  async function score(session: Session, base: Saved) {
    scoringStarted.current = true;
    setScoredCount(0);
    const report = await streamReport(session, {
      onItem: () => setScoredCount((n) => n + 1),
    });
    update({ ...base, session, phase: "report", report });
  }

  const onAnswer = (text: string, cutOff: boolean) =>
    run(async () => {
      if (!saved.session) return;
      const q = saved.session.questions[saved.session.current];
      const session = await submitAnswer(saved.session, {
        question_id: q.id,
        text,
        cut_off: cutOff,
      });
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
    setScoredCount(0);
    scoringStarted.current = false;
  };

  if (!hydrated) return null;

  return (
    <>
      {preparing && (
        <Preflight
          sessionId={preparing.sessionId}
          ready={preparing.session !== null}
          error={error}
          onBegin={() => {
            if (!preparing.session) return;
            update({ phase: "practice", session: preparing.session, report: null, spoken: {} });
            setPreparing(null);
          }}
          onBack={() => {
            setPreparing(null);
            setError(null);
          }}
        />
      )}

      {saved.phase === "setup" && !preparing && (
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

      {saved.phase === "report" && !saved.report && saved.session && (
        <ScoringWait
          scored={scoredCount}
          total={saved.session.questions.length}
          error={error}
          onRetry={() => saved.session && run(() => score(saved.session!, saved))}
        />
      )}

      {saved.phase === "report" && saved.report && <ReportView report={saved.report} onRestart={onRestart} />}
    </>
  );
}
