import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LISTENING,
  MAX_ANSWER_MS,
  NO_SPEECH_MS,
  SILENCE_MS,
  SPEECH_MS,
  hearing,
  pickFormat,
  type ListenState,
} from "../lib/voice.ts";

const THRESHOLD = 0.02;
const LOUD = 0.2;
const QUIET = 0.001;

/** Feed a run of samples 50 ms apart, starting at t=0. */
function speak(levels: number[], start: ListenState = LISTENING): ListenState {
  let state = start;
  levels.forEach((level, i) => {
    state = hearing(state, { level, at: i * 50, startedAt: 0, threshold: THRESHOLD });
  });
  return state;
}

const held = (ms: number, level: number) => Array(Math.ceil(ms / 50)).fill(level);

test("a short noise is not speech", () => {
  const state = speak(held(SPEECH_MS - 100, LOUD));
  assert.equal(state.heardSpeech, false);
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
  const state = speak([...held(1000, LOUD), ...held(SILENCE_MS + 200, QUIET)]);
  assert.equal(state.ended, "silence");
});

test("silence before any speech never ends the turn as an answer", () => {
  const state = speak(held(SILENCE_MS * 2, QUIET));
  assert.equal(state.ended, null);
});

test("a dead microphone gives up rather than recording forever", () => {
  let state = LISTENING;
  state = hearing(state, { level: QUIET, at: NO_SPEECH_MS + 1, startedAt: 0, threshold: THRESHOLD });
  assert.equal(state.ended, "no-speech");
});

test("an answer that runs past the cap is stopped", () => {
  let state = speak(held(1000, LOUD));
  state = hearing(state, { level: LOUD, at: MAX_ANSWER_MS, startedAt: 0, threshold: THRESHOLD });
  assert.equal(state.ended, "too-long");
});

test("an ended turn stays ended", () => {
  const ended = speak([...held(1000, LOUD), ...held(SILENCE_MS + 200, QUIET)]);
  const after = hearing(ended, { level: LOUD, at: 99_000, startedAt: 0, threshold: THRESHOLD });
  assert.deepEqual(after, ended);
});

test("the recording format keeps its codec and its ticket type apart", () => {
  const chrome = pickFormat((t) => t.startsWith("audio/webm"));
  assert.equal(chrome?.mimeType, "audio/webm;codecs=opus");
  assert.equal(chrome?.base, "audio/webm");

  const safari = pickFormat((t) => t === "audio/mp4");
  assert.equal(safari?.base, "audio/mp4");

  assert.equal(pickFormat(() => false), null);
});
