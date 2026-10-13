"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Mic, ScrollText, Volume2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { interjection } from "@/lib/api";
import { loadVoicePreference, saveVoicePreference } from "@/lib/store";
import {
  donnaVoice,
  microphoneSupported,
  releaseMicrophone,
  unlockAudio,
  watchLevel,
} from "@/lib/voice";

/** A level an ordinary speaking voice clears; the meter is only a reassurance,
 *  so this is generous rather than precise. */
const HEARD_LEVEL = 0.02;

type MicState = "asking" | "on" | "heard" | "blocked";
type SpeakerState = "idle" | "loading" | "playing" | "asked" | "ok" | "failed";

interface Props {
  sessionId: string;
  /** The questions are planned and the interview can begin. */
  ready: boolean;
  error: string | null;
  onBegin: () => void;
  onBack: () => void;
}

/** Between "Start interview" and question one (ADR 0028). Planning takes about
 *  twenty seconds; this spends them getting the room ready — microphone allowed
 *  and heard, Donna's voice heard — so nothing interrupts question one. The
 *  Begin click is also the user gesture the browser wants before audio plays. */
export function Preflight({ sessionId, ready, error, onBegin, onBack }: Props) {
  const [voice, setVoice] = useState(() => loadVoicePreference() && microphoneSupported());
  const [mic, setMic] = useState<MicState>("asking");
  const [level, setLevel] = useState(0);
  const [speaker, setSpeaker] = useState<SpeakerState>("idle");
  const stopMeter = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!voice) return;
    // Fetch her cut-in lines now, so "let's move on" is ready the first time it
    // is needed and is never queued behind the question that follows it.
    void interjection(sessionId, "time_up");
    void interjection(sessionId, "stalled");
    let live = true;
    // Asking now puts the browser's permission prompt here, not in question one.
    watchLevel((l) => {
      if (!live) return;
      setLevel(l);
      if (l >= HEARD_LEVEL) setMic("heard");
    })
      .then((stop) => {
        if (!live) return stop();
        stopMeter.current = stop;
        setMic((m) => (m === "asking" ? "on" : m));
      })
      .catch(() => live && setMic("blocked"));
    return () => {
      live = false;
      stopMeter.current?.();
      stopMeter.current = null;
    };
  }, [voice, sessionId]);

  async function playDonna() {
    unlockAudio(); // this click is what lets the page play sound
    setSpeaker("loading");
    const player = donnaVoice();
    try {
      await player.enable();
    } catch {
      setSpeaker("failed");
      return;
    }
    const clip = await interjection(sessionId, "hello");
    if (!clip) {
      setSpeaker("failed");
      return;
    }
    player.stop();
    player.onFinished = () => setSpeaker("asked");
    player.play(clip);
    player.markComplete();
    setSpeaker("playing");
  }

  function typeInstead() {
    saveVoicePreference(false);
    releaseMicrophone();
    setVoice(false);
  }

  const checksDone = !voice || ((mic === "on" || mic === "heard") && (speaker === "ok" || speaker === "failed"));

  return (
    <div className="setup-workspace mx-auto flex w-full max-w-2xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="eyebrow">Before Donna walks in</p>
        <h1 className="text-2xl font-semibold tracking-tight">Let&rsquo;s get the room ready.</h1>
        <p className="text-sm text-muted-foreground">
          {voice
            ? "This is a spoken interview. Check you can hear Donna and she can hear you while she reads your resume and plans the questions."
            : "You'll answer by typing. Donna is reading your resume and planning the questions."}
        </p>
      </header>

      <ol className="preflight-steps">
        {voice && (
          <li data-state={mic === "blocked" ? "failed" : mic === "asking" ? "working" : "done"}>
            <StepIcon state={mic === "blocked" ? "failed" : mic === "asking" ? "working" : "done"} icon={<Mic />} />
            <div>
              <strong>Microphone</strong>
              {mic === "asking" && <span>Allow the microphone when your browser asks.</span>}
              {mic === "on" && <span>Allowed. Say a few words to check the level.</span>}
              {mic === "heard" && <span>Allowed, and Donna can hear you.</span>}
              {mic === "blocked" && (
                <span>
                  Blocked. Allow it in your browser&rsquo;s site settings and reload, or answer by
                  typing.
                </span>
              )}
              {(mic === "on" || mic === "heard") && (
                <span className="preflight-meter" aria-hidden>
                  <span style={{ width: `${Math.min(100, level * 1200)}%` }} />
                </span>
              )}
            </div>
          </li>
        )}

        {voice && (
          <li data-state={speaker === "ok" ? "done" : speaker === "failed" ? "failed" : "working"}>
            <StepIcon
              state={speaker === "ok" ? "done" : speaker === "failed" ? "failed" : "todo"}
              icon={<Volume2 />}
            />
            <div>
              <strong>Speaker</strong>
              {speaker === "idle" && <span>Turn your sound on, then play Donna.</span>}
              {speaker === "loading" && <span>Getting Donna&rsquo;s voice…</span>}
              {speaker === "playing" && <span>Listen…</span>}
              {speaker === "asked" && <span>Did you hear her?</span>}
              {speaker === "ok" && <span>You can hear Donna.</span>}
              {speaker === "failed" && (
                <span>Donna&rsquo;s voice isn&rsquo;t available right now. Questions will show as text.</span>
              )}
              <span className="preflight-actions">
                {(speaker === "idle" || speaker === "asked") && (
                  <Button type="button" variant="outline" className="h-9" onClick={() => void playDonna()}>
                    {speaker === "idle" ? "Play Donna" : "Play again"}
                  </Button>
                )}
                {speaker === "asked" && (
                  <Button type="button" className="h-9" onClick={() => setSpeaker("ok")}>
                    Yes, I heard her
                  </Button>
                )}
              </span>
            </div>
          </li>
        )}

        <li data-state={ready ? "done" : error ? "failed" : "working"}>
          <StepIcon state={ready ? "done" : error ? "failed" : "working"} icon={<ScrollText />} />
          <div>
            <strong>Questions</strong>
            <span>
              {ready
                ? "Five questions, planned for you and this role."
                : error
                  ? error
                  : "Donna is reading your resume and the job, and planning five questions."}
            </span>
          </div>
        </li>
      </ol>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          size="lg"
          className="h-11 px-5 text-base"
          disabled={!ready || !checksDone}
          onClick={() => {
            unlockAudio(); // and this click covers question one
            stopMeter.current?.();
            onBegin();
          }}
        >
          {!ready && !error ? "Planning your questions…" : "Begin interview"}
        </Button>
        {voice && (
          <button
            type="button"
            className="text-xs text-muted-foreground underline underline-offset-4"
            onClick={typeInstead}
          >
            Answer by typing instead
          </button>
        )}
        <button
          type="button"
          className="ml-auto text-xs text-muted-foreground underline underline-offset-4"
          onClick={onBack}
        >
          Back to setup
        </button>
      </div>
    </div>
  );
}

function StepIcon({
  state,
  icon,
}: {
  state: "todo" | "working" | "done" | "failed";
  icon: React.ReactNode;
}) {
  return (
    <span className="preflight-icon" aria-hidden>
      {state === "done" ? (
        <Check />
      ) : state === "failed" ? (
        <X />
      ) : state === "working" ? (
        <Loader2 className="animate-spin motion-reduce:animate-none" />
      ) : (
        icon
      )}
    </span>
  );
}
