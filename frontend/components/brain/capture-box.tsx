"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, createDump, createDumpFromUpload, uploadResume } from "@/lib/api";
import {
  CAPTURE_TEMPLATES,
  formatCapture,
  formattedCaptureIsValid,
  type CaptureTemplate,
} from "@/lib/capture-templates";
import { MAX_UPLOAD_BYTES, UPLOAD_TYPES, type Proposal } from "@/lib/types";

interface Props {
  onProposal: (p: Proposal) => void;
}

/** Capture stays above the map so a new memory is always one scroll away. */
export function CaptureBox({ onProposal }: Props) {
  const [text, setText] = useState("");
  const [template, setTemplate] = useState<CaptureTemplate>("thought");
  const [formatted, setFormatted] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [stage, setStage] = useState<"idle" | "uploading" | "reading">("idle");
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = stage !== "idle";
  const definition = CAPTURE_TEMPLATES[template];
  const valid = formatted
    ? formattedCaptureIsValid(template, fields)
    : text.trim().length >= 20;

  async function run(action: () => Promise<Proposal>) {
    setError(null);
    try {
      onProposal(await action());
      setText("");
      setFields({});
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
          if (!valid || busy) return;
          setStage("reading");
          void run(() => createDump(formatted ? formatCapture(template, fields, text) : text));
        }}
      >
        <label className="text-sm font-medium" htmlFor="dump">
          What’s worth remembering?
        </label>
        <div className="capture-template-row">
          <label htmlFor="entry-template">Capture as</label>
          <select
            id="entry-template"
            value={template}
            onChange={(e) => {
              const next = e.target.value as CaptureTemplate;
              setTemplate(next);
              if (next === "thought") setFormatted(false);
            }}
            disabled={busy}
          >
            {(Object.entries(CAPTURE_TEMPLATES) as [CaptureTemplate, typeof definition][]).map(
              ([key, item]) => <option key={key} value={key}>{item.label}</option>,
            )}
          </select>
          <label className={`formatted-toggle ${template === "thought" ? "is-disabled" : ""}`}>
            <input
              type="checkbox"
              checked={formatted}
              disabled={busy || template === "thought"}
              onChange={(e) => setFormatted(e.target.checked)}
            />
            <span>Formatted</span>
          </label>
        </div>
        {formatted && (
          <fieldset className="formatted-capture">
            <legend>{definition.label} details</legend>
            <p>{definition.description}</p>
            <div className="formatted-capture-grid">
              {definition.fields.map((field) => (
                <label key={field.key} className={field.wide ? "sm:col-span-2" : ""}>
                  <span>{field.label}{field.required && <em>Required</em>}</span>
                  {field.type === "textarea" ? (
                    <Textarea
                      rows={2}
                      value={fields[field.key] ?? ""}
                      placeholder={field.placeholder}
                      disabled={busy}
                      onChange={(e) => setFields((current) => ({ ...current, [field.key]: e.target.value }))}
                    />
                  ) : field.type === "select" ? (
                    <select
                      value={fields[field.key] ?? ""}
                      disabled={busy}
                      onChange={(e) => setFields((current) => ({ ...current, [field.key]: e.target.value }))}
                    >
                      <option value="">Select…</option>
                      {field.options?.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                  ) : (
                    <Input
                      type={field.type ?? "text"}
                      value={fields[field.key] ?? ""}
                      placeholder={field.placeholder}
                      disabled={busy}
                      required={field.required}
                      onChange={(e) => setFields((current) => ({ ...current, [field.key]: e.target.value }))}
                    />
                  )}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <label className="capture-notes-label" htmlFor="dump">
          {formatted ? "Additional context (optional)" : "Your notes"}
        </label>
        <Textarea
          id="dump"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={formatted ? "Anything else Donna should know about this entry…" : "Write a raw thought, a project you shipped, a role, a skill, or a certification. Donna turns it into garden entries for you to review."}
          rows={3}
          maxLength={20000}
          disabled={busy}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" className="h-11 px-5 text-base" disabled={busy || !valid}>
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
