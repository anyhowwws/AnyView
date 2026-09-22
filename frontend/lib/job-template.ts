// The target job, filled in by hand (ADR 0014). Twin of capture-templates.ts:
// the same "Formatted" idea the Digital Garden uses for a memory, applied to
// the posting. Company, role and seniority have their own inputs on the form
// because the backend needs them as fields; everything here folds into the one
// `job_description` string, which is exactly what an uploaded JD produces too.
import type { JobParse, Seniority } from "@/lib/types";

export interface JobField {
  key: keyof JobValues;
  label: string;
  placeholder: string;
  type?: "text" | "textarea";
  wide?: boolean;
}

export interface JobValues {
  team: string;
  responsibilities: string;
  must_haves: string;
  nice_to_haves: string;
}

export const EMPTY_JOB: JobValues = {
  team: "",
  responsibilities: "",
  must_haves: "",
  nice_to_haves: "",
};

export const JOB_FIELDS: JobField[] = [
  { key: "team", label: "Team or function", placeholder: "e.g. Platform Engineering" },
  {
    key: "responsibilities",
    label: "What the role owns",
    placeholder: "One per line — e.g. Own the platform roadmap",
    type: "textarea",
    wide: true,
  },
  {
    key: "must_haves",
    label: "Must-haves",
    placeholder: "One per line — the requirements they will screen on",
    type: "textarea",
  },
  {
    key: "nice_to_haves",
    label: "Nice-to-haves",
    placeholder: "One per line — preferred, desirable, a bonus",
    type: "textarea",
  },
];

const HEADINGS: Record<keyof JobValues, string> = {
  team: "Team",
  responsibilities: "Responsibilities",
  must_haves: "Must-haves",
  nice_to_haves: "Nice-to-haves",
};

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.replace(/^[-•*]\s*/, "").trim())
    .filter(Boolean);
}

/** The filled-in fields as the job description the prompt will carry. Reads as
 *  a posting, because that is what the model on the other end expects. */
export function formatJob(title: string, company: string, values: JobValues): string {
  const out: string[] = [];
  const header = [title.trim(), company.trim()].filter(Boolean).join(" — ");
  if (header) out.push(header);
  if (values.team.trim()) out.push(`${HEADINGS.team}: ${values.team.trim()}`);
  for (const key of ["responsibilities", "must_haves", "nice_to_haves"] as const) {
    const items = lines(values[key]);
    if (items.length) out.push(`${HEADINGS[key]}:\n${items.map((i) => `- ${i}`).join("\n")}`);
  }
  return out.join("\n\n");
}

/** True once there is enough here to be worth sending. Company, role and
 *  seniority are validated on the form itself, so this asks only whether the
 *  posting says anything about the work. */
export function jobIsDescribed(values: JobValues): boolean {
  return lines(values.responsibilities).length > 0 || lines(values.must_haves).length > 0;
}

/** An uploaded JD's parse, poured into the same fields the manual path fills.
 *  Nothing here is used until the user has looked at it. */
export function valuesFromParse(parsed: JobParse): JobValues {
  return {
    team: "",
    responsibilities: parsed.responsibilities.join("\n"),
    must_haves: parsed.must_haves.join("\n"),
    nice_to_haves: parsed.nice_to_haves.join("\n"),
  };
}

export function seniorityFromParse(parsed: JobParse): Seniority | null {
  return parsed.seniority;
}
