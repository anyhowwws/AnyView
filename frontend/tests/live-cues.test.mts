import assert from "node:assert/strict";
import { test } from "node:test";
import {
  FRESH,
  LIVE_DEAD_AIR_MS,
  LIVE_GIVE_UP_MS,
  LIVE_UNTIMED_DEAD_AIR_MS,
  MAX_NUDGES,
  QUIET_ROOM,
  VOICE_MS,
  hearVoice,
  nextCue,
  substantive,
  voiceThreshold,
  type CueLimits,
  type CueState,
  type LiveAction,
  type VoiceState,
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

// --- A voice above the room counts as talking -------------------------------------

/** Feed 100 ms microphone frames; returns when `voice` was true. */
function listen(state: VoiceState, from: number, to: number, level: (t: number) => number) {
  const voiced: number[] = [];
  for (let t = from; t < to; t += 100) {
    const out = hearVoice(state, { now: t, level: level(t) });
    state = out.state;
    if (out.voice) voiced.push(t);
  }
  return { state, voiced };
}

test("talking straight through, never transcribed, is not dead air", () => {
  // The bug: Live sent no transcript until the candidate stopped, so the clock
  // nudged and then moved them on mid-sentence. 40 s of steady talking, with
  // the 100 ms gaps between words real speech has, and no transcript at all.
  const talking = (t: number) => (t % 600 === 0 ? 0.003 : 0.06);
  let voice = QUIET_ROOM;
  let cues = asked;
  const actions: LiveAction[] = [];
  for (let t = 0; t <= 40_000; t += 100) {
    const heard = hearVoice(voice, { now: t, level: talking(t) });
    voice = heard.state;
    if (t % 250 !== 0) continue; // the clock ticks every 250 ms
    const out = nextCue(cues, { now: t, spoke: heard.voice, harvey: false }, TIMED);
    cues = out.state;
    if (out.action) actions.push(out.action);
  }
  assert.deepEqual(actions, []);
});

test("a breath or a click is not a voice", () => {
  const { voiced } = listen(QUIET_ROOM, 0, 3_000, (t) =>
    t >= 1_000 && t < 1_000 + VOICE_MS - 100 ? 0.06 : 0.003,
  );
  assert.deepEqual(voiced, []);
});

test("a quiet room stays silence, so the nudge still comes", () => {
  const { voiced } = listen(QUIET_ROOM, 0, 20_000, () => 0.008);
  assert.deepEqual(voiced, []);
});

test("a steady hum is learned as the room within a few seconds", () => {
  const { state, voiced } = listen(QUIET_ROOM, 0, 30_000, () => 0.03);
  assert.ok(voiceThreshold(state.room) > 0.03, `threshold ${voiceThreshold(state.room)}`);
  assert.ok((voiced.at(-1) ?? 0) < 5_000, `still a voice at ${voiced.at(-1)}`);
});
