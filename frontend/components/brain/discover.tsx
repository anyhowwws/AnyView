"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, askDonna, type Citation, type DiscoverTurn } from "@/lib/api";
import { blocks, suggestions, type Inline } from "@/lib/discover-text";
import type { Brain } from "@/lib/types";

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
  const conversation = useRef(newConversationId());
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const titles = useMemo(() => entryTitles(brain), [brain]);
  const empty = titles.size === 0;
  const starters = useMemo(() => suggestions(brain), [brain]);

  useEffect(() => () => controller.current?.abort(), []);
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
    try {
      const citations = await askDonna(
        conversation.current,
        q,
        history,
        (chunk) => setMessages((prev) => withLast(prev, (m) => ({ ...m, text: m.text + chunk }))),
        abort.signal,
      );
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

  function reset() {
    controller.current?.abort();
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
        {messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={reset}><RotateCcw size={15} aria-hidden />New conversation</Button>
        )}
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

      <form className="discover-compose" onSubmit={(e) => { e.preventDefault(); void ask(draft); }}>
        <label htmlFor="discover-question" className="sr-only">Ask Donna</label>
        <Textarea
          id="discover-question"
          value={draft}
          maxLength={2000}
          rows={2}
          placeholder="Which projects have I done with AWS Bedrock?"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter is a new line.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void ask(draft);
            }
          }}
        />
        <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Ask">
          <ArrowUp size={18} aria-hidden />
        </Button>
      </form>
    </section>
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
