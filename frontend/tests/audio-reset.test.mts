import assert from "node:assert/strict";
import { test } from "node:test";

// Just enough of the browser for lib/voice.ts: a context that records what is
// done to it, and a mediaDevices that can fire "devicechange" (ADR 0041).
class FakeContext {
  static made: FakeContext[] = [];
  state: "running" | "suspended" | "closed" = "suspended";
  currentTime = 0;
  constructor() {
    FakeContext.made.push(this);
  }
  async resume() {
    if (this.state !== "closed") this.state = "running";
  }
  async close() {
    this.state = "closed";
  }
}
const deviceListeners: (() => void)[] = [];
Object.assign(globalThis, {
  window: { AudioContext: FakeContext },
});
Object.defineProperty(globalThis, "navigator", {
  value: { mediaDevices: { addEventListener: (_: string, fn: () => void) => deviceListeners.push(fn) } },
  configurable: true,
});

const voice = await import("../lib/voice.ts");

test("resetAudio makes a new context, closes the old one and tells listeners", async () => {
  const first = voice.audioContext() as unknown as FakeContext;
  const heard: unknown[] = [];
  const stop = voice.onAudioReset((ctx) => heard.push(ctx));
  const second = voice.resetAudio() as unknown as FakeContext;
  stop();
  await Promise.resolve();
  assert.notEqual(second, first);
  assert.equal(first.state, "closed");
  assert.equal(voice.audioContext(), second);
  assert.deepEqual(heard, [second]);
});

test("an enabled player moves to the new context", async () => {
  const player = voice.harveyVoice();
  await player.enable();
  assert.equal(player.ready, true);
  const fresh = voice.resetAudio();
  // `ready` stays true and the next clip is scheduled on the new context.
  assert.equal(player.ready, true);
  assert.equal((player as unknown as { ctx: unknown }).ctx, fresh);
});

test("no rebuild without a device change, one after it", () => {
  const before = voice.audioContext();
  voice.refreshAudioIfDevicesChanged();
  assert.equal(voice.audioContext(), before);
  for (const fn of deviceListeners) fn(); // headphones connected
  voice.refreshAudioIfDevicesChanged();
  assert.notEqual(voice.audioContext(), before);
  const after = voice.audioContext();
  voice.refreshAudioIfDevicesChanged(); // the change was handled once
  assert.equal(voice.audioContext(), after);
});

test("a device change never cuts off a clip that is playing", () => {
  const player = voice.harveyVoice() as unknown as { nextAt: number };
  const ctx = voice.audioContext() as unknown as FakeContext;
  player.nextAt = ctx.currentTime + 2; // Harvey is mid-sentence
  for (const fn of deviceListeners) fn();
  voice.refreshAudioIfDevicesChanged();
  assert.equal(voice.audioContext(), ctx);
  player.nextAt = 0; // he finished: the next safe moment rebuilds
  voice.refreshAudioIfDevicesChanged();
  assert.notEqual(voice.audioContext(), ctx);
});

test("a stopped context is woken, not left suspended", () => {
  const ctx = voice.audioContext() as unknown as FakeContext;
  ctx.state = "suspended";
  voice.unlockAudio();
  return Promise.resolve().then(() => assert.equal(ctx.state, "running"));
});


test("a clip that fails reports an error and never claims to have finished", async () => {
  const player = new voice.VoicePlayer();
  await player.enable();
  const ctx = voice.audioContext() as unknown as { decodeAudioData: () => Promise<never> };
  ctx.decodeAudioData = () => Promise.reject(new Error("bad clip"));
  const events: string[] = [];
  player.onFinished = () => events.push("finished");
  player.onError = () => events.push("error");
  const warn = console.warn;
  console.warn = () => {};
  player.play(btoa("not audio"));
  player.markComplete();
  await new Promise((resolve) => setTimeout(resolve, 0));
  console.warn = warn;
  assert.deepEqual(events, ["error"]);
});
