"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Keyboard, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { LiveAnswer } from "@/components/live-answer";
import { NO_ANSWER, VoiceAnswer } from "@/components/voice-answer";
import { ApiError, askQuestion, interjection } from "@/lib/api";
import { liveAvailable, markLiveBroken } from "@/lib/live";
import { loadVoicePreference, saveVoicePreference } from "@/lib/store";
import { harveyVoice, microphoneSupported, type ListenEnd, type VoicePlayer } from "@/lib/voice";
import type { FollowUp, Session } from "@/lib/types";

interface Props {
  session: Session;
  spoken: string | undefined; // already-streamed text for this question (after a reload)
  onSpoken: (questionId: number, text: string) => void;
  /** `cutOff`: the clock or Harvey ended the answer, so the next question
   *  opens without thanking them for it (ADR 0028). `followUps`: asked on Live
   *  (ADR 0031), scored with the answer. */
  onAnswer: (text: string, cutOff: boolean, followUps?: FollowUp[]) => Promise<boolean>;
  onEnd: () => void;
  busy: boolean;
  error: string | null;
}

/** The candidate's turn, once Harvey has finished speaking. `typing` is both the
 *  silent path and the escape hatch from any voice state. `sending` is a spoken
 *  answer on its way: it goes straight in, as it would in a real interview,
 *  and is shown only if sending it fails. `live` is the whole question as one
 *  Gemini Live conversation (ADR 0031): asking, answering and follow-ups. */
type Turn = "typing" | "listening" | "sending" | "live";

/** The Practice surface: one question centred, streaming text, a typing
 *  indicator, a thin progress rail. Speaking is the default — the question is
 *  spoken and the microphone opens when Harvey stops (ADR 0013) — and when the
 *  interview is time-bounded each question carries its own clock (ADR 0016). */
