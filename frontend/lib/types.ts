// Mirrors backend/src/anyview/interview/models.py. The browser holds the
// Session between requests (Phase 0 is stateless server-side), so these are
// both the API contract and the app state.

export type Seniority = "junior" | "mid" | "senior" | "staff" | "principal";
export const SENIORITIES: { value: Seniority; label: string }[] = [
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "staff", label: "Staff" },
  { value: "principal", label: "Principal" },
];

export type Dimension =
  | "star_completeness"
  | "specificity"
  | "quantified_outcome"
  | "ownership_language";

export const DIMENSION_LABELS: Record<Dimension, string> = {
  star_completeness: "STAR completeness",
  specificity: "Specificity",
  quantified_outcome: "Quantified outcome",
  ownership_language: "Ownership language",
};

export type State =
  | "intake" | "plan" | "ask" | "answer" | "probe" | "next" | "wrap" | "score" | "report";

export interface Setup {
  resume: string;
  company: string;
  role: string;
  seniority: Seniority;
  job_description: string | null;
  resume_object: string | null;
}

/** What the browser sends to start: uploaded object name or pasted text, not both. */
export interface SetupInput {
  resume?: string;
  resume_object?: string;
  company: string;
  role: string;
  seniority: Seniority;
  job_description: string | null;
}

export const UPLOAD_TYPES: Record<string, string> = {
  "application/pdf": ".pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
};
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export interface Question {
  id: number;
  text: string;
  competency: string;
  rationale: string;
}

export interface Answer {
  question_id: number;
  text: string;
}

export interface Session {
  session_id: string;
  setup: Setup;
  state: State;
  questions: Question[];
  answers: Answer[];
  current: number;
}

export interface DimensionScore {
  dimension: Dimension;
  score: number; // 0–4
  evidence: string;
}

export interface IdealAnswer {
  answer: string;
  cited_resume_lines: string[];
  resume_has_material: boolean;
}

export interface QuestionReport {
  question: Question;
  answer: string;
  dimensions: DimensionScore[];
  summary: string;
  gaps: string[];
  ideal: IdealAnswer;
}

export interface Report {
  session_id: string;
  company: string;
  role: string;
  seniority: Seniority;
  items: QuestionReport[];
}
