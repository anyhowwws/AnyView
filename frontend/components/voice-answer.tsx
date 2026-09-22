"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, transcribeAnswer, uploadAnswerAudio } from "@/lib/api";
import { listen, type ListenEnd, type ListenHandle } from "@/lib/voice";

interface Props {
  sessionId: string;
  /** The recording ends by itself after a pause; this is the text that came back. */
  onTranscript: (text: string) => void;
  onError: (message: string) => void;
  /** The candidate gave up on the microphone for this question. */
  onTypeInstead: () => void;
}

/** The candidate's turn: an open microphone that closes itself when they stop
 *  talking, then the recording on its way to being transcribed (ADR 0013). */
export function VoiceAnswer({ sessionId, onTranscript, onError, onTypeInstead }: Props) {
  const [phase, setPhase] = useState<"listening" | "working">("listening");
  const [level, setLevel] = useState(0);
  const handle = useRef<ListenHandle | null>(null);

  useEffect(() => {
    let live = true;

    async function send(blob: Blob, contentType: string, reason: ListenEnd | "manual") {
      if (reason === "no-speech") {
        onError("We didn't hear anything. Check your microphone, or type your answer.");
        return;
      }
      setPhase("working");
      try {
        const object = await uploadAnswerAudio(blob, contentType);
        const text = await transcribeAnswer(sessionId, object);
        if (live) onTranscript(text);
      } catch (err) {
        if (!live) return;
        setPhase("listening");
        onError(err instanceof ApiError ? err.message : "That recording didn't go through.");
      }
    }

    void listen({
      onLevel: (l) => live && setLevel(l),
      onEnd: (recording, reason) => {
        if (live) void send(recording.blob, recording.contentType, reason);
      },
      onError: (message) => live && onError(message),
    }).then((h) => {
      handle.current = h;
      // Unmounted while the permission prompt was open: drop the recording.
      if (!live) h.cancel();
    });

    return () => {
      live = false;
      handle.current?.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  if (phase === "working") {
    return (
      <div className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
        <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
        Writing down what you said…
      </div>
    );
  }

  // The meter is a rough loudness reading, so it is scaled generously: an
  // ordinary speaking voice should visibly move it.
  const loudness = Math.min(1, level * 12);

  return (
    <div className="flex flex-col gap-4">
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
        <div className="flex-1">
          <p className="text-sm font-medium" role="status">
            Listening — answer out loud.
          </p>
          <p className="text-xs text-muted-foreground">
            Stop talking for a couple of seconds and Donna takes it from there.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="h-10"
          onClick={() => handle.current?.stop()}
          data-icon="inline-start"
        >
          <Square className="size-3.5" />
          I&apos;m done
        </Button>
        <Button variant="ghost" className="h-10" onClick={onTypeInstead}>
          Type this one instead
        </Button>
      </div>
    </div>
  );
}
