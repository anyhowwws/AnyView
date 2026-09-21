"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createDump, createDumpFromUpload, uploadResume } from "@/lib/api";
import { MAX_UPLOAD_BYTES, UPLOAD_TYPES, type Proposal } from "@/lib/types";

interface Props {
  onProposal: (p: Proposal) => void;
}

/** Capture stays above the map so a new memory is always one scroll away. */
export function CaptureBox({ onProposal }: Props) {
  const [text, setText] = useState("");
  const [template, setTemplate] = useState("thought");
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
    <section className="capture-panel">
      <form
        className="flex w-full flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length < 20 || busy) return;
          setStage("reading");
          void run(() => createDump(template === "thought" ? text : `${template} entry:\n${text}`));
        }}
      >
        <label className="text-sm font-medium" htmlFor="dump">
          What’s worth remembering?
        </label>
        <div className="capture-template-row">
          <label htmlFor="entry-template">Capture as</label>
          <select id="entry-template" value={template} onChange={(e) => setTemplate(e.target.value)} disabled={busy}>
            <option value="thought">Freeform thought</option>
            <option value="role">Role</option>
            <option value="project">Project</option>
            <option value="story">Story</option>
            <option value="skill">Skill</option>
            <option value="certification">Certification</option>
            <option value="education">Education</option>
            <option value="language">Language</option>
          </select>
        </div>
        <Textarea
          id="dump"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Write a raw thought, a project you shipped, a role, a skill, or a certification. Donna turns it into garden entries for you to review."
          rows={3}
          maxLength={20000}
          disabled={busy}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" className="h-11 px-5 text-base" disabled={busy || text.trim().length < 20}>
            {stage === "reading" ? "Donna is reading…" : "Grow the garden"}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.png,.jpg,.jpeg,.webp"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              if (!(f.type in UPLOAD_TYPES)) return setError("Upload a PDF, Word (.docx), PNG, JPG, or WebP file.");
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
            {stage === "uploading" ? "Uploading…" : "Upload resume or diagram"}
          </Button>
          <span className="text-xs text-muted-foreground">
            {busy ? "About 20 seconds." : "Donna drafts. You review. Only confirmed entries enter your Digital Garden."}
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
