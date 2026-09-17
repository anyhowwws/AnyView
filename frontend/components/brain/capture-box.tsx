"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createDump, createDumpFromUpload, uploadResume } from "@/lib/api";
import { MAX_UPLOAD_BYTES, UPLOAD_TYPES, type Proposal } from "@/lib/types";

interface Props {
  onProposal: (p: Proposal) => void;
}

/** The persistent "dump something" box, pinned at the top of the Brain screen. */
export function CaptureBox({ onProposal }: Props) {
  const [text, setText] = useState("");
  const [stage, setStage] = useState<"idle" | "uploading" | "reading">("idle");
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = stage !== "idle";

  async function run(action: () => Promise<Proposal>) {
    setError(null);
    try {
      onProposal(await action());
      setText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setStage("idle");
    }
  }

  return (
    // Pinned at the top on wide screens (brief). On a phone a pinned box would
    // hold a quarter of the viewport, so it scrolls with the page there.
    <section className="-mx-4 border-b bg-background/95 px-4 py-4 backdrop-blur sm:sticky sm:top-0 sm:z-10 sm:-mx-6 sm:px-6">
      <form
        className="mx-auto flex w-full max-w-4xl flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length < 20 || busy) return;
          setStage("reading");
          void run(() => createDump(text));
        }}
      >
        <label className="text-sm font-medium" htmlFor="dump">
          Dump something
        </label>
        <Textarea
          id="dump"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="A project you shipped, a story from a hard week, a skill you picked up, a certification… Maya turns it into entries for you to review."
          rows={3}
          maxLength={20000}
          disabled={busy}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" className="h-11 px-5 text-base" disabled={busy || text.trim().length < 20}>
            {stage === "reading" ? "Maya is reading…" : "Add to brain"}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              if (!(f.type in UPLOAD_TYPES)) return setError("Upload a PDF or a Word (.docx) file.");
              if (f.size > MAX_UPLOAD_BYTES) return setError("That file is over 10 MB.");
              setStage("uploading");
              void run(async () => {
                const object = await uploadResume(f);
                setStage("reading");
                return createDumpFromUpload(object);
              });
            }}
          />
          <Button type="button" variant="outline" className="h-10" disabled={busy} onClick={() => fileInput.current?.click()}>
            {stage === "uploading" ? "Uploading…" : "Upload a resume"}
          </Button>
          <span className="text-xs text-muted-foreground">
            {busy ? "About 20 seconds." : "Nothing is saved until you confirm it in the queue."}
          </span>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
