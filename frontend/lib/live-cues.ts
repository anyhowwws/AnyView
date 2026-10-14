// The browser's clock for a question on Gemini Live (ADR 0016, 0031, 0032).
//
// Live hears the candidate and decides when an answer is finished, but barge-in
// runs one way: their speech interrupts Harvey, never the reverse, so he cannot
// cut in when time is up. And it cannot tell "err…" from an answer. So the browser owns time and silence
// outright: it plays Harvey's fixed lines (the `/interview/say` clips) and ends
// the question itself. When that happens is decided here, by rules kept pure so
// they can be tested without a microphone.
//
// "Silence" is measured from the candidate's last real word, or from the last
// moment their voice was clearly above the room. Words alone relied on Live
// transcribing while they speak; it does not always, so someone talking straight
// through was nudged and then moved on mid-sentence. A level alone counted
// breathing and the room as talking, and the nudge never came. So a level counts
// only when it is well above the room's own and lasts longer than a breath
// (`hearVoice`). A long "ummm" now counts as talking too: missing a nudge is far
// better than cutting someone off.

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

/** How long a level has to stay up to be a voice, not a breath or a click. */
export const VOICE_MS = 300;
/** A voice is this many times the room's level, and never below MIN_VOICE:
 *  higher than the turn-based path's 3x, because here a false "talking" only
 *  delays a nudge while a missed one cuts someone off. */
const VOICE_MULTIPLE = 4;
const MIN_VOICE = 0.02;
const MAX_VOICE = 0.08;
/** The room's level follows quiet fast and loud slowly, per 100 ms frame: speech
 *  has gaps between words that pull it back down, a fan or a hum does not, so a
 *  steady noise is absorbed in a couple of seconds and speech barely moves it. */
const ROOM_FALL = 0.3;
const ROOM_RISE = 0.005;

export interface VoiceState {
  /** The room's level when nobody is talking. */
  room: number;
  loudSince: number | null;
}

export const QUIET_ROOM: VoiceState = { room: MIN_VOICE / VOICE_MULTIPLE, loudSince: null };

export function voiceThreshold(room: number): number {
  return Math.min(MAX_VOICE, Math.max(MIN_VOICE, room * VOICE_MULTIPLE));
}

/** Fold one microphone frame in. `voice` is true while the candidate is clearly
 *  talking, whether or not Live has transcribed any of it yet. */
export function hearVoice(
  state: VoiceState,
  { now, level }: { now: number; level: number },
): { state: VoiceState; voice: boolean } {
  const loud = level >= voiceThreshold(state.room);
  const rate = level < state.room ? ROOM_FALL : ROOM_RISE;
  const next: VoiceState = {
    room: state.room + (level - state.room) * rate,
    loudSince: loud ? (state.loudSince ?? now) : null,
  };
  return { state: next, voice: next.loudSince !== null && now - next.loudSince >= VOICE_MS };
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
