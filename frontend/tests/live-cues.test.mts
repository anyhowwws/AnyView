import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FRESH,
  LIVE_DEAD_AIR_MS,
  LIVE_GIVE_UP_MS,
  LIVE_UNTIMED_DEAD_AIR_MS,
  MAX_NUDGES,
  nextCue,
  substantive,
  type CueLimits,
  type CueState,
  type LiveAction,
} from "../lib/live-cues.ts";

const TIMED: CueLimits = { budgetMs: 120_000 };
const UNTIMED: CueLimits = { budgetMs: null };

/** Run ticks 250 ms apart from `from` to `to`; `talk(t)` says who is audible. */
function run(
  state: CueState,
  from: number,
  to: number,
  limits: CueLimits,
  talk: (t: number) => { spoke?: boolean; harvey?: boolean } = () => ({}),
) {
  const actions: [number, LiveAction][] = [];
  for (let t = from; t <= to; t += 250) {
    const who = talk(t);
    const out = nextCue(state, { now: t, spoke: !!who.spoke, harvey: !!who.harvey }, limits);
    state = out.state;
    if (out.action) actions.push([t, out.action]);
  }
  return { state, actions };
}

const asked: CueState = { ...FRESH, askedAt: 0, lastSoundAt: 0 };

test("fillers are not words", () => {
  for (const filler of ["um", " Uh…", "err", "Errr, erm", "hmm.", "Mm", "uhm, ah"]) {
    assert.equal(substantive(filler), false, filler);
  }
  for (const word of ["So", " um, I led", "Er, 38%", "it's", "a"]) {
    assert.equal(substantive(word), true, word);
  }
});

test("nothing happens before the question has been asked", () => {
  const { actions } = run(FRESH, 0, 60_000, TIMED);
  assert.deepEqual(actions, []);
});

test("ten seconds without a real word brings a nudge", () => {
  const { actions } = run(asked, 0, LIVE_DEAD_AIR_MS + 500, TIMED);
  assert.deepEqual(actions, [[LIVE_DEAD_AIR_MS, "stalled"]]);
});

test("silence after the nudge moves on", () => {
  // The nudge plays for two seconds after it fires.
  const nudge = LIVE_DEAD_AIR_MS;
  const { actions, state } = run(asked, 0, 40_000, TIMED, (t) => ({
    harvey: t > nudge && t <= nudge + 2000,
  }));
  assert.deepEqual(actions, [
    [nudge, "stalled"],
    [nudge + 2000 + LIVE_GIVE_UP_MS, "move_on"],
  ]);
  assert.equal(state.ended, true);
});

test("answering the nudge starts the count again", () => {
  const nudge = LIVE_DEAD_AIR_MS;
  const { actions } = run(asked, 0, 40_000, TIMED, (t) => ({ spoke: t > 12_000 && t <= 20_000 }));
  assert.deepEqual(actions, [
    [nudge, "stalled"],
    [20_000 + LIVE_DEAD_AIR_MS, "stalled"],
  ]);
});

test("after the last nudge, the next dead air moves on", () => {
  const state = { ...asked, nudges: MAX_NUDGES };
  const { actions } = run(state, 0, LIVE_DEAD_AIR_MS, TIMED);
  assert.deepEqual(actions, [[LIVE_DEAD_AIR_MS, "move_on"]]);
});

test("talking keeps the nudges away, and the budget still ends the question mid-sentence", () => {
  const { actions } = run(asked, 0, 130_000, TIMED, () => ({ spoke: true }));
  assert.deepEqual(actions, [[120_000, "time_up"]]);
});

test("an untimed question waits longer and never runs out", () => {
  const { actions } = run(asked, 0, LIVE_UNTIMED_DEAD_AIR_MS + 250, UNTIMED);
  assert.deepEqual(actions, [[LIVE_UNTIMED_DEAD_AIR_MS, "stalled"]]);
});

test("nothing follows the end of a question", () => {
  const { actions } = run(asked, 0, 300_000, TIMED, () => ({ spoke: true }));
  assert.deepEqual(actions, [[120_000, "time_up"]]);
});
