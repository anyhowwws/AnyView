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
import { ApiError, getBrain, getDump, getResumeOnFile, parseJob, uploadResume } from "@/lib/api";
import {
  EMPTY_JOB,
  JOB_FIELDS,
  formatJob,
  valuesFromParse,
  type JobValues,
} from "@/lib/job-template";
import {
  DIFFICULTIES,
  PACES,
  MAX_UPLOAD_BYTES,
  SENIORITIES,
  type Difficulty,
  type JobParse,
  type ResumeOnFile,
  type Seniority,
  type SetupInput,
} from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  resume_pdf: "PDF",
  resume_docx: "Word document",
  text: "typed text",
};

interface Props {
  /** Receives the resume file (only when replacing) and the rest of the setup;
   *  the caller uploads then starts. */
  onStart: (file: File | null, setup: Omit<SetupInput, "resume_object">) => Promise<void>;
  error: string | null;
  busy: boolean;
  /** What the caller is doing right now, for the button label. */
  stage: "idle" | "uploading" | "starting";
}

function pickDocument(list: FileList | null): { file: File | null; error: string | null } {
  const f = list?.[0] ?? null;
  if (!f) return { file: null, error: null };
  if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".docx")) {
    return { file: null, error: "Upload a PDF or a Word (.docx) file." };
  }
  if (f.size > MAX_UPLOAD_BYTES) {
    return { file: null, error: "That file is over 10 MB. Please upload a smaller one." };
  }
  return { file: f, error: null };
}

