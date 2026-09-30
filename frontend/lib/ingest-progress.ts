// What the upload screen shows while Donna reads a resume (ADR 0019).
// Pure: the API's `progress` frames go in, a view comes out, so the
// sequencing is tested without a browser.

import type { EntityKind } from "./types";

export type Step = "upload" | "read" | "parts" | "tidy" | "link";

export interface Part {
  id: number;
  /** experience · projects · skills · certifications · education · languages · summary · other · document */
  kind: string;
  /** For one job of the experience section, its first line. */
  label: string;
  done: boolean;
  found: number | null;
  /** What this part found, by name, once read: shown while the rest are still being read. */
  names: string[];
}

export interface IngestView {
  step: Step;
  parts: Part[];
  /** Characters of text read from the file, once known. */
  characters: number | null;
}

/** One `progress` frame's data, as the API sends it. */
export type ProgressFrame =
  | { stage: "reading"; file: string }
  | { stage: "read"; characters: number }
  | { stage: "sections"; sections: { id: number; kind: string; label: string }[] }
  | { stage: "section_done"; id: number; found: number; names?: string[] }
  | { stage: "tidying"; skills: number }
  | { stage: "linking"; skills: number };

export function startView(fromFile: boolean): IngestView {
  return { step: fromFile ? "upload" : "parts", parts: [], characters: null };
}

export function applyProgress(view: IngestView, frame: ProgressFrame): IngestView {
  switch (frame.stage) {
    case "reading":
      return { ...view, step: "read" };
    case "read":
      return { ...view, characters: frame.characters };
    case "sections":
      return {
        ...view,
        step: "parts",
        parts: frame.sections.map((s) => ({ ...s, done: false, found: null, names: [] })),
      };
    case "section_done":
      return {
        ...view,
        parts: view.parts.map((p) =>
          p.id === frame.id ? { ...p, done: true, found: frame.found, names: frame.names ?? [] } : p,
        ),
      };
    case "tidying":
      return { ...view, step: "tidy" };
    case "linking":
      return { ...view, step: "link" };
    default:
      return view; // a stage this build does not know: keep showing what it does
  }
}

/** The one sentence at the top of the progress view. */
export function headline(view: IngestView): string {
  switch (view.step) {
    case "upload":
      return "Uploading your file";
    case "read":
      return "Reading your document";
    case "parts": {
      const left = view.parts.filter((p) => !p.done).length;
      if (view.parts.length === 0) return "Finding the sections";
      if (view.parts.length === 1) return "Reading what you wrote";
      return left === 0 ? "Putting the pieces together" : `Reading ${view.parts.length} parts at once`;
    }
    case "tidy":
      return "Folding duplicate skills together";
    case "link":
      return "Linking skills to where you used them";
  }
}

const PART_NAMES: Record<string, string> = {
  experience: "Experience",
  projects: "Projects",
  skills: "Skills",
  certifications: "Certifications",
  education: "Education",
  languages: "Languages",
  summary: "Summary",
  other: "Other details",
  document: "Your text",
};

export function partName(part: Part): string {
  return part.label || PART_NAMES[part.kind] || part.kind;
}

/** The garden kind a section mostly grows, for its node colour. */
export const PART_KIND: Record<string, EntityKind | null> = {
  experience: "role",
  projects: "project",
  skills: "skill",
  certifications: "achievement",
  education: "education",
  languages: "language",
  summary: "story",
  other: null,
  document: null,
};

export function entriesLabel(found: number): string {
  return found === 1 ? "1 entry" : `${found} entries`;
}