export function Practice({ session, spoken, onSpoken, onAnswer, onEnd, busy, error }: Props) {
  const question = session.questions[session.current];
  const total = session.questions.length;
  const timed = session.setup.time_bounded;
  const [text, setText] = useState(spoken ?? "");
  const [streaming, setStreaming] = useState(spoken === undefined);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [ending, setEnding] = useState(false);

  const [voiceOn, setVoiceOn] = useState(false);
  const [voiceReady, setVoiceReady] = useState(false); // preference read, audio unlocked or not
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  // The ask effect needs the setting at the moment it fires, but must not
  // re-run when it changes: switching mode mid-question would abandon the
  // stream and pay for the same question twice.
  const wantsVoice = useRef(false);
  const [turn, setTurn] = useState<Turn>("typing");
  // Set when switching to speaking: ask this question again, aloud, even though
  // its text is already here.
  const reask = useRef(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  // One player for the whole interview, shared across these per-question
  // mounts, so a clip from the last question plays out under the next (ADR 0028).
  const harvey = useRef<VoicePlayer | null>(null);
  if (harvey.current === null && typeof window !== "undefined") harvey.current = harveyVoice();
  // Which (question, attempt) the Live conversation was opened for.
  const liveKey = useRef<string | null>(null);

  useEffect(() => {
    // Speaking is the default, so this normally just unlocks audio. Getting
    // here took clicks, which is the user activation a browser demands.
    if (!loadVoicePreference() || !microphoneSupported()) {
      setVoiceReady(true);
      return;
    }
    harvey.current
      ?.enable()
      .then(() => {
        wantsVoice.current = true;
        setVoiceOn(true);
      })
      .catch(() => setVoiceNote("Switch to speaking to hear Harvey ask the question."))
      .finally(() => setVoiceReady(true));
  }, []);

  useEffect(() => {
    // Ask once per (question, attempt). The request is sent on the next tick so
    // React's dev-mode double effect (mount, unmount, mount) cancels the first
    // run before any bytes leave the browser — otherwise the server would start
    // a paid model call for a request the client immediately abandons. The
    // cleanup also aborts an in-flight stream when the question changes.
    if (!voiceReady) return; // wait for the preference, so we ask only once
    const voice = harvey.current;
    const speaking = wantsVoice.current && voice !== null && voice.ready;

    // Speaking, on Live: one conversation does the asking and the answering,
    // so there is nothing to stream from /ask. Harvey re-asks a question we
    // already have the text for, which is what an interviewer would do.
    if (speaking && liveAvailable()) {
      // `onSpoken` changes `spoken`, which re-runs this effect mid-conversation.
      const key = `${question.id}:${attempt}`;
      if (liveKey.current === key) return;
      liveKey.current = key;
      reask.current = false;
      // The planned question, not Live's transcript of it: that arrives late
      // and in fragments, and its tail used to land in the follow-up line.
      setText(question.text);
      setStreaming(true);
      setStreamError(null);
      setTurn("live");
      return () => voice?.detach();
    }

    if (spoken !== undefined && !reask.current) {
      // Re-entering a question we already have the text for: nothing to stream,
      // so it is the candidate's turn straight away.
      if (wantsVoice.current) setTurn("listening");
      return;
    }
    reask.current = false;

    const controller = new AbortController();
    let collected = "";
    setText("");
    setStreaming(true);
    setStreamError(null);
    setTurn("typing");

    // The voice arriving is what hands the turn over; without it, the end of
    // the text does.
    let audioExpected = speaking;
    // Not stop(): whatever Harvey is still saying ("let's move on") plays to the
    // end, and this question's clips queue behind it.
    if (voice) voice.onFinished = () => setTurn("listening");

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
      voice?.detach();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question.id, attempt, spoken, voiceReady]);

  // --- The clock (ADR 0016) -------------------------------------------------
  // It starts when the candidate's turn does, which is when the question has
  // finished arriving. Sending a spoken answer is not answering, so it stops —
  // and neither is deciding whether to walk out, or the answer would be sent
  // from under the confirmation.
  const answering =
    timed && !streaming && !streamError && turn !== "sending" && !busy && !ending;

  // A pause holds the remainder rather than resetting it: opening the "end
  // interview" confirmation and thinking better of it must not hand out a
  // fresh two minutes, and must not eat the time either.
  const held = useRef<number | null>(null);

  useEffect(() => {
    held.current = null; // a new question brings a new clock
  }, [question.id]);

  // When the countdown reaches zero, as a ref so a follow-up can move it (ADR 0040).
  const deadlineAt = useRef(0);

  useEffect(() => {
    if (!answering) {
      setRemaining(null);
      return;
    }
    deadlineAt.current = performance.now() + (held.current ?? question.seconds * 1000);
    setRemaining(Math.ceil((deadlineAt.current - performance.now()) / 1000));
    const tick = setInterval(() => {
      const left = Math.max(0, Math.ceil((deadlineAt.current - performance.now()) / 1000));
      setRemaining(left);
      if (left === 0) clearInterval(tick);
    }, 250);
    return () => {
      clearInterval(tick);
      held.current = Math.max(0, deadlineAt.current - performance.now());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answering, question.id]);

  /** Harvey is following up: give the question more time, on the screen's
   *  countdown as well as in the cue clock that actually ends it (ADR 0040). */
  function extendClock(extraMs: number) {
    deadlineAt.current += extraMs;
    setRemaining(Math.max(0, Math.ceil((deadlineAt.current - performance.now()) / 1000)));
  }

  // Once per question. Without this a failed send looped: `busy` pauses the
  // clock, the pause holds 0 s, resuming sets `remaining` to 0 again, and that
  // fired the send again — thousands of requests a minute while the API was down.
  const timedOut = useRef(false);

  useEffect(() => {
    // Only the typed path is enforced here. When the microphone is open the
    // recorder owns the cut-off, because it has to stop the recording at the
    // same instant.
    if (remaining !== 0 || turn === "listening" || turn === "live" || !answering || timedOut.current) {
      return;
    }
    timedOut.current = true;
    const text = answer.trim() || NO_ANSWER;
    setAnswer(text); // so a failed send can be sent again by hand
    void interject("time_up");
    void submit(text, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining]);

  // The last question closes the interview, so a cut-in there is a goodbye,
  // not "let's move on" (ADR 0032). Once per interview.
  const last = session.current + 1 === total;
  const saidGoodbye = useRef(false);

  async function interject(line: "time_up" | "stalled" | "move_on" | "goodbye") {
    if (!wantsVoice.current) return;
    if (last && (line === "time_up" || line === "move_on")) line = "goodbye";
    if (line === "goodbye") {
      if (saidGoodbye.current) return;
      saidGoodbye.current = true;
    }
    const clip = await interjection(session.session_id, line);
    if (clip) harvey.current?.play(clip);
  }

  function submit(override?: string, cutOff = false) {
    const trimmed = (override ?? answer).trim();
    if (!trimmed || busy) return;
    return onAnswer(trimmed, cutOff).then((saved) => {
      if (!saved) return;
      // Turn-based voice has no Harvey to close the interview himself.
      if (last) void interject("goodbye");
      setAnswer("");
      setTurn(voiceOn ? "listening" : "typing");
    });
  }

  function chooseVoice(on: boolean) {
    if (on === voiceOn) return;
    if (!on) {
      harvey.current?.stop();
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
    harvey.current
      ?.enable()
      .then(() => {
        wantsVoice.current = true;
        setVoiceOn(true);
        saveVoicePreference(true);
        setVoiceNote(null);
        // Ask this question again, aloud. It costs one more short call, and
        // opening the microphone on a question Harvey never said left people
        // waiting for Harvey to speak — until Harvey asked whether to move on.
        harvey.current?.stop();
        reask.current = true;
        setAttempt((n) => n + 1);
      })
      .catch(() => setVoiceNote("This browser is blocking audio playback on the page."));
  }

  /** A Live answer goes straight in, follow-ups and all. If sending fails, the
   *  transcript lands in the typed box so it can be sent again by hand. */
  function onLiveAnswer(live: { text: string; cut_off?: boolean; follow_ups?: FollowUp[] }) {
    setAnswer(live.text);
    setTurn("sending");
    void onAnswer(live.text, !!live.cut_off, live.follow_ups).then((saved) => {
      if (!saved) return;
      setAnswer("");
    });
  }

  /** The candidate pressed "Next question" (or "Finish") on Live. On the last
   *  question Harvey never got to say goodbye, so the fixed line does. */
  function onLiveEnd() {
    if (last) void interject("goodbye");
  }

  /** Live failed for a reason of its own: carry on with the turn-based voice
   *  path for the rest of the interview, starting with this question. */
  function onLiveFallback(message: string) {
    markLiveBroken();
    setVoiceNote(`${message} Carrying on with standard voice mode.`);
    reask.current = true;
    setAttempt((n) => n + 1);
  }

  /** Every spoken answer goes straight in. If the clock or the silence ended
   *  it, Harvey has already said "let's move on", so the next question won't
   *  thank them for it. */
  function onTranscript(spokenText: string, reason: ListenEnd | "manual") {
    setAnswer(spokenText);
    setTurn("sending");
    void submit(spokenText, reason === "limit" || reason === "no-speech");
  }

  const canAnswer = !streaming && !streamError && answer.trim().length > 0 && !busy;
  const answered = session.answers.length;

  return (
    <div className="workspace-panel mx-auto flex w-full max-w-3xl flex-col gap-8">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <div className="h-1 min-w-24 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
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

        {remaining !== null && (
          <span
            className={`tabular-nums font-medium ${remaining <= 30 ? "text-destructive" : ""}`}
            role="timer"
            aria-label={`${remaining} seconds left for this answer`}
          >
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
          </span>
        )}

        <div className="answer-mode" role="radiogroup" aria-label="How do you want to answer?">
          <button
            type="button"
            role="radio"
            aria-checked={voiceOn}
            onClick={() => chooseVoice(true)}
          >
            <Mic className="size-3.5" aria-hidden />
            Answer by speaking
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={!voiceOn}
            onClick={() => chooseVoice(false)}
          >
            <Keyboard className="size-3.5" aria-hidden />
            Answer by typing
          </button>
        </div>

        <Button variant="ghost" size="sm" onClick={() => setEnding(true)}>
          End interview
        </Button>
      </div>

      {ending && (
        <div className="end-confirm" role="alertdialog" aria-label="End this interview?">
          <div>
            <strong>End this interview?</strong>
            <p>
              You are on question {session.current + 1} of {total}.{" "}
              {answered > 0
                ? `Your ${answered} ${answered === 1 ? "answer" : "answers"} will be discarded and you won't get a report.`
                : "Nothing will be saved."}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" className="h-10" onClick={() => setEnding(false)}>
              Keep going
            </Button>
            <Button
              variant="destructive"
              className="h-10"
              onClick={() => {
                harvey.current?.stop();
                onEnd();
              }}
            >
              End and discard
            </Button>
          </div>
        </div>
      )}

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
            Harvey · {question.competency}
          </p>
          <p className="text-xl leading-relaxed sm:text-2xl" aria-hidden={streaming}>
            {text}
            {streaming && <TypingDots />}
          </p>
          {/* One announcement per question for screen readers, not one per token. */}
          <p className="sr-only" role="status">
            {streaming ? "Harvey is speaking." : text}
          </p>
          {streamError && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-destructive" role="alert">
              <span>{streamError}</span>
              <Button
              variant="outline"
              className="h-10"
              onClick={() => {
                harvey.current?.stop();
                setAttempt((n) => n + 1);
              }}
            >
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

      {voiceOn && turn === "live" && !streamError ? (
        <LiveAnswer
          session={session}
          seconds={timed ? question.seconds : null}
          last={last}
          onExtend={extendClock}
          onAsked={() => {
            setStreaming(false);
            onSpoken(question.id, question.text);
          }}
          onInterject={(line) => void interject(line)}
          onEnd={onLiveEnd}
          onAnswer={onLiveAnswer}
          onFallback={onLiveFallback}
          onError={(message) => {
            setVoiceNote(message);
            setStreaming(false);
            setTurn("typing");
          }}
          onTypeInstead={() => {
            setStreaming(false);
            setTurn("typing");
          }}
        />
      ) : voiceOn && turn === "listening" && !streaming && !streamError ? (
        <VoiceAnswer
          sessionId={session.session_id}
          seconds={timed ? question.seconds : null}
          onTranscript={onTranscript}
          onInterject={(line) => void interject(line)}
          onError={(message) => {
            setVoiceNote(message);
            setTurn("typing");
          }}
          onTypeInstead={() => setTurn("typing")}
        />
      ) : voiceOn && turn === "sending" && !error ? (
        <p className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
          <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
          Got it.
        </p>
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
              {turn === "sending"
                ? "Your spoken answer didn't send. Check it, then send it again."
                : `${answer.length.toLocaleString()} / 4,000`}
            </span>
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={!canAnswer} className="h-11 px-5 text-base">
                {busy
                  ? "Sending…"
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
    <span className="ml-1 inline-flex gap-0.5 align-middle" aria-label="Harvey is typing">
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
