"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getBrain } from "@/lib/api";
import {
  MAX_UPLOAD_BYTES,
  SENIORITIES,
  UPLOAD_TYPES,
  type Seniority,
  type SetupInput,
} from "@/lib/types";

type Source = "upload" | "paste" | "brain";

interface Props {
  /** Receives the file (if any) and the rest of the setup; the caller uploads then starts. */
  onStart: (file: File | null, setup: Omit<SetupInput, "resume_object">) => Promise<void>;
  error: string | null;
  busy: boolean;
  /** What the caller is doing right now, for the button label. */
  stage: "idle" | "uploading" | "starting";
}

export function SetupForm({ onStart, error, busy, stage }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [source, setSource] = useState<Source>("upload");
  const [addToBrain, setAddToBrain] = useState(true);
  const [brainSize, setBrainSize] = useState<number | null>(null); // entities in the brain; null = unknown
  const [resume, setResume] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [seniority, setSeniority] = useState<Seniority | null>(null);
  const [jd, setJd] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const pasting = source === "paste";
  const resumeTooShort = pasting && resume.trim().length > 0 && resume.trim().length < 50;
  const hasResume =
    source === "brain" ? (brainSize ?? 0) > 0 : pasting ? resume.trim().length >= 50 : file !== null;
  const canSubmit = hasResume && company.trim() && role.trim() && seniority;

  useEffect(() => {
    // Is there a brain to interview from? One request; absence just hides the option.
    getBrain()
      .then((b) => setBrainSize(b.roles.length + b.projects.length + b.stories.length + b.skills.length))
      .catch(() => setBrainSize(null));
  }, []);

  function pick(list: FileList | null) {
    const f = list?.[0] ?? null;
    setFileError(null);
    if (!f) return setFile(null);
    if (!(f.type in UPLOAD_TYPES)) {
      setFile(null);
      return setFileError("Upload a PDF or a Word (.docx) file.");
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      return setFileError("That file is over 10 MB. Please upload a smaller one.");
    }
    setFile(f);
  }

  return (
    <form
      className="setup-workspace mx-auto flex w-full max-w-3xl flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (!seniority || !canSubmit) return;
        void onStart(source === "upload" ? file : null, {
          resume: pasting ? resume : undefined,
          use_brain: source === "brain" || undefined,
          add_to_brain: source === "upload" && addToBrain ? true : undefined,
          company: company.trim(),
          role: role.trim(),
          seniority,
          job_description: jd.trim() || null,
        });
      }}
    >
      <header className="page-heading">
        <div><p className="eyebrow">Your next chapter starts here</p>
        <h1>Make your experience<br />speak for itself<span className="text-primary">.</span></h1>
        <p className="text-sm text-muted-foreground">
          Five thoughtful questions. Feedback grounded in your experience.
          A little more confidence for the real conversation.
        </p>
        </div>
      </header>
      <div className="practice-steps" aria-label="How practice works"><span><b>01</b> Bring your experience</span><span><b>02</b> Practice with Maya</span><span><b>03</b> Find your next step</span></div>

      {brainSize !== null && brainSize > 0 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Where should Maya read about you?">
          {(
            [
              ["upload", "Upload a resume"],
              ["brain", `My brain (${brainSize} ${brainSize === 1 ? "entry" : "entries"})`],
              ["paste", "Paste text"],
            ] as [Source, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={source === value}
              onClick={() => setSource(value)}
              className={`min-h-11 rounded-lg border px-3 py-2 text-sm ${source === value ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {source === "brain" ? (
        <p className="rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          Maya will interview you from your confirmed brain and cite its entries ([R1], [S2]…) in
          the ideal answers.
        </p>
      ) : pasting ? (
        <Field
          label="Resume"
          hint={resumeTooShort ? "at least 50 characters" : `${resume.length.toLocaleString()} / 15,000`}
          hintTone={resumeTooShort ? "warn" : "muted"}
        >
          <Textarea
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste your resume as plain text…"
            rows={10}
            maxLength={15000}
          />
          <button
            type="button"
            className="self-start text-xs text-muted-foreground underline underline-offset-4"
            onClick={() => setSource("upload")}
          >
            Upload a file instead
          </button>
        </Field>
      ) : (
        <Field label="Resume" hint="PDF or Word, up to 10 MB">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            className="sr-only"
            onChange={(e) => pick(e.target.files)}
          />
          <div
            className="upload-area flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-7"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              pick(e.dataTransfer.files);
            }}
          >
            <Button type="button" variant="outline" className="h-10" onClick={() => fileInput.current?.click()}>
              {file ? "Choose a different file" : "Choose file"}
            </Button>
            <span className="text-sm text-muted-foreground">
              {file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : "or drop it here"}
            </span>
          </div>
          {fileError && (
            <p role="alert" className="text-xs text-destructive">
              {fileError}
            </p>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4"
              checked={addToBrain}
              onChange={(e) => setAddToBrain(e.target.checked)}
            />
            Also add this resume to my brain (you review before anything is saved)
          </label>
          <button
            type="button"
            className="self-start text-xs text-muted-foreground underline underline-offset-4"
            onClick={() => setSource("paste")}
          >
            Paste text instead
          </button>
        </Field>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Company">
          <Input value={company} onChange={(e) => setCompany(e.target.value)} maxLength={120} required />
        </Field>
        <Field label="Role">
          <Input value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} required />
        </Field>
        <Field label="Seniority">
          <Select items={SENIORITIES} value={seniority} onValueChange={(v) => setSeniority(v as Seniority)}>
            <SelectTrigger className="w-full" aria-label="Seniority">
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              {SENIORITIES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <Field label="Job description" hint="optional">
        <Textarea
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          placeholder="Paste the posting if you have it…"
          rows={5}
          maxLength={8000}
        />
      </Field>

      {error && (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={!canSubmit || busy} className="h-11 px-5 text-base">
          {stage === "uploading"
            ? "Uploading your resume…"
            : stage === "starting"
              ? "Reading it and planning your questions…"
              : "Start interview"}
        </Button>
        {!canSubmit && !busy && (
          <span className="text-xs text-muted-foreground">
            Needs a resume, a company, a role, and a seniority.
          </span>
        )}
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  hintTone = "muted",
  children,
}: {
  label: string;
  hint?: string;
  hintTone?: "muted" | "warn";
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between text-sm font-medium">
        {label}
        {hint && (
          <span
            className={`text-xs font-normal ${hintTone === "warn" ? "text-destructive" : "text-muted-foreground"}`}
            aria-live="polite"
          >
            {hint}
          </span>
        )}
      </span>
      {children}
    </label>
  );
}
