export type CaptureTemplate =
  | "thought"
  | "role"
  | "project"
  | "story"
  | "skill"
  | "certification"
  | "education"
  | "language"
  | "feedback";

export interface CaptureField {
  key: string;
  label: string;
  placeholder: string;
  type?: "text" | "date" | "textarea" | "select";
  options?: string[];
  required?: boolean;
  wide?: boolean;
}

export const CAPTURE_TEMPLATES: Record<
  CaptureTemplate,
  { label: string; description: string; fields: CaptureField[] }
> = {
  thought: { label: "Freeform thought", description: "Write naturally. Donna will identify the useful entries.", fields: [] },
  role: {
    label: "Role",
    description: "Record where you worked and the position you held.",
    fields: [
      { key: "company", label: "Company", placeholder: "e.g. Lenovo PCCW Solutions", required: true },
      { key: "title", label: "Job title", placeholder: "e.g. Multi-Cloud Solutions Architect", required: true },
      { key: "level", label: "Level", placeholder: "e.g. Senior" },
      { key: "start_date", label: "Start date", placeholder: "", type: "date" },
      { key: "end_date", label: "End date", placeholder: "Leave blank if current", type: "date" },
    ],
  },
  project: {
    label: "Project",
    description: "Capture the problem, your contribution, and the outcome.",
    fields: [
      { key: "name", label: "Project name", placeholder: "e.g. Multi-cloud landing zone", required: true, wide: true },
      { key: "problem", label: "Problem", placeholder: "What needed to change?", type: "textarea" },
      { key: "action", label: "What you did", placeholder: "Your specific contribution", type: "textarea" },
      { key: "result", label: "Result", placeholder: "What improved?", type: "textarea", wide: true },
      { key: "tech", label: "Technologies", placeholder: "e.g. GCP, Terraform, Cloud Run" },
      { key: "metrics", label: "Metrics", placeholder: "e.g. 38% lower monthly cost" },
    ],
  },
  story: {
    label: "Story",
    description: "Shape an interview-ready example using the STAR structure.",
    fields: [
      { key: "title", label: "Story title", placeholder: "A short name you will recognise", required: true, wide: true },
      { key: "situation", label: "Situation", placeholder: "What was happening?", type: "textarea" },
      { key: "task", label: "Task", placeholder: "What were you responsible for?", type: "textarea" },
      { key: "action", label: "Action", placeholder: "What did you do?", type: "textarea" },
      { key: "result", label: "Result", placeholder: "What changed because of it?", type: "textarea" },
    ],
  },
  skill: {
    label: "Skill",
    description: "Add a capability and how deeply you have used it.",
    fields: [
      { key: "name", label: "Skill", placeholder: "e.g. Terraform", required: true },
      { key: "depth", label: "Depth", placeholder: "", type: "select", options: ["1 — Familiar", "2 — Used", "3 — Regular use", "4 — Led with it", "5 — Expert / taught"] },
      { key: "projects", label: "Supporting projects", placeholder: "Where have you applied it?", wide: true },
    ],
  },
  certification: {
    label: "Certification",
    description: "Keep the credential, issuing body, and date together.",
    fields: [
      { key: "title", label: "Certification title", placeholder: "e.g. Professional Cloud Architect", required: true, wide: true },
      { key: "issuer", label: "Issuer", placeholder: "e.g. Google Cloud" },
      { key: "achieved_on", label: "Date earned", placeholder: "", type: "date" },
    ],
  },
  education: {
    label: "Education",
    description: "Record formal education and the field you studied.",
    fields: [
      { key: "institution", label: "Institution", placeholder: "e.g. National University of Singapore", required: true, wide: true },
      { key: "qualification", label: "Qualification", placeholder: "e.g. Bachelor of Computing" },
      { key: "field", label: "Field of study", placeholder: "e.g. Information Systems" },
      { key: "start_date", label: "Start date", placeholder: "", type: "date" },
      { key: "end_date", label: "End date", placeholder: "", type: "date" },
    ],
  },
  language: {
    label: "Language",
    description: "Add a language and your working proficiency.",
    fields: [
      { key: "name", label: "Language", placeholder: "e.g. English", required: true },
      { key: "proficiency", label: "Proficiency", placeholder: "", type: "select", options: ["Basic", "Conversational", "Professional", "Fluent", "Native"] },
    ],
  },
  feedback: {
    label: "Feedback",
    description: "Capture what someone said about your work, in their words.",
    fields: [
      { key: "given_by", label: "Who said it", placeholder: "e.g. Manager, 2024 performance review", required: true, wide: true },
      { key: "content", label: "What they said", placeholder: "Quote it as closely as you can remember", type: "textarea", required: true, wide: true },
      { key: "received_on", label: "When", placeholder: "", type: "date" },
    ],
  },
};

export function formatCapture(template: CaptureTemplate, values: Record<string, string>, notes: string): string {
  if (template === "thought") return notes.trim();
  const definition = CAPTURE_TEMPLATES[template];
  const lines = definition.fields
    .map((field) => [field.label, values[field.key]?.trim()] as const)
    .filter(([, value]) => value)
    .map(([label, value]) => `${label}: ${value}`);
  if (notes.trim()) lines.push(`Additional context: ${notes.trim()}`);
  return `${definition.label} entry:\n${lines.join("\n")}`;
}

export function formattedCaptureIsValid(template: CaptureTemplate, values: Record<string, string>): boolean {
  return CAPTURE_TEMPLATES[template].fields
    .filter((field) => field.required)
    .every((field) => Boolean(values[field.key]?.trim()));
}
