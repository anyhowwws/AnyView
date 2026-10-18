"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LiveQuestion } from "@/lib/live";
import type { LiveAction } from "@/lib/live-cues";
import type { Answer, Session } from "@/lib/types";

interface Props {
  session: Session;
  /** The question's clock in seconds, or null when the interview is untimed. */
  seconds: number | null;
  /** What is left of that clock in ms, read once when the conversation opens. */
  timeLeftMs: () => number;
  /** Harvey has already asked this question on Live: he says a short cue
   *  instead of asking it again. Read once when the conversation opens. */
  resumed: boolean;
  /** The interview's last question: the button says "Finish". */
  last: boolean;
  /** Harvey has finished asking; the clock starts. */
  onAsked: () => void;
  /** What is left of the question's clock in ms, null when untimed. Stands
   *  still while Harvey speaks (ADR 0043). */
  onClock: (remainingMs: number | null) => void;
  /** Play one of Harvey's fixed lines: a nudge, or the cut-in that ends the question. */
  onInterject: (line: LiveAction) => void;
  /** The candidate ended the question themselves. */
  onEnd: () => void;
  onAnswer: (answer: Answer) => void;
  /** Live itself failed: carry on with the turn-based voice path. */
  onFallback: (message: string) => void;
  onError: (message: string) => void;
  onTypeInstead: () => void;
}

/** One question on Gemini Live (ADR 0031): Harvey asks, listens, nudges and
 *  follows up in one open conversation. Mounted once per question. */
export function LiveAnswer({
  session,
  seconds,
  timeLeftMs,
  resumed,
  last,
  onAsked,
  onClock,
  onInterject,
  onEnd,
  onAnswer,
  onFallback,
  onError,
  onTypeInstead,
}: Props) {
  const [level, setLevel] = useState(0);
  const [asked, setAsked] = useState(false);
  const [heard, setHeard] = useState("");
  const [followUps, setFollowUps] = useState(0);
  // The follow-up Harvey is asking now, as he declared it to the API. His
  // transcript arrives late and in fragments, so it is never what is shown.
  const [line, setLine] = useState("");
  const conversation = useRef<LiveQuestion | null>(null);
  // The callbacks change on every render of the parent; the socket must not.
  const props = useRef({
    timeLeftMs,
    resumed,
    onAsked,
    onClock,
    onInterject,
    onAnswer,
    onFallback,
    onError,
  });
  props.current = {
    timeLeftMs,
    resumed,
    onAsked,
    onClock,
    onInterject,
    onAnswer,
    onFallback,
    onError,
  };

  useEffect(() => {
    setAsked(false);
    setHeard("");
    setLine("");
    setFollowUps(0);
    const question = new LiveQuestion(
      session,
      {
        onCandidate: (text) => setHeard((prev) => prev + text),
        onAsked: () => {
          setAsked(true);
          props.current.onAsked();
        },
        onClock: (ms) => props.current.onClock(ms),
        onFollowUp: (asked) => {
          setFollowUps((n) => n + 1);
          setLine(asked);
          setHeard("");
        },
        onInterject: (line) => props.current.onInterject(line),
        onLevel: setLevel,
        onDone: (answer) => props.current.onAnswer(answer),
        onError: (message, fallback) =>
          fallback ? props.current.onFallback(message) : props.current.onError(message),
      },
      // What is left, not `seconds`: typing part of the answer and switching
      // back must not start the clock again.
      seconds === null ? null : props.current.timeLeftMs(),
      props.current.resumed,
    );
    conversation.current = question;
    // Next tick, so React's dev-mode double effect never opens a paid session.
    const timer = setTimeout(() => void question.start(), 0);
    return () => {
      clearTimeout(timer);
      question.close();
    };
    // One conversation per question; the session's other fields change with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.session_id, session.current, seconds]);

  const loudness = Math.min(1, level * 12);
  const lastWords = heard.trim().split(/\s+/).slice(-24).join(" ");

  return (
    <div className="flex flex-col gap-4">
      {line.trim() && (
        <p className="border-l-2 border-primary pl-3 text-base leading-relaxed" role="status">
          {line.trim()}
        </p>
      )}
      <div className="flex items-center gap-4">
        <span className="relative inline-flex size-12 items-center justify-center">
          <motion.span
            className="absolute inset-0 rounded-full bg-primary/20"
            animate={{ scale: 1 + loudness * 0.6, opacity: 0.35 + loudness * 0.5 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            aria-hidden
          />
          <span className="relative inline-flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <Mic className="size-4" />
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium" role="status">
            {!asked
              ? "Harvey is asking…"
              : followUps > 0
                ? "Harvey followed up — answer out loud."
                : "Listening — answer out loud."}
          </p>
          <p className="text-xs text-muted-foreground">
            Pause to think whenever you like. Harvey picks it up when you&apos;re done, and you can
            talk over him.
          </p>
        </div>
      </div>
      {lastWords && (
        <p className="truncate text-sm text-muted-foreground" aria-live="off">
          … {lastWords}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="h-10"
          onClick={() => {
            conversation.current?.end("manual");
            onEnd();
          }}
          disabled={!asked}
          data-icon="inline-start"
        >
          <Square className="size-3.5" />
          {last ? "Finish" : "Next question"}
        </Button>
        <Button variant="ghost" className="h-10" onClick={onTypeInstead}>
          Type this one instead
        </Button>
      </div>
    </div>
  );
}
