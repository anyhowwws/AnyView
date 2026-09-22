"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Mic, MicOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { VoiceAnswer } from "@/components/voice-answer";
import { ApiError, askQuestion } from "@/lib/api";
import { loadVoicePreference, saveVoicePreference } from "@/lib/store";
import { DonnaVoice, microphoneSupported } from "@/lib/voice";
import type { Session } from "@/lib/types";

interface Props {
  session: Session;
  spoken: string | undefined; // already-streamed text for this question (after a reload)
  onSpoken: (questionId: number, text: string) => void;
  onAnswer: (text: string) => Promise<void>;
  busy: boolean;
  error: string | null;
}

/** How long a transcript sits on screen before it is sent, so a misheard word
 *  can be caught. Short enough that the conversation keeps its rhythm. */
const REVIEW_SECONDS = 4;

/** The candidate's turn, once Donna has finished speaking. `typing` is both the
 *  silent path and the escape hatch from any voice state. */
type Turn = "typing" | "listening" | "reviewing";

/** The Practice surface: one question centred, streaming text, a typing
 *  indicator, a thin progress rail. Nothing else on screen. In voice mode the
 *  question is also spoken, and the microphone opens when she stops (ADR 0013). */
export function Practice({ session, spoken, onSpoken, onAnswer, busy, error }: Props) {
  const question = session.questions[session.current];
  const total = session.questions.length;
  const [text, setText] = useState(spoken ?? "");
  const [streaming, setStreaming] = useState(spoken === undefined);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [attempt, setAttempt] = useState(0);

  const [voiceOn, setVoiceOn] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false); // preference read, audio unlocked or not
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  // The ask effect needs the setting at the moment it fires, but must not
  // re-run when it changes: turning voice on mid-question would abandon the
  // stream and pay for the same question twice.
  const wantsVoice = useRef(false);
  const [turn, setTurn] = useState<Turn>("typing");
  const [countdown, setCountdown] = useState<number | null>(null);
  // One player for the whole practice run; it holds the AudioContext, which a
  // browser only lets us open in response to a click.
  const donna = useRef<DonnaVoice | null>(null);
  if (donna.current === null && typeof window !== "undefined") donna.current = new DonnaVoice();

  useEffect(() => {
    // Restore the preference before asking, so the first question of a run is
    // spoken too. Reaching this screen took clicks, so the page normally
    // already has the user activation that audio needs.
    if (!loadVoicePreference() || !microphoneSupported()) {
      setVoiceReady(true);
      return;
    }
    donna.current
      ?.enable()
      .then(() => {
        wantsVoice.current = true;
        setVoiceOn(true);
      })
      .catch(() => setVoiceNote("Turn voice on to hear Donna ask the question."))
      .finally(() => setVoiceReady(true));
  }, []);

  useEffect(() => {
    // Ask once per (question, attempt). The request is sent on the next tick so
    // React's dev-mode double effect (mount, unmount, mount) cancels the first
    // run before any bytes leave the browser — otherwise the server would start
    // a paid model call for a request the client immediately abandons. The
    // cleanup also aborts an in-flight stream when the question changes.
    if (!voiceReady) return; // wait for the preference, so we ask only once
    const voice = donna.current;
    const speaking = wantsVoice.current && voice !== null && voice.ready;

    if (spoken !== undefined) {
      // Re-entering a question we already have the text for: nothing to stream,
      // so it is the candidate's turn straight away.
      if (wantsVoice.current) setTurn("listening");
      return;
    }

    const controller = new AbortController();
    let collected = "";
    setText("");
    setStreaming(true);
    setStreamError(null);
    setTurn("typing");

    // Her voice arriving is what hands the turn over; without it, the end of
    // the text does.
    let audioExpected = speaking;
    if (voice) {
      voice.stop();
      voice.onFinished = () => setTurn("listening");
    }

    const timer = setTimeout(() => {
      askQuestion(
        session,
        {
          onToken: (delta) => {
            collected += delta;
            setText(collected);
          },
          onAudio: (b64) => voice?.play(b64),
          onVoiceOff: (message) => {
            audioExpected = false;
            setVoiceNote(message);
          },
        },
        controller.signal,
        speaking,
      )
        .then(() => {
          setStreaming(false);
          onSpoken(question.id, collected);
          if (audioExpected) voice?.markComplete();
          else if (wantsVoice.current) setTurn("listening");
        })
        .catch((err: unknown) => {
          if ((err as Error).name === "AbortError") return;
          setStreaming(false);
          setStreamError(err instanceof ApiError ? err.message : "Something went wrong.");
        });
    }, 0);

    return () => {
      clearTimeout(timer);
      controller.abort();
      voice?.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id, attempt, spoken, voiceReady]);

  // A transcript is sent on its own after a beat, so a spoken interview needs
  // no clicking. Any edit, or "Send now", takes over from the timer.
  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setCountdown(null);
      void submit();
      return;
    }
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countdown]);

  function submit() {
    const trimmed = answer.trim();
    if (!trimmed || busy) return;
    setCountdown(null);
    return onAnswer(trimmed).then(() => {
      setAnswer("");
      setTurn(voiceOn ? "listening" : "typing");
    });
  }

  function toggleVoice() {
    if (voiceOn) {
      donna.current?.stop();
      wantsVoice.current = false;
      setVoiceOn(false);
      setTurn("typing");
      saveVoicePreference(false);
      return;
    }
    if (!microphoneSupported()) {
      setVoiceNote("This browser can't record audio. Chrome, Edge, Safari and Firefox all can.");
      return;
    }
    // This click is the user gesture that lets the page play audio at all.
    donna.current
      ?.enable()
      .then(() => {
        wantsVoice.current = true;
        setVoiceOn(true);
        saveVoicePreference(true);
        setVoiceNote(null);
        // This question is already streaming or streamed, so she stays silent
        // for it — re-asking would pay for the same question twice. The
        // microphone opens as soon as the words are on screen.
        if (!streaming) setTurn("listening");
      })
      .catch(() => setVoiceNote("This browser is blocking audio playback on the page."));
  }

  const canAnswer = !streaming && !streamError && answer.trim().length > 0 && !busy;

  return (
    <div className="workspace-panel mx-auto flex w-full max-w-3xl flex-col gap-8">
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
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleVoice}
          aria-pressed={voiceOn}
          data-icon="inline-start"
          title={voiceOn ? "Switch to typing" : "Speak with Donna out loud"}
        >
          {voiceOn ? <Mic className="size-3.5" /> : <MicOff className="size-3.5" />}
          {voiceOn ? "Voice on" : "Voice off"}
        </Button>
      </div>

      <AnimatePresence mode="wait">
        <motion.section
          key={question.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
          className="min-h-40 space-y-4"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Donna · {question.competency}
          </p>
          <p className="text-xl leading-relaxed sm:text-2xl" aria-hidden={streaming}>
            {text}
            {streaming && <TypingDots />}
          </p>
          {/* One announcement per question for screen readers, not one per token. */}
          <p className="sr-only" role="status">
            {streaming ? "Donna is speaking." : text}
          </p>
          {streamError && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-destructive" role="alert">
              <span>{streamError}</span>
              <Button variant="outline" className="h-10" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </Button>
            </div>
          )}
        </motion.section>
      </AnimatePresence>

      {voiceNote && (
        <p className="text-sm text-muted-foreground" role="status">
          {voiceNote}
        </p>
      )}

      {voiceOn && turn === "listening" && !streaming && !streamError ? (
        <VoiceAnswer
          sessionId={session.session_id}
          onTranscript={(spokenText) => {
            setAnswer(spokenText);
            setTurn("reviewing");
            setCountdown(REVIEW_SECONDS);
          }}
          onError={(message) => {
            setVoiceNote(message);
            setTurn("typing");
          }}
          onTypeInstead={() => setTurn("typing")}
        />
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canAnswer) return;
            void submit();
          }}
        >
          <Textarea
            value={answer}
            onChange={(e) => {
              setAnswer(e.target.value);
              setCountdown(null); // an edit means they want to look it over
            }}
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
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              {turn === "reviewing"
                ? "Heard that — edit anything Donna got wrong."
                : `${answer.length.toLocaleString()} / 4,000`}
            </span>
            <div className="flex items-center gap-2">
              {voiceOn && turn === "reviewing" && (
                <Button
                  variant="ghost"
                  className="h-11"
                  onClick={() => {
                    setCountdown(null);
                    setAnswer("");
                    setTurn("listening");
                  }}
                  type="button"
                >
                  Say it again
                </Button>
              )}
              <Button type="submit" disabled={!canAnswer} className="h-11 px-5 text-base">
                {busy
                  ? "Sending…"
                  : countdown !== null
                    ? `Sending in ${countdown}…`
                    : session.current + 1 === total
                      ? "Finish"
                      : "Next question"}
              </Button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}

function TypingDots() {
  return (
    <span className="ml-1 inline-flex gap-0.5 align-middle" aria-label="Donna is typing">
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
