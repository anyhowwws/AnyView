// What each kind of garden entry asks for, and what makes an answer valid.
// One definition, used by the in-place editor (/brain) and the review queue,
// so a field reads the same way wherever it is filled in.
//
// Values travel as strings while a form is open (an empty string is "not
// set"); `toPayload` turns them back into what the API stores. Dates are
// month-precision in the UI because resumes are: "2017-08" is shown, and
// stored as "2017-08-01" unless the entry already had a day in that month.

import type { Brain, EntityKind } from "./types";

export type FieldControl =
  | "text"
  | "textarea"
  | "lines" // a list of strings, one per line
  | "month" // a month picker; stores YYYY-MM-DD
  | "depth" // skill depth, 1–5
  | "choice" // a fixed list, plus whatever value the entry already had
  | "links"; // several other entries, picked as toggles; one value per line

export interface FieldSpec {
  name: string;
  label: string;
  control: FieldControl;
  required?: boolean;
  max?: number; // characters, mirroring the backend's max_length
  hint?: string;
  placeholder?: string;
  wide?: boolean; // spans both columns
  options?: { value: string; label: string }[];
  /** For an end date: what an empty value means ("Present"). */
  emptyMeans?: string;
  /** A date that cannot be later than this month. */
  notFuture?: boolean;
  /** What an empty choice is called ("Not linked"). */
  emptyLabel?: string;
}

/** Start and end fields that must be in order. */
export const DATE_RANGES: [start: string, end: string][] = [["start_date", "end_date"]];

export const DEPTHS = [
  { value: "1", label: "Familiar", hint: "Read about it, tried it" },
  { value: "2", label: "Used", hint: "Used it on real work" },
  { value: "3", label: "Regular", hint: "Part of the day job" },
  { value: "4", label: "Led", hint: "Led work built on it" },
  { value: "5", label: "Expert", hint: "Taught it, set the standard" },
];

export const PROFICIENCIES = ["Basic", "Conversational", "Professional", "Fluent", "Native"].map((p) => ({ value: p, label: p }));

const STAR_HINT = "One or two sentences is enough.";

export const ENTRY_FIELDS: Record<EntityKind, FieldSpec[]> = {
  role: [
    { name: "company", label: "Company", control: "text", required: true, max: 200, placeholder: "e.g. Lenovo PCCW Solutions" },
    { name: "title", label: "Job title", control: "text", required: true, max: 200, placeholder: "e.g. Solutions Architect" },
    { name: "level", label: "Level", control: "text", max: 80, placeholder: "e.g. Senior", hint: "How senior the role was." },
    { name: "start_date", label: "Started", control: "month" },
    { name: "end_date", label: "Ended", control: "month", emptyMeans: "Present", hint: "Leave as Present if you still work here." },
    { name: "responsibilities", label: "Responsibilities", control: "lines", wide: true, hint: "Enter starts the next one. Ongoing work; bounded work with an outcome is a project." },
  ],
  project: [
    { name: "name", label: "Project name", control: "text", required: true, max: 200, wide: true },
    { name: "problem", label: "Problem", control: "textarea", placeholder: "What needed to change?" },
    { name: "action", label: "What you did", control: "textarea", placeholder: "Your own contribution" },
    { name: "result", label: "Result", control: "textarea", wide: true, placeholder: "What improved, ideally with a number" },
    { name: "tech", label: "Technologies", control: "lines", placeholder: "e.g. Terraform", hint: "Enter starts the next one." },
    { name: "metrics", label: "Metrics", control: "lines", placeholder: "e.g. 38% lower monthly cost", hint: "Enter starts the next one." },
  ],
  story: [
    { name: "title", label: "Story title", control: "text", required: true, max: 200, wide: true, hint: "A short name you will recognise." },
    { name: "situation", label: "Situation", control: "textarea", hint: STAR_HINT },
    { name: "task", label: "Task", control: "textarea", hint: STAR_HINT },
    { name: "action", label: "Action", control: "textarea", hint: STAR_HINT },
    { name: "result", label: "Result", control: "textarea", hint: STAR_HINT },
  ],
  skill: [
    { name: "name", label: "Skill", control: "text", required: true, max: 100 },
    { name: "depth", label: "Depth", control: "depth", required: true },
  ],
  achievement: [
    { name: "title", label: "Title", control: "text", required: true, max: 200, wide: true },
    {
      name: "kind", label: "Type", control: "choice", required: true,
      options: [{ value: "credential", label: "Certification" }, { value: "achievement", label: "Achievement" }],
    },
    { name: "issuer", label: "Issued by", control: "text", max: 200, placeholder: "e.g. Google Cloud" },
    { name: "achieved_on", label: "Date", control: "month", notFuture: true },
  ],
  education: [
    { name: "institution", label: "Institution", control: "text", required: true, max: 200, wide: true },
    { name: "qualification", label: "Qualification", control: "text", max: 200, placeholder: "e.g. B.Sc. (Hons)" },
    { name: "field", label: "Field of study", control: "text", max: 200, placeholder: "e.g. Statistics" },
    { name: "start_date", label: "Started", control: "month" },
    { name: "end_date", label: "Finished", control: "month", emptyMeans: "Ongoing", hint: "An expected date is fine." },
  ],
  language: [
    { name: "name", label: "Language", control: "text", required: true, max: 100 },
    { name: "proficiency", label: "Proficiency", control: "choice", options: PROFICIENCIES },
  ],
  feedback: [
    { name: "given_by", label: "Who said it", control: "text", required: true, max: 200, wide: true, placeholder: "e.g. Manager, 2024 performance review" },
    { name: "content", label: "What they said", control: "textarea", required: true, max: 2000, wide: true, hint: "As close to their words as you can." },
    { name: "received_on", label: "When", control: "month", notFuture: true },
  ],
};

