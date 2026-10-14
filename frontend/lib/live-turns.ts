// Manual turn-taking on Gemini Live (LIVE_TURNS=manual): an experiment, see
// docs/live-manual-turns.md.
//
// With Live's own voice-activity detection off, the browser decides where each
// of the candidate's turns starts and ends, and tells Live with `activity`
// frames. That is what lets Harvey cut in on time-up: the browser ends the turn
// itself, and nothing the candidate says afterwards reaches him.
//
// The cost is that the browser now judges the end of *every* answer, which Live
// did well on its own. The decision is made here, from two signals:
//
// - the microphone level, every 100 ms frame, against a threshold that follows
//   the room's noise floor (as voice.ts does on the turn-based path), raised
//   while Harvey is audible so his voice leaking from the speakers is not
//   taken for the candidate talking over him;
// - Live's transcript of the turn, when it arrives mid-turn: a real word counts
//   as sound (fragments lag the audio), and a turn whose last fragment was only
//   "um" or "err…" is given longer before it is called over.
//
// Pure on purpose, like live-cues.ts: testable without a microphone.

/** Loud this long before it is speech, not a cough or a door. */
export const TURN_START_MS = 250;
/** Quiet this long and the answer is over. Live's own detection waited 1.2 s at
 *  low sensitivity; an interview answer has thinking pauses, so a little more. */
export const TURN_END_MS = 2_000;
/** After a trailing "um", they are still thinking: wait longer. */
export const FILLER_HOLD_MS = 3_500;
/** Audio kept from before the turn starts. Live adds no padding of its own in
 *  manual mode, so without it the first syllable would be lost. */
export const PRE_ROLL_FRAMES = 3;

const FLOOR_MULTIPLE = 3;
const MIN_THRESHOLD = 0.012;
const MAX_THRESHOLD = 0.08;
/** While Harvey is audible, speech has to beat his echo too. */
const ECHO_MULTIPLE = 2;
/** How the noise floor follows the room, per 100 ms frame. It falls fast to the
 *  quiet between words and rises slowly under a steady level, so speech (which
 *  always has gaps) barely moves it while a hum or a fan is absorbed in about
 *  two seconds. A classic minimum-tracker; it learns while Harvey talks too,
 *  since his echo can only make it more cautious. */
const FLOOR_FALL = 0.3;
const FLOOR_RISE = 0.005;

export interface FloorState {
  /** The candidate's turn is open on Live. */
  speaking: boolean;
  loudSince: number | null;
  /** The last moment that counted as sound: a loud frame or a real word. */
  lastSoundAt: number;
  /** The last transcript fragment was only a filler. */
  trailingFiller: boolean;
  /** The room's level when nobody is talking, smoothed. */
  noise: number;
}

export const QUIET_FLOOR: FloorState = {
  speaking: false,
  loudSince: null,
  lastSoundAt: 0,
  trailingFiller: false,
  noise: MIN_THRESHOLD / FLOOR_MULTIPLE,
};

export function speechThreshold(noise: number, harvey: boolean): number {
  const base = Math.min(MAX_THRESHOLD, Math.max(MIN_THRESHOLD, noise * FLOOR_MULTIPLE));
  return harvey ? base * ECHO_MULTIPLE : base;
}

/** Fold one microphone frame (and any transcript since the last) into the
 *  state. Returns `start` or `end` when the browser should tell Live. */
export function nextFloor(
  state: FloorState,
  {
    now,
    level,
    words,
    harvey,
  }: {
    now: number;
    level: number;
    words: "real" | "filler" | null;
    harvey: boolean;
  },
): { state: FloorState; action: "start" | "end" | null } {
  const threshold = speechThreshold(state.noise, harvey);
  const loud = level >= threshold;
  let next: FloorState = { ...state };

  if (loud) {
    next.loudSince = state.loudSince ?? now;
    next.lastSoundAt = now;
  } else {
    next.loudSince = null;
  }
  const rate = level < state.noise ? FLOOR_FALL : FLOOR_RISE;
  next.noise = state.noise + (level - state.noise) * rate;
  // `words` is `wordsIn` (live-cues.ts) of what Live transcribed since the last frame.
  if (words === "real") next = { ...next, lastSoundAt: now, trailingFiller: false };
  if (words === "filler") next = { ...next, trailingFiller: true };

  if (!next.speaking) {
    if (next.loudSince !== null && now - next.loudSince >= TURN_START_MS) {
      return {
        state: { ...next, speaking: true, trailingFiller: false },
        action: "start",
      };
    }
    return { state: next, action: null };
  }

  const wait = next.trailingFiller ? FILLER_HOLD_MS : TURN_END_MS;
  if (now - next.lastSoundAt >= wait) {
    return {
      state: { ...next, speaking: false, trailingFiller: false },
      action: "end",
    };
  }
  return { state: next, action: null };
}
