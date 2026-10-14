"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, Keyboard, Mic, RotateCcw, Sparkles, Square, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  askDonna,
  transcribeQuestion,
  uploadAnswerAudio,
  type Citation,
  type DiscoverTurn,
} from "@/lib/api";
import { blocks, suggestions, type Inline } from "@/lib/discover-text";
import type { Brain } from "@/lib/types";
import {
  donnaVoice,
  listen,
  microphoneSupported,
  QUESTION,
  releaseMicrophone,
  type ListenHandle,
} from "@/lib/voice";

interface Message {
  role: "user" | "donna";
  text: string;
  citations?: Citation[];
  failed?: boolean;
}

interface Props {
  brain: Brain;
  /** Show one entry in the Entries view. */
  onOpen: (id: string) => void;
}

/** Typing is the default; speaking is chosen per visit, never remembered (ADR 0030). */
type Mode = "type" | "speak";
/** The microphone, while a question is being asked out loud. */
type Mic = "idle" | "listening" | "transcribing";

function newConversationId(): string {
  return crypto.randomUUID();
}

/** Ask Donna about your own garden (ADR 0017). Read-only: she answers from
 *  confirmed entries and cites them; adding things stays in the capture box.
 *  The conversation lives only in this component — nothing is saved. */
export function Discover({ brain, onOpen }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; question: string } | null>(null);
  const [mode, setMode] = useState<Mode>("type");
  // Read by `ask`, which can run from a recording that finished after a switch.
  const modeRef = useRef<Mode>("type");
  modeRef.current = mode;
  const [mic, setMic] = useState<Mic>("idle");
  const [level, setLevel] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const conversation = useRef(newConversationId());
  const controller = useRef<AbortController | null>(null);
  const listening = useRef<ListenHandle | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const titles = useMemo(() => entryTitles(brain), [brain]);
  const empty = titles.size === 0;
  const starters = useMemo(() => suggestions(brain), [brain]);

  // Leaving the garden ends everything: the stream, Donna mid-sentence, the mic.
  useEffect(
    () => () => {
      controller.current?.abort();
      quiet();
      listening.current?.cancel();
      releaseMicrophone();
    },
    [],
  );
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    // Failed turns are not part of the conversation Donna sees.
    const history: DiscoverTurn[] = messages
      .filter((m) => !m.failed && m.text)
      .map(({ role, text }) => ({ role, text }));
    setDraft("");
    setError(null);
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", text: q }, { role: "donna", text: "" }]);
    const abort = new AbortController();
    controller.current = abort;
    // In speak mode every answer is spoken, typed question or not. A new
    // question cuts off whatever Donna was still saying about the last one.
    const voice = modeRef.current === "speak" ? donnaVoice() : null;
    voice?.stop();
    if (voice) voice.onFinished = () => setSpeaking(false);
    try {
      const citations = await askDonna(
        conversation.current,
        q,
        history,
        (chunk) => setMessages((prev) => withLast(prev, (m) => ({ ...m, text: m.text + chunk }))),
        abort.signal,
        voice
          ? {
              onAudio: (b64) => {
                setSpeaking(true);
                voice.play(b64);
              },
              onVoiceOff: (message) => setVoiceNote(`${message} Donna's answer is on screen.`),
            }
          : undefined,
      );
      voice?.markComplete();
      setMessages((prev) => withLast(prev, (m) => ({ ...m, citations })));
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError({ message: err instanceof ApiError ? err.message : "Donna couldn't answer that.", question: q });
      // Keep the question on screen, drop Donna's partial reply, and mark the pair failed.
      setMessages((prev) => [...prev.slice(0, -2), { role: "user", text: q, failed: true }]);
    } finally {
      setBusy(false);
    }
  }

  /** Stop Donna mid-sentence. */
  function quiet() {
    const voice = donnaVoice();
    voice.onFinished = null;
    voice.stop();
    setSpeaking(false);
  }

  function chooseMode(next: Mode) {
    if (next === mode) return;
    setVoiceNote(null);
    if (next === "type") {
      quiet();
      listening.current?.cancel();
      listening.current = null;
      releaseMicrophone();
      setMic("idle");
      setMode("type");
      return;
    }
    if (!microphoneSupported()) {
      setVoiceNote("This browser can't record audio. Chrome, Edge, Safari and Firefox all can.");
      return;
    }
    // This click is the user gesture that lets the page play Donna at all.
    donnaVoice()
      .enable()
      .then(() => setMode("speak"))
      .catch(() => setVoiceNote("This browser is blocking audio playback on the page."));
  }

  /** Ask out loud: record until a pause, write it down, then ask it. */
  async function speakQuestion() {
    if (busy || mic !== "idle") return;
    quiet(); // she must not be talking into the microphone
    setVoiceNote(null);
    setLevel(0);
    setMic("listening");
    listening.current = await listen({
      limits: QUESTION,
      onLevel: setLevel,
      onError: (message) => {
        setMic("idle");
        setVoiceNote(message);
      },
      onEnd: async (recording) => {
        listening.current = null;
        if (!recording.heardSpeech) {
          setMic("idle");
          setVoiceNote("Donna didn't hear anything. Check your microphone, or type your question.");
          return;
        }
        setMic("transcribing");
        try {
          const object = await uploadAnswerAudio(recording.blob, recording.contentType);
          const text = await transcribeQuestion(conversation.current, object);
          setMic("idle");
          void ask(text);
        } catch (err) {
          setMic("idle");
          setVoiceNote(err instanceof ApiError ? err.message : "That recording didn't go through. Try again.");
        }
      },
    });
  }

  function reset() {
    controller.current?.abort();
    quiet();
    conversation.current = newConversationId();
    setMessages([]);
    setError(null);
    setBusy(false);
  }

  if (empty) {
    return (
      <section className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Donna can only talk about what your Digital Garden holds, and it&apos;s empty. Capture a role, a project or a story above, confirm it, then ask her about it here.
      </section>
    );
  }

  return (
    <section className="workspace-panel discover-panel" aria-labelledby="discover-heading">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id="discover-heading" className="text-lg font-semibold">Ask Donna about your garden</h2>
          <p className="mt-1 text-sm text-muted-foreground">She answers from confirmed entries only, and tells you when something isn&apos;t there.</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div className="answer-mode" role="radiogroup" aria-label="How do you want to ask?">
            <button type="button" role="radio" aria-checked={mode === "type"} onClick={() => chooseMode("type")}>
              <Keyboard className="size-3.5" aria-hidden />
              Type
            </button>
            <button type="button" role="radio" aria-checked={mode === "speak"} onClick={() => chooseMode("speak")}>
              <Mic className="size-3.5" aria-hidden />
              Speak
            </button>
          </div>
          {messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={reset}><RotateCcw size={15} aria-hidden />New conversation</Button>
          )}
        </div>
      </header>

      <div className="discover-log" role="log" aria-live="polite" aria-busy={busy}>
        {messages.length === 0 && (
          <div className="discover-starters">
            <p className="text-sm text-muted-foreground"><Sparkles size={15} aria-hidden className="inline align-[-2px]" /> Try asking</p>
            <div className="flex flex-wrap gap-2">
              {starters.map((s) => <button key={s} type="button" className="discover-starter" onClick={() => void ask(s)}>{s}</button>)}
            </div>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="discover-question" data-failed={m.failed || undefined}>{m.text}</p>
          ) : (
            <DonnaAnswer key={i} message={m} titles={titles} onOpen={onOpen} pending={busy && i === messages.length - 1} />
          ),
        )}
        <div ref={bottom} />
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <p>{error.message}</p>
          <Button variant="outline" size="sm" onClick={() => { setMessages((prev) => prev.slice(0, -1)); void ask(error.question); }}>Try again</Button>
        </div>
      )}

      {voiceNote && <p className="text-sm text-muted-foreground" role="status">{voiceNote}</p>}

      {mode === "speak" && speaking && (
        <div className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
          <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
          Donna is speaking
          <Button variant="ghost" size="sm" onClick={quiet}><VolumeX size={15} aria-hidden />Stop</Button>
        </div>
      )}

      {mic === "listening" ? (
        <QuestionListening level={level} onDone={() => listening.current?.stop()} onCancel={() => {
          listening.current?.cancel();
          listening.current = null;
          setMic("idle");
        }} />
      ) : mic === "transcribing" ? (
        <div className="flex items-center gap-3 text-sm text-muted-foreground" role="status">
          <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
          Writing down your question…
        </div>
      ) : (
      <form className="discover-compose" onSubmit={(e) => { e.preventDefault(); void ask(draft); }}>
        <label htmlFor="discover-question" className="sr-only">Ask Donna</label>
        <Textarea
          id="discover-question"
          value={draft}
          maxLength={2000}
          rows={2}
          placeholder={mode === "speak" ? "Press the microphone and ask, or type here" : "Which projects have I done with AWS Bedrock?"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter is a new line.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void ask(draft);
            }
          }}
        />
        {mode === "speak" && (
          <Button type="button" size="icon" variant="outline" className="discover-mic" disabled={busy} aria-label="Ask out loud" onClick={() => void speakQuestion()}>
            <Mic size={18} aria-hidden />
          </Button>
        )}
        <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Ask">
          <ArrowUp size={18} aria-hidden />
        </Button>
      </form>
      )}
    </section>
  );
}

