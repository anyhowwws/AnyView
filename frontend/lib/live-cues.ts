// The browser's clock for a question on Gemini Live (ADR 0016, 0031).
//
// Live hears the candidate and decides when an answer is finished, but it does
// not notice silence on its own: it only reacts once someone has spoken. So the
// browser still owns time, as it always has, and tells Harvey when to step in.
// What Harvey *says* is up to him; when he says it is decided here, by rules
// kept pure so they can be tested without a microphone.

export type LiveCue = "silent" | "move_on" | "time_up";

/** Dead air an interviewer would notice. Untimed interviews wait longer. */
export const LIVE_DEAD_AIR_MS = 10_000;
export const LIVE_UNTIMED_DEAD_AIR_MS = 30_000;
/** After a nudge, how much more silence counts as "let's move on". */
export const LIVE_GIVE_UP_MS = 15_000;
/** Nudges per question; past this, the next long silence moves on. */
export const MAX_NUDGES = 2;
/** After a cue that closes the question, how long to wait for Harvey to close it
 *  before the browser closes it itself. */
export const CLOSE_GRACE_MS = 15_000;

export interface CueState {
  /** When Harvey finished asking the question: the clock starts here. Null until then. */
  askedAt: number | null;
  /** The last moment anyone was audible: the candidate talking or Harvey playing. */
  lastSoundAt: number;
  nudges: number;
  /** When the last nudge was sent. Cleared when the candidate speaks again. */
  nudgedAt: number | null;
  /** A cue that closes the question has gone. Nothing more is sent after it. */
  closing: boolean;
  closingAt: number | null;
}

export const FRESH: CueState = {
  askedAt: null,
  lastSoundAt: 0,
  nudges: 0,
  nudgedAt: null,
  closing: false,
  closingAt: null,
};

export interface CueLimits {
  /** The question's budget in ms, or null when the interview is untimed. */
  budgetMs: number | null;
}

/** Fold one tick into the state. Returns the cue to send now, if any, and
 *  `end` when the browser should close the question itself because Harvey has
 *  not, long after being told to. */
export function nextCue(
  state: CueState,
  { now, candidate, harvey }: { now: number; candidate: boolean; harvey: boolean },
  limits: CueLimits,
): { state: CueState; cue: LiveCue | null; end: boolean } {
  let next = candidate || harvey ? { ...state, lastSoundAt: now } : state;
  // They answered the nudge: the next long silence is a fresh one.
  if (candidate && next.nudgedAt !== null) next = { ...next, nudgedAt: null };

  if (next.closing) {
    const overdue = next.closingAt !== null && now - next.closingAt >= CLOSE_GRACE_MS;
    return { state: next, cue: null, end: overdue };
  }
  if (next.askedAt === null) return { state: next, cue: null, end: false };

  const close = (cue: LiveCue) => ({
    state: { ...next, closing: true, closingAt: now },
    cue,
    end: false,
  });

  // The clock beats everything: a timed question ends when it ends.
  if (limits.budgetMs !== null && now - next.askedAt >= limits.budgetMs) return close("time_up");

  const quietFor = now - Math.max(next.lastSoundAt, next.askedAt);
  const deadAir = limits.budgetMs === null ? LIVE_UNTIMED_DEAD_AIR_MS : LIVE_DEAD_AIR_MS;

  if (next.nudgedAt !== null) {
    // Nudged, and the candidate has not spoken since. Harvey's nudge counts as
    // sound, so the silence is measured from when he stopped, or from the cue
    // if he has not started yet.
    if (now - Math.max(next.lastSoundAt, next.nudgedAt) >= LIVE_GIVE_UP_MS) return close("move_on");
    return { state: next, cue: null, end: false };
  }

  if (quietFor >= deadAir) {
    if (next.nudges >= MAX_NUDGES) return close("move_on");
    next = { ...next, nudges: next.nudges + 1, nudgedAt: now };
    return { state: next, cue: "silent", end: false };
  }
  return { state: next, cue: null, end: false };
}