// --- Months -----------------------------------------------------------------

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTHS = MONTH_NAMES;

/** "2017-08-01" or "2017-08" → "2017-08"; anything unreadable → "". */
export function monthOf(value: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})/.exec(value ?? "");
  return m && Number(m[2]) >= 1 && Number(m[2]) <= 12 ? `${m[1]}-${m[2]}` : "";
}

/** "2017-08" → "Aug 2017". */
export function monthLabel(value: string | null | undefined): string {
  const ym = monthOf(value);
  if (!ym) return "";
  return `${MONTH_NAMES[Number(ym.slice(5)) - 1]} ${ym.slice(0, 4)}`;
}

/** The stored date for a picked month: keep the old day if the month did not
 *  change (so opening and closing the picker never rewrites a real date). */
export function dateForMonth(ym: string, previous: string | null | undefined): string {
  if (!ym) return "";
  return monthOf(previous) === ym ? (previous as string) : `${ym}-01`;
}

/** This month as "YYYY-MM", in the viewer's time zone. */
export function thisMonth(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

// --- Values -----------------------------------------------------------------

/** An entity's (or draft's) field as form text. */
export function asFormValue(value: unknown): string {
  if (Array.isArray(value)) return value.join("\n");
  return value == null ? "" : String(value);
}

/** Form text back to what the API stores for that field. */
export function fromFormValue(spec: FieldSpec, text: string): unknown {
  if (spec.control === "lines" || spec.control === "links") return text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (spec.control === "depth") return Number(text);
  const trimmed = text.trim();
  return trimmed === "" ? null : trimmed;
}

/** Field name → message, for every field that would be refused or makes no
 *  sense. Empty when the form can be saved. */
export function validateEntry(specs: FieldSpec[], values: Record<string, string>, now = new Date()): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const spec of specs) {
    const value = (values[spec.name] ?? "").trim();
    if (spec.required && !value) errors[spec.name] = `${spec.label} is required.`;
    else if (spec.max && value.length > spec.max) errors[spec.name] = `Keep it under ${spec.max} characters (${value.length} now).`;
    else if (spec.control === "month" && value && !monthOf(value)) errors[spec.name] = "Pick a month.";
    else if (spec.notFuture && value && monthOf(value) > thisMonth(now)) errors[spec.name] = "This can't be in the future.";
    else if (spec.control === "depth" && value && !DEPTHS.some((d) => d.value === value)) errors[spec.name] = "Pick a depth from 1 to 5.";
  }
  for (const [start, end] of DATE_RANGES) {
    const from = monthOf(values[start]);
    const to = monthOf(values[end]);
    const names = new Set(specs.map((s) => s.name));
    if (!names.has(start) || !names.has(end) || errors[end]) continue;
    if (from && to && to < from) {
      errors[end] = `Must be on or after the start (${monthLabel(from)}).`;
    }
  }
  return errors;
}

// --- Links ------------------------------------------------------------------

/** The fields that place an entry among the others: a project's role, a
 *  story's role and project, a skill's projects, roles and certifications.
 *  Adding refers to entries by label ("R1"), as a draft does; editing sets
 *  ids, as the edit route stores them. */
export function linkSpecs(kind: EntityKind, brain: Pick<Brain, "roles" | "projects" | "achievements">, mode: "add" | "edit"): FieldSpec[] {
  const ref = (e: { id: string; label: string }) => (mode === "add" ? e.label : e.id);
  return linkFields(kind, {
    roles: brain.roles.map((r) => ({ value: ref(r), label: `${r.title} · ${r.company}` })),
    projects: brain.projects.map((p) => ({ value: ref(p), label: p.name })),
    certs: brain.achievements.map((a) => ({ value: ref(a), label: a.title })),
  }, mode);
}

type Options = NonNullable<FieldSpec["options"]>;

/** The link fields for a kind, given what can be linked to. The review queue
 *  calls this directly, offering the proposal's own new drafts by key ("r1")
 *  beside the garden's entries by label ("R2"), as a Patch refers to them. */
export function linkFields(
  kind: EntityKind,
  { roles, projects, certs }: { roles: Options; projects: Options; certs: Options },
  mode: "add" | "edit",
): FieldSpec[] {
  const one = (name: string, label: string, options: FieldSpec["options"], hint?: string): FieldSpec =>
    ({ name, label, control: "choice", options, emptyLabel: "Not linked", hint });
  const many = (name: string, label: string, options: FieldSpec["options"], hint: string): FieldSpec =>
    ({ name, label, control: "links", options, wide: true, hint });
  const n = (add: string, edit: string) => (mode === "add" ? add : edit);
  const specs: FieldSpec[] = [];
  if (kind === "project" || kind === "story" || kind === "feedback") {
    if (roles.length) specs.push(one(n("role", "role_id"), kind === "feedback" ? "About the role" : "Role", roles));
  }
  if (kind === "story" || kind === "feedback") {
    if (projects.length) specs.push(one(n("project", "project_id"), kind === "feedback" ? "About the project" : "Part of project", projects));
  }
  if (kind === "skill") {
    if (projects.length) specs.push(many(n("projects", "project_ids"), "Used in projects", projects, "Tap each project that used it."));
    if (roles.length) specs.push(many(n("roles", "role_ids"), "Used in roles", roles, "Tap each role where you used it."));
    if (certs.length) specs.push(many(n("achievements", "achievement_ids"), "Certified by", certs, "Certifications that attest to it."));
  }
  return specs;
}
