"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, askQuestion } from "@/lib/api";
import type { Session } from "@/lib/types";

interface Props {
  session: Session;
  spoken: string | undefined; // already-streamed text for this question (after a reload)
  onSpoken: (questionId: number, text: string) => void;
  onAnswer: (text: string) => Promise<void>;
  busy: boolean;
  error: string | null;
}

/** The Practice surface: one question centred, streaming text, a typing
 *  indicator, a thin progress rail. Nothing else on screen. */
export function Practice({ session, spoken, onSpoken, onAnswer, busy, error }: Props) {
  const question = session.questions[session.current];
  const total = session.questions.length;
  const [text, setText] = useState(spoken ?? "");
  const [streaming, setStreaming] = useState(spoken === undefined);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [attempt, setAttempt] = useState(0);
  const askedFor = useRef<string | null>(null);

  useEffect(() => {
    // Ask once per (question, attempt). The ref guards React's dev-mode double
    // effect; the AbortController stops the stream if the user navigates away.
    const key = `${question.id}:${attempt}`;
    if (spoken !== undefined || askedFor.current === key) return;
    askedFor.current = key;

    const controller = new AbortController();
    let collected = "";
    setText("");
    setStreaming(true);
    setStreamError(null);

    askQuestion(
      session,
      (delta) => {
        collected += delta;
        setText(collected);
      },
      controller.signal,
    )
      .then(() => {
        setStreaming(false);
        onSpoken(question.id, collected);
      })
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        setStreaming(false);
        setStreamError(err instanceof ApiError ? err.message : "Something went wrong.");
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id, attempt, spoken]);

  const canAnswer = !streaming && !streamError && answer.trim().length > 0 && !busy;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
          <motion.div
            className="h-full bg-primary"
            initial={false}
            animate={{ width: `${((session.current + (streaming ? 0.5 : 1)) / total) * 100}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>
        <span className="tabular-nums">
          {session.current + 1} / {total}
        </span>
      </div>

      <AnimatePresence mode="wait">
        <motion.section
          key={question.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
          className="min-h-40 space-y-4"
          aria-live="polite"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Maya · {question.competency}
          </p>
          <p className="text-xl leading-relaxed sm:text-2xl">
            {text}
            {streaming && <TypingDots />}
          </p>
          {streamError && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-destructive" role="alert">
              <span>{streamError}</span>
              <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </Button>
            </div>
          )}
        </motion.section>
      </AnimatePresence>

      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!canAnswer) return;
          void onAnswer(answer.trim()).then(() => setAnswer(""));
        }}
      >
        <Textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder={streaming ? "Listening…" : "Your answer"}
          rows={6}
          maxLength={4000}
          disabled={streaming || !!streamError}
          aria-label="Your answer"
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{answer.length.toLocaleString()} / 4,000</span>
          <Button type="submit" disabled={!canAnswer}>
            {busy ? "Sending…" : session.current + 1 === total ? "Finish" : "Next question"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="ml-1 inline-flex gap-0.5 align-middle" aria-label="Maya is typing">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="inline-block size-1.5 rounded-full bg-muted-foreground"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  );
}