export function SetupForm({ onStart, error, busy, stage }: Props) {
  // 01 · you
  const [onFile, setOnFile] = useState<ResumeOnFile | null>(null);
  const [checking, setChecking] = useState(true);
  const [replacing, setReplacing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [extracted, setExtracted] = useState<string | null>(null);

  // 02 · the job
  const [jobMode, setJobMode] = useState<"upload" | "manual">("upload");
  const [jobText, setJobText] = useState<string | null>(null);
  const [parsed, setParsed] = useState<JobParse | null>(null);
  const [jobValues, setJobValues] = useState<JobValues>(EMPTY_JOB);
  const [jobBusy, setJobBusy] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [seniority, setSeniority] = useState<Seniority | null>(null);

  // 03 · the room
  const [difficulty, setDifficulty] = useState<Difficulty>("hiring_manager");
  // A real interview has a schedule, so the clock starts on (ADR 0016).
  const [timeBounded, setTimeBounded] = useState(true);
  const [brainSize, setBrainSize] = useState<number | null>(null);

  const resumeInput = useRef<HTMLInputElement>(null);
  const jobInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getResumeOnFile()
      .then(setOnFile)
      .catch(() => setOnFile(null))
      .finally(() => setChecking(false));
    getBrain()
      .then((b) =>
        setBrainSize(
          b.roles.length + b.projects.length + b.stories.length + b.skills.length +
            b.achievements.length + b.education.length + b.languages.length + b.feedback.length,
        ),
      )
      .catch(() => setBrainSize(null));
  }, []);

  const hasResume = Boolean(onFile?.dump_id) || file !== null;
  const needsUpload = checking ? false : !onFile?.dump_id || replacing;
  const canSubmit = hasResume && company.trim() && role.trim() && seniority && !jobBusy;

  function chooseResume(list: FileList | null) {
    const { file: f, error: e } = pickDocument(list);
    setFile(f);
    setFileError(e);
  }

  async function showExtractedText() {
    if (!onFile?.dump_id) return;
    try {
      setExtracted((await getDump(onFile.dump_id)).text);
    } catch {
      setExtracted("Couldn't load the text we read from it.");
    }
  }

  /** Upload the posting, read it, and pour what it says into the fields. */
  async function readJob(list: FileList | null) {
    const { file: f, error: e } = pickDocument(list);
    setJobError(e);
    if (!f) return;
    setJobBusy(true);
    try {
      const document = await parseJob(await uploadResume(f));
      setJobText(document.text);
      setParsed(document.parsed);
      setJobValues(valuesFromParse(document.parsed));
      if (document.parsed.company) setCompany(document.parsed.company);
      if (document.parsed.role) setRole(document.parsed.role);
      if (document.parsed.seniority) setSeniority(document.parsed.seniority);
    } catch (err) {
      setJobError(err instanceof ApiError ? err.message : "Couldn't read that posting.");
    } finally {
      setJobBusy(false);
    }
  }

  function clearJob() {
    setJobText(null);
    setParsed(null);
    setJobValues(EMPTY_JOB);
    setJobError(null);
    if (jobInput.current) jobInput.current.value = "";
  }

  function jobDescription(): string | null {
    if (jobMode === "upload") return jobText;
    return formatJob(role, company, jobValues) || null;
  }

  return (
    <form
      className="setup-workspace mx-auto flex w-full max-w-3xl flex-col gap-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (!seniority || !canSubmit) return;
        void onStart(file, {
          company: company.trim(),
          role: role.trim(),
          seniority,
          difficulty,
          time_bounded: timeBounded,
          job_description: jobDescription(),
        });
      }}
    >
      <header className="page-heading">
        <div>
          <p className="eyebrow">Your next chapter starts here</p>
          <h1>
            Make your experience speak for itself<span className="text-primary">.</span>
          </h1>
          <p className="text-sm text-muted-foreground">
            Five questions, feedback grounded in your experience, and more confidence for the real thing.
          </p>
        </div>
      </header>
      <div className="practice-steps" aria-label="How practice works">
        <span><b>01</b> Your resume</span>
        <span><b>02</b> The job</span>
        <span><b>03</b> The room</span>
      </div>

      {/* --- 01 · the resume an interviewer would have received ------------- */}
      <section className="setup-section" aria-labelledby="step-resume">
        <h2 id="step-resume">
          <span>01</span> Your resume
        </h2>
        <p className="setup-note">
          This is the document an interviewer receives — it is all they know about you
          before you walk in. Everything else you have told Donna lives in your Digital
          Garden, and only the hardest room gets to read it.
        </p>

        {checking ? (
          <p className="text-sm text-muted-foreground" role="status">
            Checking for a resume on file…
          </p>
        ) : !needsUpload && onFile?.dump_id ? (
          <>
            <div className="on-file-card">
              <span className="on-file-tick" aria-hidden="true">✓</span>
              <div>
                <p className="on-file-title">Resume on file</p>
                <p className="on-file-detail">
                  {KIND_LABELS[onFile.kind ?? ""] ?? "Document"}
                  {onFile.uploaded_at &&
                    ` · added ${new Date(onFile.uploaded_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}`}
                  {onFile.characters > 0 && ` · ${onFile.characters.toLocaleString()} characters`}
                </p>
              </div>
              <div className="on-file-actions">
                <button type="button" onClick={() => void showExtractedText()}>
                  {extracted === null ? "View what Donna read" : "Reload"}
                </button>
                <button type="button" onClick={() => setReplacing(true)}>
                  Replace
                </button>
              </div>
            </div>
            {extracted !== null && (
              <pre className="extracted-text" tabIndex={0}>
                {extracted}
              </pre>
            )}
          </>
        ) : (
          <>
            <input
              ref={resumeInput}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="sr-only"
              onChange={(e) => chooseResume(e.target.files)}
            />
            <div
              className="upload-area flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-7"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                chooseResume(e.dataTransfer.files);
              }}
            >
              <Button
                type="button"
                variant="outline"
                className="h-10"
                onClick={() => resumeInput.current?.click()}
              >
                {file ? "Choose a different file" : "Choose file"}
              </Button>
              <span className="text-sm text-muted-foreground">
                {file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : "or drop it here — PDF or Word, up to 10 MB"}
              </span>
            </div>
            {fileError && (
              <p role="alert" className="text-xs text-destructive">
                {fileError}
              </p>
            )}
            <p className="setup-note">
              What&rsquo;s new in it goes to your Digital Garden&rsquo;s review queue. Nothing is
              saved there until you confirm it.
            </p>
            {onFile?.dump_id && (
              <button
                type="button"
                className="self-start text-xs text-muted-foreground underline underline-offset-4"
                onClick={() => {
                  setReplacing(false);
                  setFile(null);
                  setFileError(null);
                }}
              >
                Keep the one on file
              </button>
            )}
          </>
        )}
      </section>

      {/* --- 02 · the job -------------------------------------------------- */}
      <section className="setup-section" aria-labelledby="step-job">
        <h2 id="step-job">
          <span>02</span> The job
        </h2>

        <div className="mode-switch" role="group" aria-label="How to describe the job">
          {(
            [
              ["upload", "Upload the posting"],
              ["manual", "Fill it in"],
            ] as ["upload" | "manual", string][]
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={jobMode === value}
              onClick={() => setJobMode(value)}
              disabled={jobBusy}
            >
              {label}
            </button>
          ))}
        </div>

        {jobMode === "upload" ? (
          <>
            <input
              ref={jobInput}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="sr-only"
              onChange={(e) => void readJob(e.target.files)}
            />
            <div
              className="upload-area flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-7"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                void readJob(e.dataTransfer.files);
              }}
            >
              <Button
                type="button"
                variant="outline"
                className="h-10"
                disabled={jobBusy}
                onClick={() => jobInput.current?.click()}
              >
                {jobText ? "Choose a different posting" : "Choose file"}
              </Button>
              <span className="text-sm text-muted-foreground" aria-live="polite">
                {jobBusy
                  ? "Reading the posting…"
                  : jobText
                    ? `Read · ${jobText.length.toLocaleString()} characters`
                    : "or drop it here — PDF or Word, up to 10 MB"}
              </span>
              {jobText && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground underline underline-offset-4"
                  onClick={clearJob}
                >
                  Remove
                </button>
              )}
            </div>
            {jobError && (
              <p role="alert" className="text-xs text-destructive">
                {jobError}
              </p>
            )}
            {parsed && (
              <div className="parsed-receipt">
                <p>
                  Donna read this out of the posting. Correct anything below that isn&rsquo;t
                  right — the fields are yours, not hers.
                </p>
                <Chips label="Must-haves" items={parsed.must_haves} />
                <Chips label="Nice-to-haves" items={parsed.nice_to_haves} />
                <Chips label="The role owns" items={parsed.responsibilities} />
              </div>
            )}
          </>
        ) : (
          <fieldset className="formatted-capture">
            <legend>The posting, in your words</legend>
            <p>
              Only the company, role and seniority are required. The rest sharpens the
              questions, and at harder levels it is what Donna pushes on.
            </p>
            <div className="formatted-capture-grid">
              {JOB_FIELDS.map((field) => (
                <label key={field.key} className={field.wide ? "sm:col-span-2" : ""}>
                  <span>{field.label}</span>
                  {field.type === "textarea" ? (
                    <Textarea
                      rows={3}
                      value={jobValues[field.key]}
                      placeholder={field.placeholder}
                      onChange={(e) =>
                        setJobValues((v) => ({ ...v, [field.key]: e.target.value }))
                      }
                    />
                  ) : (
                    <Input
                      value={jobValues[field.key]}
                      placeholder={field.placeholder}
                      onChange={(e) =>
                        setJobValues((v) => ({ ...v, [field.key]: e.target.value }))
                      }
                    />
                  )}
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Company">
            <Input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              maxLength={120}
              required
            />
          </Field>
          <Field label="Role">
            <Input value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} required />
          </Field>
          <Field label="Seniority">
            <Select
              items={SENIORITIES}
              value={seniority}
              onValueChange={(v) => setSeniority(v as Seniority)}
            >
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
      </section>

      {/* --- 03 · the room ------------------------------------------------- */}
      <section className="setup-section" aria-labelledby="step-room">
        <h2 id="step-room">
          <span>03</span> The room
        </h2>
        <p className="setup-note">
          Difficulty is not a tone of voice. It is how much the interviewer already knows,
          and so how far past your resume they can push.
        </p>
        <div className="difficulty-grid" role="radiogroup" aria-label="How hard should this be?">
          {DIFFICULTIES.map((level) => (
            <button
              key={level.value}
              type="button"
              role="radio"
              aria-checked={difficulty === level.value}
              className="difficulty-option"
              onClick={() => setDifficulty(level.value)}
            >
              <strong>{level.label}</strong>
              <span>{level.blurb}</span>
              {level.value === "panel" && brainSize !== null && (
                <em>
                  {brainSize > 0
                    ? `${brainSize} ${brainSize === 1 ? "entry" : "entries"} in your Digital Garden`
                    : "Your Digital Garden is empty — they will push on the job description instead"}
                </em>
              )}
            </button>
          ))}
        </div>

        <p className="setup-note">
          And the clock. Each question carries its own limit — Donna decides how long a
          strong answer to that question needs when she plans the interview.
        </p>
        <div className="pace-grid" role="radiogroup" aria-label="Should the clock run?">
          {PACES.map((pace) => (
            <button
              key={String(pace.value)}
              type="button"
              role="radio"
              aria-checked={timeBounded === pace.value}
              className="difficulty-option"
              onClick={() => setTimeBounded(pace.value)}
            >
              <strong>{pace.label}</strong>
              <span>{pace.blurb}</span>
            </button>
          ))}
        </div>
      </section>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
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
            {hasResume ? "Needs a company, a role, and a seniority." : "Needs your resume."}
          </span>
        )}
      </div>
    </form>
  );
}

function Chips({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <p className="parsed-chips">
      <span>{label}</span>
      {items.map((item, i) => (
        <em key={i}>{item}</em>
      ))}
    </p>
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
