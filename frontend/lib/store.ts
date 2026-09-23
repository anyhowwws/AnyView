// The in-progress interview survives a reload via sessionStorage. Storage can
// be unavailable (private mode, blocked site data), so every access is guarded
// and the app works without it.

import type { Report, Session } from "@/lib/types";

export type Phase = "setup" | "practice" | "report";

export interface Saved {
  phase: Phase;
  session: Session | null;
  report: Report | null;
  /** Interviewer text already streamed per question id, so a reload doesn't re-ask. */
  spoken: Record<number, string>;
}

const KEY = "anyview.phase0";

export const EMPTY: Saved = { phase: "setup", session: null, report: null, spoken: {} };

export function load(): Saved {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Saved) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function save(state: Saved): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // storage unavailable; the app keeps working in memory
  }
}

export function clear(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

// Voice mode is a preference, not session state, so it outlives the interview
// in localStorage (ADR 0013). Speaking is the default: an interview is a spoken
// event, so only someone who has actively chosen typing gets typing (ADR 0016).
const VOICE_KEY = "anyview.voice";

export function loadVoicePreference(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) !== "off";
  } catch {
    // No storage is not a preference for silence.
    return true;
  }
}

export function saveVoicePreference(on: boolean): void {
  try {
    localStorage.setItem(VOICE_KEY, on ? "on" : "off");
  } catch {
    // storage unavailable; the preference lasts for this page only
  }
}
