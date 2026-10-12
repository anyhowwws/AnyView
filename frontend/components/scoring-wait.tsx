"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

interface Props {
  scored: number;
  total: number;
  error: string | null;
  onRetry: () => void;
}

/** The wait between the last answer and the report. Answers are scored in
 *  parallel and finish in any order, so this counts them rather than showing
 *  them: the report appears whole, in question order, once the last is in. */
export function ScoringWait({ scored, total, error, onRetry }: Props) {
  const seconds = useElapsed();

  if (error) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-3 py-24 text-center">
        <p className="text-sm text-destructive" role="alert">{error}</p>
        <button className="text-sm underline underline-offset-4" onClick={onRetry}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-24 text-center" role="status">
      <Loader2 size={28} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden />
      <p className="text-sm">Scoring your answers against the rubric…</p>
      <div className="flex w-48 gap-1" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-500 ${i < scored ? "bg-primary" : "bg-muted-foreground/25"}`}
          />
        ))}
      </div>
      <p className="text-xs tabular-nums text-muted-foreground">
        {scored} of {total} done · {seconds} s · usually under a minute
      </p>
    </div>
  );
}

function useElapsed(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}
