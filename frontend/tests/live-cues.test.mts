import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CLOSE_GRACE_MS,
  FRESH,
  LIVE_DEAD_AIR_MS,
  LIVE_GIVE_UP_MS,
  LIVE_UNTIMED_DEAD_AIR_MS,
  MAX_NUDGES,
  nextCue,
  type CueLimits,
  type CueState,
  type LiveCue,
} from "../lib/live-cues.ts";

const TIMED: CueLimits = { budgetMs: 120_000 };
const UNTIMED: CueLimits = { budgetMs: null };

/** Run ticks 250 ms apart from `from` to `to`; `talk(t)` says who is audible. */
function run(
  state: CueState,
  from: number,
  to: number,
  limits: CueLimits,
  talk: (t: number) => { candidate?: boolean; harvey?: boolean } = () => ({}),
) {
  const cues: [number, LiveCue][] = [];
  let ended: number | null = null;
  for (let t = from; t <= to; t += 250) {
    const who = talk(t);
    const out = nextCue(state, { now: t, candidate: !!who.candidate, harvey: !!who.harvey }, limits);
    state = out.state;
    if (out.cue) cues.push([t, out.cue]);
    if (out.end && ended === null) ended = t;
  }
  return { state, cues, ended };
}

const asked: CueState = { ...FRESH, askedAt: 0, lastSoundAt: 0 };

test("nothing happens before the question has been asked", () => {
  const { cues } = run(FRESH, 0, 60_000, TIMED);
  assert.deepEqual(cues, []);
});

test("ten seconds of dead air brings a nudge", () => {
  const { cues } = run(asked, 0, LIVE_DEAD_AIR_MS + 500, TIMED);
  assert.deepEqual(cues, [[LIVE_DEAD_AIR_MS, "silent"]]);
});

test("silence after the nudge moves on", () => {
  // Harvey's nudge plays for two seconds after it is sent.
  const nudge = LIVE_DEAD_AIR_MS;
  const { cues } = run(asked, 0, 40_000, TIMED, (t) => ({ harvey: t > nudge && t <= nudge + 2000 }));
  assert.deepEqual(cues, [
    [nudge, "silent"],
    [nudge + 2000 + LIVE_GIVE_UP_MS, "move_on"],
  ]);
});

test("answering the nudge starts the count again", () => {
  const nudge = LIVE_DEAD_AIR_MS;
  const { cues } = run(asked, 0, 40_000, TIMED, (t) => ({ candidate: t > 12_000 && t <= 20_000 }));
  assert.deepEqual(cues, [
    [nudge, "silent"],
    [20_000 + LIVE_DEAD_AIR_MS, "silent"],
  ]);
});

test("after the last nudge, the next dead air moves on", () => {
  const state = { ...asked, nudges: MAX_NUDGES };
  const { cues } = run(state, 0, LIVE_DEAD_AIR_MS, TIMED);
  assert.deepEqual(cues, [[LIVE_DEAD_AIR_MS, "move_on"]]);
});

test("talking keeps the nudges away, and the budget still ends the question", () => {
  const { cues } = run(asked, 0, 130_000, TIMED, () => ({ candidate: true }));
  assert.deepEqual(cues, [[120_000, "time_up"]]);
});

test("an untimed question waits longer and never runs out", () => {
  const { cues } = run(asked, 0, LIVE_UNTIMED_DEAD_AIR_MS + 250, UNTIMED, () => ({}));
  assert.deepEqual(cues, [[LIVE_UNTIMED_DEAD_AIR_MS, "silent"]]);
});

test("nothing follows a closing cue, and the browser closes if Harvey doesn't", () => {
  const { cues, ended } = run(asked, 0, 120_000 + CLOSE_GRACE_MS + 1000, TIMED, () => ({ candidate: true }));
  assert.deepEqual(cues, [[120_000, "time_up"]]);
  assert.equal(ended, 120_000 + CLOSE_GRACE_MS);
});
