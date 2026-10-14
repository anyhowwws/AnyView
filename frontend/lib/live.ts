// Harvey on Gemini Live (ADR 0031): one question as a live conversation.
//
// One WebSocket per question to the API, which holds the Live session (the
// browser cannot: Vertex accepts only IAM credentials). The microphone streams
// up as 16 kHz PCM the whole time; Harvey's voice streams down as 24 kHz PCM and
// is scheduled on the shared AudioContext. Live decides when the candidate has
// finished and whether to follow up. The browser keeps the clock (live-cues.ts)
// and tells Harvey when to step in. The question ends with a `done` frame
// carrying the Answer, which the caller posts like any other.
//
// No dependency: an AudioWorklet does the capture and downsampling in ~30 lines.

import { LIVE_URL, signInToken } from "@/lib/api";
import { FRESH, nextCue, type CueState, type LiveCue } from "@/lib/live-cues";
import type { Answer, Session } from "@/lib/types";
import { acquireMicrophone, audioContext } from "@/lib/voice";

const INPUT_RATE = 16_000;
const OUTPUT_RATE = 24_000;
/** Level above which the candidate counts as talking, for the dead-air clock.
 *  Noise suppression is on, so a fixed bar is enough for "is anyone there". */
const SPEAKING_LEVEL = 0.02;
const TICK_MS = 250;