/** The open microphone while a question is asked out loud. It closes itself
 *  after a pause; "Done" is for anyone who would rather not wait for it. */
function QuestionListening({ level, onDone, onCancel }: {
  level: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  // Scaled generously, as in the interview: an ordinary voice should move it.
  const loudness = Math.min(1, level * 12);
  return (
    <div className="flex flex-wrap items-center gap-4">
      <span className="relative inline-flex size-11 items-center justify-center">
        <motion.span
          className="absolute inset-0 rounded-full bg-primary/20"
          animate={{ scale: 1 + loudness * 0.6, opacity: 0.35 + loudness * 0.5 }}
          transition={{ type: "spring", stiffness: 300, damping: 20 }}
          aria-hidden
        />
        <span className="relative inline-flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Mic className="size-4" aria-hidden />
        </span>
      </span>
      <p className="flex-1 text-sm" role="status">Listening — ask Donna out loud. A pause sends it.</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onDone}><Square className="size-3.5" aria-hidden />Done</Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

function DonnaAnswer({ message, titles, onOpen, pending }: {
  message: Message;
  titles: Map<string, string>;
  onOpen: (id: string) => void;
  pending: boolean;
}) {
  const citations = message.citations ?? [];
  const byLabel = new Map(citations.map((c) => [c.label, c]));
  const known = new Set(byLabel.keys());

  const render = (pieces: Inline[]) =>
    pieces.map((piece, j) => {
      if (piece.t === "text") return <span key={j}>{piece.text}</span>;
      if (piece.t === "bold") return <strong key={j}>{piece.text}</strong>;
      const c = byLabel.get(piece.label)!;
      return (
        <button key={j} type="button" className="discover-cite" title={titles.get(c.id)} onClick={() => onOpen(c.id)}>
          {piece.label}
        </button>
      );
    });

  if (!message.text && pending) {
    return <p className="discover-answer text-muted-foreground" role="status">Donna is looking through your garden…</p>;
  }
  return (
    <div className="discover-answer">
      {blocks(message.text, known).map((b, i) => {
        if (b.type === "p") return <p key={i}>{render(b.inline)}</p>;
        const List = b.type;
        return <List key={i}>{b.items.map((item, j) => <li key={j}>{render(item)}</li>)}</List>;
      })}
      {citations.length > 0 && (
        <ul className="discover-sources" aria-label="Entries this answer cites">
          {citations.map((c) => (
            <li key={c.id}>
              <button type="button" onClick={() => onOpen(c.id)}>
                <span className="tabular-nums text-muted-foreground">{c.label}</span> {titles.get(c.id) ?? "Entry"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function withLast(list: Message[], change: (m: Message) => Message): Message[] {
  return [...list.slice(0, -1), change(list[list.length - 1])];
}

/** id → a short human title, for citation chips and their tooltips. */
function entryTitles(brain: Brain): Map<string, string> {
  const pairs: [string, string][] = [
    ...brain.roles.map((r): [string, string] => [r.id, `${r.title} · ${r.company}`]),
    ...brain.projects.map((p): [string, string] => [p.id, p.name]),
    ...brain.stories.map((s): [string, string] => [s.id, s.title]),
    ...brain.skills.map((k): [string, string] => [k.id, k.name]),
    ...brain.achievements.map((a): [string, string] => [a.id, a.title]),
    ...(brain.education ?? []).map((e): [string, string] => [e.id, e.institution]),
    ...(brain.languages ?? []).map((l): [string, string] => [l.id, l.name]),
    ...(brain.feedback ?? []).map((f): [string, string] => [f.id, `Feedback from ${f.given_by}`]),
  ];
  return new Map(pairs);
}
