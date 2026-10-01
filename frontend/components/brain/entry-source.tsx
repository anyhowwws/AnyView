"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { ChevronRight, FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, getDump } from "@/lib/api";
import { findQuote, originLine } from "@/lib/provenance";
import type { Provenance } from "@/lib/types";

/** Where an entry came from (ADR 0023): a quiet line that opens to the quote
 *  that justified it, and from there the whole document, scrolled to that
 *  quote. An entry added by hand is its own source, so it gets the line only. */
export function EntrySource({ source }: { source: Provenance }) {
  const [open, setOpen] = useState(false);
  if (source.origin === "manual") {
    return <p className="mt-2 text-xs text-muted-foreground">{originLine(source)}</p>;
  }
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex min-h-6 items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={`size-3.5 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden />
        {originLine(source)}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 pl-4.5">
          {source.evidence ? (
            <blockquote className="border-l-2 border-primary/60 pl-2 text-xs leading-relaxed text-foreground/85">
              “{source.evidence}”
            </blockquote>
          ) : (
            <p className="text-xs text-muted-foreground">No quote was kept for this entry; it predates quotes being saved.</p>
          )}
          <SourceDocument source={source} />
        </div>
      )}
    </div>
  );
}

/** The whole document in a side panel, fetched when opened, with the quote
 *  highlighted and scrolled into view. */
function SourceDocument({ source }: { source: Provenance }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open || text !== null) return;
    getDump(source.raw_dump_id)
      .then((d) => setText(d.text))
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load the document."));
  }, [open, text, source.raw_dump_id]);

  useEffect(() => {
    if (open && text !== null) mark.current?.scrollIntoView({ block: "center" });
  }, [open, text]);

  const at = text !== null ? findQuote(text, source.evidence) : null;

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className="inline-flex min-h-6 items-center gap-1 text-xs font-medium text-primary hover:underline underline-offset-4">
        <FileText className="size-3.5" aria-hidden />
        Open document
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l bg-card text-card-foreground shadow-2xl outline-none">
          <div className="flex items-start justify-between gap-3 border-b p-4">
            <div>
              <Dialog.Title className="text-sm font-semibold">Source document</Dialog.Title>
              <Dialog.Description className="text-xs text-muted-foreground">
                {originLine(source)}{at ? " · the highlighted part is where this entry came from" : ""}
              </Dialog.Description>
            </div>
            <Dialog.Close render={<Button variant="ghost" size="icon" className="size-9" aria-label="Close" />}>
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-auto p-4">
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            {text === null && !error && <p className="text-sm text-muted-foreground">Loading…</p>}
            {text !== null && (
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                {at ? (
                  <>
                    {text.slice(0, at[0])}
                    <mark ref={mark} className="rounded bg-primary/25 px-0.5 text-foreground">{text.slice(at[0], at[1])}</mark>
                    {text.slice(at[1])}
                  </>
                ) : (
                  text
                )}
              </pre>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
