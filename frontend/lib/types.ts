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
  source: "resume" | "brain";
}

/** What the browser sends to start: uploaded object name or pasted text, not both. */
export interface SetupInput {
  resume?: string;
  resume_object?: string;
  use_brain?: boolean;
  add_to_brain?: boolean;
  company: string;
  role: string;
  seniority: Seniority;
  job_description: string | null;
}

export const UPLOAD_TYPES: Record<string, string> = {
  "application/pdf": ".pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
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
  source: "resume" | "brain";
  items: QuestionReport[];
}

// --- The Digital Garden (mirrors backend/src/anyview/brain/models.py) -------

export type EntityKind = "role" | "project" | "story" | "skill" | "achievement" | "education" | "language";

export interface Provenance {
  raw_dump_id: string;
  event_id: number;
}

export interface Role {
  id: string;
  label: string;
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  level: string | null;
  source: Provenance;
}

export interface Project {
  id: string;
  label: string;
  role_id: string | null;
  name: string;
  problem: string | null;
  action: string | null;
  result: string | null;
  tech: string[];
  metrics: string[];
  source: Provenance;
}

export interface Story {
  id: string;
  label: string;
  role_id: string | null;
  project_id: string | null;
  title: string;
  situation: string | null;
  task: string | null;
  action: string | null;
  result: string | null;
  competencies: string[];
  source: Provenance;
}

export interface Skill {
  id: string;
  label: string;
  name: string;
  depth: number;
  project_ids: string[];
  source: Provenance;
}

export interface Achievement {
  id: string;
  label: string;
  kind: "achievement" | "credential";
  title: string;
  issuer: string | null;
  achieved_on: string | null;
  source: Provenance;
}

export interface Education {
  id: string;
  label: string;
  institution: string;
  qualification: string | null;
  field: string | null;
  start_date: string | null;
  end_date: string | null;
  source: Provenance;
}

export interface Language {
  id: string;
  label: string;
  name: string;
  proficiency: string | null;
  source: Provenance;
}

export interface Competency {
  key: string;
  label: string;
}

export type Strength = "none" | "weak" | "strong";

export interface Coverage {
  competencies: Competency[];
  roles: Role[];
  cells: Record<string, Record<string, Strength>>;
}

export interface Brain {
  roles: Role[];
  projects: Project[];
  stories: Story[];
  skills: Skill[];
  achievements: Achievement[];
  education: Education[];
  languages: Language[];
  coverage: Coverage;
  pending_proposals: number;
}

// Drafts: what the model proposed, editable in the review queue.
interface Draft {
  key: string;
  existing: string | null;
  evidence: string;
}
export interface RoleDraft extends Draft {
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  level: string | null;
}
export interface ProjectDraft extends Draft {
  role: string | null;
  name: string;
  problem: string | null;
  action: string | null;
  result: string | null;
  tech: string[];
  metrics: string[];
}
export interface StoryDraft extends Draft {
  role: string | null;
  project: string | null;
  title: string;
  situation: string | null;
  task: string | null;
  action: string | null;
  result: string | null;
  competencies: string[];
}
export interface SkillDraft extends Draft {
  name: string;
  depth: number;
  projects: string[];
}
export interface AchievementDraft extends Draft {
  kind: "achievement" | "credential";
  title: string;
  issuer: string | null;
  achieved_on: string | null;
}
export interface EducationDraft extends Draft {
  institution: string;
  qualification: string | null;
  field: string | null;
  start_date: string | null;
  end_date: string | null;
}
export interface LanguageDraft extends Draft {
  name: string;
  proficiency: string | null;
}
export interface Patch {
  roles: RoleDraft[];
  projects: ProjectDraft[];
  stories: StoryDraft[];
  skills: SkillDraft[];
  achievements: AchievementDraft[];
  education: EducationDraft[];
  languages: LanguageDraft[];
}

export interface Proposal {
  id: string;
  raw_dump_id: string;
  status: "pending" | "confirmed" | "discarded";
  patch: Patch;
  model: string;
  created_at: string;
  resolved_at: string | null;
  dump_kind: "text" | "resume_pdf" | "resume_docx" | null;
}

export interface BrainEvent {
  id: number;
  seq: number;
  kind: "patch_confirmed" | "entity_edited" | "entity_retired";
  payload: Record<string, unknown>;
  raw_dump_id: string | null;
  proposal_id: string | null;
  created_at: string;
}

export interface RawDump {
  id: string;
  kind: "text" | "resume_pdf" | "resume_docx";
  text: string;
  object_name: string | null;
  created_at: string;
}
