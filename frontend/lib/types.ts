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

/** How much the interviewer knows, and so how far past the resume they push
 *  (ADR 0014). Named for the room, because the room is what the level
 *  simulates. */
export type Difficulty = "recruiter_screen" | "hiring_manager" | "panel";
export const DIFFICULTIES: { value: Difficulty; label: string; blurb: string }[] = [
  {
    value: "recruiter_screen",
    label: "Recruiter screen",
    blurb: "Only what your resume can answer. Everything is on the page in front of them.",
  },
  {
    value: "hiring_manager",
    label: "Hiring manager",
    blurb: "Your resume and the job description. They will ask about what the role needs and your CV doesn't show.",
  },
  {
    value: "panel",
    label: "Panel",
    blurb: "They have done their homework — your Digital Garden too. Expect the questions your resume alone could not have prompted.",
  },
];

/** Whether the clock runs (ADR 0016). Two options, so a boolean rather than a
 *  named type — but the copy belongs beside the difficulty copy. */
export const PACES: { value: boolean; label: string; blurb: string }[] = [
  {
    value: true,
    label: "Interview pace",
    blurb:
      "Every question has a time limit. Harvey moves on when it runs out, mid-sentence if need be — the way an interviewer working to a schedule does.",
  },
  {
    value: false,
    label: "Take your time",
    blurb:
      "No clock. Think, restart, and finish the answer whenever you're ready. Better for a first run at a hard question.",
  },
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
  difficulty: Difficulty;
  /** Whether the clock runs on each answer (ADR 0016). */
  time_bounded: boolean;
  job_description: string | null;
  resume_object: string | null;
  /** The confirmed garden, present only when the interviewer is allowed it. */
  garden: string | null;
}

/** What the browser sends to start (ADR 0014). Send no resume at all and the
 *  one on file is used; `resume_object` replaces it. */
export interface SetupInput {
  resume_object?: string;
  company: string;
  role: string;
  seniority: Seniority;
  difficulty: Difficulty;
  time_bounded: boolean;
  job_description: string | null;
  /** How the job was described, so it is saved for next time (ADR 0025). */
  job?: JobInput;
}

/** The form's structured job fields, one item per line (see job-template.ts). */
export interface JobFields {
  team: string;
  responsibilities: string;
  must_haves: string;
  nice_to_haves: string;
}

export type JobSource = "upload" | "manual";

/** `id` set: a saved job was picked, and edits write back to it. */
export interface JobInput {
  id: string | null;
  source: JobSource;
  fields: JobFields;
}

/** A target job kept for the next practice run (ADR 0025). */
export interface SavedJob {
  id: string;
  company: string;
  role: string;
  seniority: Seniority;
  source: JobSource;
  job_description: string | null;
  fields: JobFields;
  created_at: string;
  last_used_at: string;
}

/** The resume an interviewer would have received, as the setup form shows it.
 *  `dump_id === null` means there is nothing on file yet. */
export interface ResumeOnFile {
  dump_id: string | null;
  kind: string | null;
  uploaded_at: string | null;
  characters: number;
}

/** What Harvey read out of an uploaded job description. Every field is a
 *  suggestion that pre-fills the form for you to confirm. */
export interface JobParse {
  company: string | null;
  role: string | null;
  seniority: Seniority | null;
  responsibilities: string[];
  must_haves: string[];
  nice_to_haves: string[];
}

export interface JobDocument {
  text: string;
  parsed: JobParse;
  /** Set when this posting is already saved: no parse ran, and the form
   *  switches to the saved job with last time's corrections. */
  saved_job: SavedJob | null;
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
  /** This question's own clock, in seconds, set by the model when it planned
   *  the interview (ADR 0016). Only enforced when the setup is time-bounded. */
  seconds: number;
}

export interface Answer {
  question_id: number;
  text: string;
  /** The clock or Harvey ended it, not the candidate: no "thank you" next (ADR 0028). */
  cut_off?: boolean;
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
  /** Resume lines, or garden entries by label ([S3]). */
  cited_lines: string[];
  has_material: boolean;
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
  difficulty: Difficulty;
  garden_used: boolean;
  items: QuestionReport[];
}

// --- The Digital Garden (mirrors backend/src/anyview/brain/models.py) -------

export type EntityKind = "role" | "project" | "story" | "skill" | "achievement" | "education" | "language" | "feedback";

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
  /** Ongoing work in the role; bounded work is a project (ADR 0019). */
  responsibilities: string[];
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
  /** Roles whose ongoing work shows this skill (ADR 0019). */
  role_ids: string[];
  /** Credentials that attest to this skill (ADR 0020). */
  achievement_ids: string[];
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

export interface Feedback {
  id: string;
  label: string;
  role_id: string | null;
  project_id: string | null;
  given_by: string;
  content: string;
  received_on: string | null;
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
  feedback: Feedback[];
  coverage: Coverage;
  pending_proposals: number;
}

// Drafts: what the model proposed, editable in the review queue.
interface Draft {
  key: string;
  existing: string | null;
  evidence: string;
  /** The quote could not be found in the dump; the user decides (ADR 0019). */
  unverified?: boolean;
}
export interface RoleDraft extends Draft {
  company: string;
  title: string;
  start_date: string | null;
  end_date: string | null;
  level: string | null;
  responsibilities: string[];
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
  roles: string[];
  /** Credentials that attest to it: keys or labels (ADR 0020). */
  achievements: string[];
  /** Link target (draft key or label) → the quote that justified it. */
  link_evidence: Record<string, string>;
  /** Other names folded into this skill as near-duplicates (ADR 0021). */
  merged_from?: string[];
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
export interface FeedbackDraft extends Draft {
  role: string | null;
  project: string | null;
  given_by: string;
  content: string;
  received_on: string | null;
}
export interface Patch {
  roles: RoleDraft[];
  projects: ProjectDraft[];
  stories: StoryDraft[];
  skills: SkillDraft[];
  achievements: AchievementDraft[];
  education: EducationDraft[];
  languages: LanguageDraft[];
  feedback: FeedbackDraft[];
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
