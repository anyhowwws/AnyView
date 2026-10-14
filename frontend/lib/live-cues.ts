// The browser's clock for a question on Gemini Live (ADR 0016, 0031, 0032).
//
// Live hears the candidate and decides when an answer is finished, but barge-in
// runs one way: their speech interrupts Harvey, never the reverse, so he cannot
// cut in when time is up. And it cannot tell "err…" from an answer. So the browser owns time and silence
// outright: it plays Harvey's fixed lines (the `/interview/say` clips) and ends
// the question itself. When that happens is decided here, by rules kept pure so
// they can be tested without a microphone.
//
// "Silence" is measured from the candidate's last real word, not from the mic
// level: a level counts fillers, breathing and the room as talking, and the
// nudge never came. This relies on Live transcribing while they speak, which it
// does in fragments every second or so.

/** What the browser does now. `stalled` is a nudge; the other two end the question. */
export type LiveAction = "stalled" | "move_on" | "time_up";

/** Dead air an interviewer would notice. Untimed interviews wait longer. */
export const LIVE_DEAD_AIR_MS = 10_000;
export const LIVE_UNTIMED_DEAD_AIR_MS = 30_000;
/** After a nudge, how much more silence counts as "let's move on". */
export const LIVE_GIVE_UP_MS = 15_000;
/** Nudges per question; past this, the next long silence moves on. */
export const MAX_NUDGES = 2;

/** Sounds that are not words. Repeated letters ("ummm", "errr") count too. */
const FILLER = /^(u+m+|u+h+m*|e+r+m*|e+h+|h+m+|m+|a+h+|o+h+)$/;

/** Whether a transcript fragment has a real word in it, not just "um" or "err…". */
export function substantive(text: string): boolean {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}']+/u)
    .some((word) => word !== "" && !FILLER.test(word));
}

/** A transcript fragment as manual turn-taking sees it (live-turns.ts): words,
 *  only fillers, or nothing worth counting. */
export function wordsIn(text: string): "real" | "filler" | null {
  if (!/[\p{L}\p{N}]/u.test(text)) return null;
  return substantive(text) ? "real" : "filler";
}

export interface CueState {
  /** When Harvey finished asking the question: the clock starts here. Null until then. */
  askedAt: number | null;
  /** The last moment that counts as not-silence: a real word from the candidate,
   *  or Harvey speaking. */
  lastSoundAt: number;
  nudges: number;
  /** When the last nudge was played. Cleared when the candidate speaks again. */
  nudgedAt: number | null;
  /** The question has been ended. Nothing more happens after it. */
  ended: boolean;
}

export const FRESH: CueState = {
  askedAt: null,
  lastSoundAt: 0,
  nudges: 0,
  nudgedAt: null,
  ended: false,
};

export interface CueLimits {
  /** The question's budget in ms, or null when the interview is untimed. */
  budgetMs: number | null;
}

/** Fold one tick into the state. `spoke`: a substantive transcript fragment
 *  arrived since the last tick. `harvey`: Harvey is audible. Returns what the
 *  browser should do now, if anything. */
export function nextCue(
  state: CueState,
  { now, spoke, harvey }: { now: number; spoke: boolean; harvey: boolean },
  limits: CueLimits,
): { state: CueState; action: LiveAction | null } {
  if (state.ended) return { state, action: null };
  let next = spoke || harvey ? { ...state, lastSoundAt: now } : state;
  // They answered the nudge: the next long silence is a fresh one.
  if (spoke && next.nudgedAt !== null) next = { ...next, nudgedAt: null };
  if (next.askedAt === null) return { state: next, action: null };

  const end = (action: LiveAction) => ({ state: { ...next, ended: true }, action });

  // The clock beats everything: a timed question ends when it ends, even
  // mid-sentence.
  if (limits.budgetMs !== null && now - next.askedAt >= limits.budgetMs) return end("time_up");

  if (next.nudgedAt !== null) {
    // Nudged, and the candidate has not said a word since. The nudge counts as
    // sound, so the silence is measured from when it stopped playing.
    if (now - Math.max(next.lastSoundAt, next.nudgedAt) >= LIVE_GIVE_UP_MS) return end("move_on");
    return { state: next, action: null };
  }

  const quietFor = now - Math.max(next.lastSoundAt, next.askedAt);
  const deadAir = limits.budgetMs === null ? LIVE_UNTIMED_DEAD_AIR_MS : LIVE_DEAD_AIR_MS;
  if (quietFor >= deadAir) {
    if (next.nudges >= MAX_NUDGES) return end("move_on");
    next = { ...next, nudges: next.nudges + 1, nudgedAt: now };
    return { state: next, action: "stalled" };
  }
  return { state: next, action: null };
}
