import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DEAD_AIR_MS,
  GIVE_UP_AFTER_STALL_MS,
  LISTENING,
  MAX_QUESTION_MS,
  QUESTION,
  SILENCE_MS,
  SPEECH_MS,
  UNTIMED,
  hearing,
  pickFormat,
  timedLimits,
  type ListenLimits,
  type ListenState,
} from "../lib/voice.ts";

const THRESHOLD = 0.02;
const LOUD = 0.2;
const QUIET = 0.001;

/** A two-minute question, the common case. */
const TIMED = timedLimits(120);

/** Feed a run of samples 50 ms apart, starting at t=0. */
function speak(levels: number[], limits: ListenLimits = UNTIMED, start: ListenState = LISTENING): ListenState {
  let state = start;
  levels.forEach((level, i) => {
    state = hearing(state, { level, at: i * 50, startedAt: 0, threshold: THRESHOLD, limits });
  });
  return state;
}

const held = (ms: number, level: number) => Array(Math.ceil(ms / 50)).fill(level);

test("a short noise is not speech", () => {
  assert.equal(speak(held(SPEECH_MS - 100, LOUD)).heardSpeech, false);
});

test("sustained sound is speech", () => {
  const state = speak(held(SPEECH_MS + 200, LOUD));
  assert.equal(state.heardSpeech, true);
  assert.equal(state.ended, null);
});

test("a pause mid-answer does not end the turn", () => {
  const state = speak([...held(1000, LOUD), ...held(SILENCE_MS - 500, QUIET), ...held(500, LOUD)]);
  assert.equal(state.ended, null);
  assert.equal(state.heardSpeech, true);
});

test("silence after speaking ends the turn", () => {
  assert.equal(speak([...held(1000, LOUD), ...held(SILENCE_MS + 200, QUIET)]).ended, "silence");
});

test("untimed, a dead microphone gives up rather than recording forever", () => {
  const state = hearing(LISTENING, {
    level: QUIET,
    at: UNTIMED.deadAirMs + 1,
    startedAt: 0,
    threshold: THRESHOLD,
    limits: UNTIMED,
  });
  assert.equal(state.ended, "no-speech");
});

test("an ended turn stays ended", () => {
  const ended = speak([...held(1000, LOUD), ...held(SILENCE_MS + 200, QUIET)]);
  const after = hearing(ended, {
    level: LOUD,
    at: 99_000,
    startedAt: 0,
    threshold: THRESHOLD,
    limits: UNTIMED,
  });
  assert.deepEqual(after, ended);
});

// --- Time-bounded interviews (ADR 0016) -------------------------------------

test("timed, ten seconds of dead air stalls but does not end the turn", () => {
  const state = speak(held(DEAD_AIR_MS + 200, QUIET), TIMED);
  assert.equal(state.stalled, true, "Harvey should have something to say");
  assert.equal(state.ended, null, "but the microphone stays open");
});

test("timed, silence after her 'shall we move on?' is taken as a yes", () => {
  const before = speak(held(DEAD_AIR_MS + GIVE_UP_AFTER_STALL_MS - 200, QUIET), TIMED);
  assert.equal(before.ended, null, "still waiting just before the give-up point");
  const after = speak(held(DEAD_AIR_MS + GIVE_UP_AFTER_STALL_MS + 100, QUIET), TIMED);
  assert.equal(after.ended, "no-speech");
  assert.ok(TIMED.giveUpMs! < TIMED.limitMs, "well before the question's own clock");
});

test("untimed never gives up on silence early: a dead microphone is a different problem", () => {
  assert.equal(UNTIMED.giveUpMs, null);
});

test("timed, a stalled turn recovers when they finally speak", () => {
  const state = speak([...held(DEAD_AIR_MS + 200, QUIET), ...held(SPEECH_MS + 200, LOUD)], TIMED);
  assert.equal(state.heardSpeech, true);
  assert.equal(state.ended, null);
});

test("the clock cuts in mid-sentence", () => {
  // Still talking at the limit: the turn ends anyway.
  let state = speak(held(2000, LOUD), TIMED);
  state = hearing(state, {
    level: LOUD,
    at: TIMED.limitMs,
    startedAt: 0,
    threshold: THRESHOLD,
    limits: TIMED,
  });
  assert.equal(state.ended, "limit");
});

test("a short question gets a short clock", () => {
  assert.equal(timedLimits(90).limitMs, 90_000);
  assert.equal(timedLimits(180).limitMs, 180_000);
});

test("no question may outrun the recording cap", () => {
  // Even if a budget slipped through, the upload has to stay uploadable.
  assert.ok(timedLimits(10_000).limitMs <= UNTIMED.limitMs);
});

test("the clock beats a pause: ending on time wins over ending on silence", () => {
  // Quiet for a while *and* past the limit — the reason must be the clock, so
  // Harvey says the right line.
  const short = timedLimits(45);
  let state = speak(held(2000, LOUD), short);
  state = hearing(state, {
    level: QUIET,
    at: short.limitMs + 5_000,
    startedAt: 0,
    threshold: THRESHOLD,
    limits: short,
  });
  assert.equal(state.ended, "limit");
});

test("the recording format keeps its codec and its ticket type apart", () => {
  const chrome = pickFormat((t) => t.startsWith("audio/webm"));
  assert.equal(chrome?.mimeType, "audio/webm;codecs=opus");
  assert.equal(chrome?.base, "audio/webm");
  assert.equal(pickFormat((t) => t === "audio/mp4")?.base, "audio/mp4");
  assert.equal(pickFormat(() => false), null);
});

test("asking Donna out loud: eight seconds of nothing closes the microphone", () => {
  const ticks = (ms: number) => Array(ms / 50 + 1).fill(QUIET);
  assert.equal(speak(ticks(7_000), QUESTION).ended, null);
  assert.equal(speak(ticks(8_000), QUESTION).ended, "no-speech");
});

test("asking Donna out loud: a question is capped at a minute", () => {
  assert.equal(speak(Array(MAX_QUESTION_MS / 50 + 1).fill(LOUD), QUESTION).ended, "limit");
});
