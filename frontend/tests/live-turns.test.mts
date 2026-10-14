import assert from "node:assert/strict";
import { test } from "node:test";
import { wordsIn } from "../lib/live-cues.ts";
import {
  FILLER_HOLD_MS,
  QUIET_FLOOR,
  TURN_END_MS,
  TURN_START_MS,
  nextFloor,
  speechThreshold,
  type FloorState,
} from "../lib/live-turns.ts";

const FRAME_MS = 100;
const SPEECH = 0.1;
const ROOM = 0.002;

type Frame = {
  level?: number;
  words?: "real" | "filler" | null;
  harvey?: boolean;
};

/** Feed 100 ms frames from `from` to `to`; `at(t)` describes each. Returns the
 *  final state and the time of every start/end. */
function run(
  state: FloorState,
  from: number,
  to: number,
  at: (t: number) => Frame,
) {
  const actions: [string, number][] = [];
  for (let now = from; now < to; now += FRAME_MS) {
    const f = at(now);
    const out = nextFloor(state, {
      now,
      level: f.level ?? ROOM,
      words: f.words ?? null,
      harvey: f.harvey ?? false,
    });
    state = out.state;
    if (out.action) actions.push([out.action, now]);
  }
  return { state, actions };
}

test("a transcript fragment is words, only fillers, or nothing", () => {
  assert.equal(wordsIn(" I led the migration"), "real");
  assert.equal(wordsIn(" um, errr…"), "filler");
  assert.equal(wordsIn(" … "), null);
});

test("speech opens a turn after a short run, and a pause closes it", () => {
  const { actions } = run(QUIET_FLOOR, 0, 8_000, (t) => ({
    level: t >= 1_000 && t < 4_000 ? SPEECH : ROOM,
  }));
  assert.deepEqual(actions, [
    // The first frame at least TURN_START_MS after the first loud one.
    ["start", 1_000 + Math.ceil(TURN_START_MS / FRAME_MS) * FRAME_MS],
    ["end", 3_900 + TURN_END_MS],
  ]);
});

test("a cough is not a turn", () => {
  const { actions } = run(QUIET_FLOOR, 0, 3_000, (t) => ({
    level: t === 1_000 || t === 1_100 ? SPEECH : ROOM,
  }));
  assert.deepEqual(actions, []);
});

test("a thinking pause shorter than the end window keeps the turn open", () => {
  const { actions } = run(QUIET_FLOOR, 0, 10_000, (t) => ({
    level: (t >= 0 && t < 2_000) || (t >= 3_500 && t < 5_000) ? SPEECH : ROOM,
  }));
  assert.equal(actions.filter(([a]) => a === "start").length, 1);
  assert.deepEqual(actions.at(-1), ["end", 4_900 + TURN_END_MS]);
});

test("a trailing 'um' buys more time before the turn is called over", () => {
  const { actions } = run(QUIET_FLOOR, 0, 10_000, (t) => ({
    level: t < 2_000 ? SPEECH : ROOM,
    words: t === 2_000 ? "filler" : null,
  }));
  assert.deepEqual(actions.at(-1), ["end", 1_900 + FILLER_HOLD_MS]);
});

test("a late transcript of real words counts as sound", () => {
  // The transcript lags the audio: a fragment 1.5 s into the quiet still means
  // they were talking, so the end window restarts from it.
  const { actions } = run(QUIET_FLOOR, 0, 10_000, (t) => ({
    level: t < 2_000 ? SPEECH : ROOM,
    words: t === 3_500 ? "real" : null,
  }));
  assert.deepEqual(actions.at(-1), ["end", 3_500 + TURN_END_MS]);
});

test("Harvey's echo does not open a turn, a candidate talking over him does", () => {
  const echo = speechThreshold(QUIET_FLOOR.noise, false) * 1.5;
  const quiet = run(QUIET_FLOOR, 0, 2_000, () => ({
    level: echo,
    harvey: true,
  }));
  assert.deepEqual(quiet.actions, []);
  const over = run(QUIET_FLOOR, 0, 2_000, () => ({
    level: SPEECH,
    harvey: true,
  }));
  assert.equal(over.actions[0]?.[0], "start");
});

test("a steady hum is learned as the room, not taken for an endless answer", () => {
  const { state, actions } = run(QUIET_FLOOR, 0, 20_000, () => ({
    level: 0.015,
  }));
  const threshold = speechThreshold(state.noise, false);
  assert.ok(threshold > 0.015 && threshold <= 0.08, `threshold ${threshold}`);
  // At worst one short false turn while the floor catches up, then quiet.
  assert.ok(actions.length <= 2, JSON.stringify(actions));
  assert.ok((actions.at(-1)?.[1] ?? 0) < 6_000, JSON.stringify(actions));
  assert.equal(state.speaking, false);
});

test("real speech, with its gaps, keeps the floor low", () => {
  // 100 ms dips between words, every half second, for 30 s.
  const { state, actions } = run(QUIET_FLOOR, 0, 30_000, (t) => ({
    level: t % 500 === 0 ? ROOM : 0.05,
  }));
  assert.equal(actions.length, 1);
  assert.equal(state.speaking, true);
  assert.ok(speechThreshold(state.noise, false) < 0.05);
});
