"use client";

import { useState } from "react";
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
import { SENIORITIES, type Seniority, type Setup } from "@/lib/types";

interface Props {
  onStart: (setup: Setup) => Promise<void>;
  error: string | null;
  busy: boolean;
}

export function SetupForm({ onStart, error, busy }: Props) {
  const [resume, setResume] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [seniority, setSeniority] = useState<Seniority | null>(null);
  const [jd, setJd] = useState("");

  const canSubmit = resume.trim().length >= 50 && company.trim() && role.trim() && seniority;

  return (
    <form
      className="mx-auto flex w-full max-w-2xl flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (!seniority) return;
        void onStart({
          resume,
          company: company.trim(),
          role: role.trim(),
          seniority,
          job_description: jd.trim() || null,
        });
      }}
    >
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Practice an interview</h1>
        <p className="text-sm text-muted-foreground">
          Paste your resume, name the target, and Maya will ask five questions tailored to you.
        </p>
      </header>

      <Field label="Resume" hint={`${resume.length.toLocaleString()} / 15,000`}>
        <Textarea
          value={resume}
          onChange={(e) => setResume(e.target.value)}
          placeholder="Paste your resume as plain text…"
          rows={10}
          maxLength={15000}
          required
        />
      </Field>

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

      <Button type="submit" size="lg" disabled={!canSubmit || busy} className="self-start">
        {busy ? "Planning your questions…" : "Start interview"}
      </Button>
    </form>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between text-sm font-medium">
        {label}
        {hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  );
}