// Runs on the audio thread. Averages each run of input samples down to one
// 16 kHz sample (a crude low-pass, plenty for speech), converts to 16-bit, and
// posts 100 ms frames with their loudness.
const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / ${INPUT_RATE};
    this.acc = 0; this.count = 0; this.pos = 0;
    this.out = new Int16Array(${INPUT_RATE / 10}); this.n = 0;
    this.energy = 0; this.samples = 0;
  }
  process(inputs) {
    const input = inputs[0] && inputs[0][0];
    if (!input) return true;
    for (let i = 0; i < input.length; i++) {
      const s = input[i];
      this.energy += s * s; this.samples++;
      this.acc += s; this.count++; this.pos++;
      if (this.pos >= this.step) {
        this.pos -= this.step;
        const v = Math.max(-1, Math.min(1, this.acc / this.count));
        this.out[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.acc = 0; this.count = 0;
        if (this.n === this.out.length) {
          const level = Math.sqrt(this.energy / Math.max(1, this.samples));
          this.port.postMessage({ pcm: this.out.buffer, level }, [this.out.buffer]);
          this.out = new Int16Array(${INPUT_RATE / 10}); this.n = 0;
          this.energy = 0; this.samples = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("anyview-capture", Capture);
`;

let workletLoaded: Promise<void> | null = null;

function loadWorklet(ctx: AudioContext): Promise<void> {
  if (!workletLoaded) {
    const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "text/javascript" }));
    workletLoaded = ctx.audioWorklet.addModule(url).catch((err) => {
      workletLoaded = null;
      throw err;
    });
  }
  return workletLoaded;
}

/** Whether this browser can hold a Live conversation at all. */
export function liveSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof WebSocket !== "undefined" &&
    typeof AudioWorkletNode !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

/** Set once Live has failed in this page: the rest of the interview uses the
 *  turn-based voice path rather than failing over on every question. */
let liveBroken = false;
export const liveAvailable = () => liveSupported() && !liveBroken;
export const markLiveBroken = () => {
  liveBroken = true;
};

export interface LiveHandlers {
  /** A fragment of what Harvey says, transcribed. */
  onHarvey: (text: string) => void;
  /** A fragment of what the candidate says, transcribed. */
  onCandidate: (text: string) => void;
  /** Harvey has finished asking: the clock starts. */
  onAsked: () => void;
  onFollowUp: (question: string) => void;
  onLevel: (level: number) => void;
  onDone: (answer: Answer) => void;
  /** `fallback`: Live itself failed, so use the turn-based voice path. */
  onError: (message: string, fallback: boolean) => void;
}

type Frame =
  | { type: "ready" | "turn_complete" | "interrupted" }
  | { type: "harvey" | "candidate"; text: string }
  | { type: "follow_up"; question: string; allowed: boolean }
  | { type: "done"; answer: Answer }
  | { type: "error"; message: string; fallback: boolean };

export class LiveQuestion {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private capture: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;
  private playing = new Set<AudioBufferSourceNode>();
  private nextAt = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private cues: CueState = FRESH;
  private level = 0;
  private finished = false;

  constructor(
    private session: Session,
    private handlers: LiveHandlers,
    /** The question's clock in ms, or null when the interview is untimed. */
    private budgetMs: number | null,
  ) {}

  async start(): Promise<void> {
    let token: string;
    try {
      token = await signInToken();
      this.ctx = audioContext();
      if (this.ctx.state === "suspended") await this.ctx.resume();
      await loadWorklet(this.ctx);
    } catch {
      this.fail("Live voice isn't available in this browser.", true);
      return;
    }
    if (this.finished) return; // closed while we were getting ready

    const ws = new WebSocket(LIVE_URL);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ token, session: this.session }));
    ws.onmessage = (event) => {
      if (typeof event.data === "string") this.frame(JSON.parse(event.data) as Frame);
      else this.play(event.data as ArrayBuffer);
    };
    ws.onerror = () => this.fail("Lost the connection to Harvey.", true);
    ws.onclose = () => {
      if (!this.finished) this.fail("Lost the connection to Harvey.", true);
    };
  }

  /** Close the question now, keeping what was said ("I'm done"). */
  end(): void {
    this.send({ type: "end" });
  }

  /** Tear everything down: the question changed, or the candidate left. */
  close(): void {
    this.finished = true;
    this.stopCapture();
    this.silence();
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close();
    this.ws = null;
  }

  private send(data: { type: "cue"; name: LiveCue } | { type: "end" }): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(data));
  }

  private frame(frame: Frame): void {
    switch (frame.type) {
      case "ready":
        void this.startCapture();
        break;
      case "harvey":
        this.handlers.onHarvey(frame.text);
        break;
      case "candidate":
        this.handlers.onCandidate(frame.text);
        break;
      case "turn_complete":
        if (this.cues.askedAt === null) {
          // The first turn is the question itself: the clock starts when it
          // has been heard, so wait for the audio still queued.
          const wait = Math.max(0, (this.nextAt - (this.ctx?.currentTime ?? 0)) * 1000);
          setTimeout(() => {
            if (this.finished || this.cues.askedAt !== null) return;
            this.cues = { ...this.cues, askedAt: performance.now(), lastSoundAt: performance.now() };
            this.handlers.onAsked();
          }, wait);
        }
        break;
      case "interrupted":
        this.silence(); // the candidate talked over Harvey: stop him mid-word
        break;
      case "follow_up":
        if (frame.allowed) this.handlers.onFollowUp(frame.question);
        break;
      case "done":
        this.finished = true;
        this.handlers.onDone(frame.answer);
        this.close();
        break;
      case "error":
        this.fail(frame.message, frame.fallback);
        break;
    }
  }

  private fail(message: string, fallback: boolean): void {
    if (this.finished) return;
    this.close();
    this.handlers.onError(message, fallback);
  }

  // --- The microphone ---------------------------------------------------------

  private async startCapture(): Promise<void> {
    const ctx = this.ctx;
    if (!ctx || this.finished) return;
    let stream: MediaStream;
    try {
      stream = await acquireMicrophone();
    } catch {
      this.fail("The microphone is blocked. Allow it in your browser, or type your answer.", false);
      return;
    }
    if (this.finished) return;
    this.source = ctx.createMediaStreamSource(stream);
    this.capture = new AudioWorkletNode(ctx, "anyview-capture");
    // A worklet only runs while it is connected to the graph; a muted gain
    // keeps it connected without playing the microphone back.
    this.sink = ctx.createGain();
    this.sink.gain.value = 0;
    this.source.connect(this.capture).connect(this.sink).connect(ctx.destination);
    this.capture.port.onmessage = (event: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
      this.level = event.data.level;
      this.handlers.onLevel(event.data.level);
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(event.data.pcm);
    };
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  private stopCapture(): void {
    if (this.capture) this.capture.port.onmessage = null;
    this.source?.disconnect();
    this.capture?.disconnect();
    this.sink?.disconnect();
    this.source = this.capture = this.sink = null;
  }

  private tick(): void {
    const harvey = !!this.ctx && this.nextAt > this.ctx.currentTime;
    const out = nextCue(
      this.cues,
      { now: performance.now(), candidate: this.level >= SPEAKING_LEVEL, harvey },
      { budgetMs: this.budgetMs },
    );
    this.cues = out.state;
    if (out.cue) this.send({ type: "cue", name: out.cue });
    if (out.end) this.end();
  }

  // --- Harvey's voice ---------------------------------------------------------

  private play(data: ArrayBuffer): void {
    const ctx = this.ctx;
    if (!ctx || this.finished) return;
    const samples = new Int16Array(data);
    const buffer = ctx.createBuffer(1, samples.length, OUTPUT_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 0x8000;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    // Chunks arrive faster than real time; each one starts where the last ends.
    const startAt = Math.max(ctx.currentTime + 0.05, this.nextAt);
    source.start(startAt);
    this.nextAt = startAt + buffer.duration;
    this.playing.add(source);
    source.onended = () => this.playing.delete(source);
  }

  private silence(): void {
    for (const source of this.playing) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // already finished
      }
    }
    this.playing.clear();
    this.nextAt = 0;
  }
}
