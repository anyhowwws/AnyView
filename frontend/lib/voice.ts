// Voice mode (ADR 0013): Harvey's speech out, the candidate's speech in.
// Time-bounded interviews (ADR 0016) add a clock to the listening rules.
//
// Out: the /interview/ask stream carries a WAV clip per sentence. They must be
// heard in order and without gaps, so each one is decoded and scheduled on the
// Web Audio clock rather than handed to an <audio> element, which would leave
// an audible seam between sentences.
//
// In: MediaRecorder captures the answer while an AnalyserNode watches the
// level, so the turn ends when the candidate stops talking rather than when
// they remember to click. No dependency does either job; both are ~50 lines of
// platform API.

/** Level below which we call it silence. Adapted per recording from the room's
 *  own noise floor, then clamped: a noisy room must not set the bar so high
 *  that speech reads as silence. */
const FLOOR_MULTIPLE = 3;
const MIN_THRESHOLD = 0.012;
const MAX_THRESHOLD = 0.08;

/** How long a level has to stay up before we believe it is speech and not a
 *  door closing. */
export const SPEECH_MS = 250;
/** How long a pause has to run before the turn is over. Long enough to think
 *  mid-answer, short enough that the conversation doesn't stall. */
export const SILENCE_MS = 2500;
/** Dead air that an interviewer would notice. In a timed interview Harvey says
 *  something; in an untimed one it is how we spot a dead microphone. */
export const DEAD_AIR_MS = 10_000;
/** After Harvey has asked "shall we move on?", how much more silence counts as a
 *  yes. Without it a timed question sat in silence until its whole clock ran out. */
export const GIVE_UP_AFTER_STALL_MS = 15_000;
export const UNTIMED_DEAD_AIR_MS = 30_000;
/** A hard cap, well inside the 10 MB upload limit at 32 kbps. A timed question
 *  replaces this with its own, shorter clock. */
export const MAX_ANSWER_MS = 4 * 60_000;

export type ListenEnd = "silence" | "limit" | "no-speech";

/** What ends a turn, and when. A timed question passes its own `limitMs` and
 *  leaves `endOnDeadAir` off, because dead air is Harvey's cue to speak, not to
 *  give up (ADR 0016). */
export interface ListenLimits {
  silenceMs: number;
  deadAirMs: number;
  limitMs: number;
  endOnDeadAir: boolean;
  /** Timed only: silence from the start this long, with nothing said, ends the
   *  turn as no answer. Null leaves it to `endOnDeadAir`. */
  giveUpMs: number | null;
}

export const UNTIMED: ListenLimits = {
  silenceMs: SILENCE_MS,
  deadAirMs: UNTIMED_DEAD_AIR_MS,
  limitMs: MAX_ANSWER_MS,
  endOnDeadAir: true,
  giveUpMs: null,
};

export function timedLimits(seconds: number): ListenLimits {
  return {
    silenceMs: SILENCE_MS,
    deadAirMs: DEAD_AIR_MS,
    limitMs: Math.min(seconds * 1000, MAX_ANSWER_MS),
    endOnDeadAir: false,
    giveUpMs: DEAD_AIR_MS + GIVE_UP_AFTER_STALL_MS,
  };
}

export interface ListenState {
  heardSpeech: boolean;
  loudSince: number | null;
  quietSince: number | null;
  /** Dead air has gone on long enough to be awkward. Not an ending: it is what
   *  makes Harvey ask whether to move on. */
  stalled: boolean;
  ended: ListenEnd | null;
}

export const LISTENING: ListenState = {
  heardSpeech: false,
  loudSince: null,
  quietSince: null,
  stalled: false,
  ended: null,
};

/** One microphone sample folded into the listening state.
 *
 *  Pure on purpose: the turn-taking rules are the part worth testing, and they
 *  are impossible to test through getUserMedia. `level` is RMS amplitude in
 *  0..1, `at` and `startedAt` are timestamps in milliseconds. */
export function hearing(
  state: ListenState,
  {
    level,
    at,
    startedAt,
    threshold,
    limits,
  }: {
    level: number;
    at: number;
    startedAt: number;
    threshold: number;
    limits: ListenLimits;
  },
): ListenState {
  if (state.ended) return state;

  let next: ListenState;
  if (level >= threshold) {
    const loudSince = state.loudSince ?? at;
    next = {
      ...state,
      loudSince,
      quietSince: null,
      heardSpeech: state.heardSpeech || at - loudSince >= SPEECH_MS,
    };
  } else {
    next = { ...state, loudSince: null, quietSince: state.quietSince ?? at };
  }

  // The clock beats everything: a timed question ends when it ends, mid-word.
  if (at - startedAt >= limits.limitMs) return { ...next, ended: "limit" };

  if (next.heardSpeech) {
    if (next.quietSince !== null && at - next.quietSince >= limits.silenceMs) {
      return { ...next, ended: "silence" };
    }
  } else if (at - startedAt >= limits.deadAirMs) {
    // Nothing said yet. Untimed, that means a dead microphone; timed, it is
    // just a silence long enough for Harvey to fill.
    if (limits.endOnDeadAir) return { ...next, ended: "no-speech" };
    if (limits.giveUpMs !== null && at - startedAt >= limits.giveUpMs) {
      return { ...next, stalled: true, ended: "no-speech" };
    }
    next = { ...next, stalled: true };
  }
  return next;
}

// --- Harvey speaking ---------------------------------------------------------

function decodeBase64(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

/** One context for the whole page. Browsers cap how many a document may open,
 *  and Practice remounts on every question, so this must not be per instance. */
let shared: AudioContext | null = null;

function audioContext(): AudioContext {
  if (!shared) {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    shared = new Ctor();
  }
  return shared;
}

/** Call from a click handler. A browser lets a page start audio only in
 *  response to a click, and that permission fades within seconds — far less
 *  than planning an interview takes. The pre-flight's "Speak to me" and "Begin"
 *  clicks call this (ADR 0028). The same context drives the microphone's level
 *  meter, so this also keeps Safari from reading the microphone as silence: a
 *  context it never saw a click for stays suspended, and a suspended analyser
 *  reads zeros. */
export function unlockAudio(): void {
  try {
    const ctx = audioContext();
    if (ctx.state === "suspended") void ctx.resume();
  } catch {
    // No Web Audio: Practice falls back to text and says so.
  }
}

export class HarveyVoice {
  private ctx: AudioContext | null = null;
  private playing = new Set<AudioBufferSourceNode>();
  /** Decoding is async, so clips are chained rather than raced: clip two must
   *  not be scheduled before clip one has claimed its slot on the clock. */
  private chain: Promise<void> = Promise.resolve();
  private nextAt = 0;
  private complete = false;
  /** Called once the last clip has finished playing. */
  onFinished: (() => void) | null = null;

  get ready(): boolean {
    return this.ctx !== null;
  }

  /** Needs user activation: a browser will not start audio on a page nobody
   *  has clicked. Rejects if the context stays suspended, so the caller can
   *  ask for a click rather than leaving Harvey silently mute. */
  async enable(): Promise<void> {
    this.ctx = audioContext();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    if (this.ctx.state !== "running") throw new Error("audio is blocked until the page is clicked");
  }

  /** Queue one clip from an `audio` frame. */
  play(b64: string): void {
    this.chain = this.chain.then(() => this.schedule(b64)).catch((err) => {
      console.warn("voice playback failed", err);
    });
  }

  private async schedule(b64: string): Promise<void> {
    const ctx = this.ctx;
    if (!ctx) return;
    const buffer = await ctx.decodeAudioData(decodeBase64(b64));
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    // A hair in the future, so the first clip doesn't clip its own attack.
    const startAt = Math.max(ctx.currentTime + 0.02, this.nextAt);
    source.start(startAt);
    this.nextAt = startAt + buffer.duration;
    this.playing.add(source);
    source.onended = () => {
      this.playing.delete(source);
      this.settle();
    };
  }

  /** No more clips are coming for this question. */
  markComplete(): void {
    this.complete = true;
    void this.chain.then(() => this.settle());
  }

  private settle(): void {
    if (this.complete && this.playing.size === 0) {
      this.complete = false;
      this.onFinished?.();
    }
  }

  /** Stop listening for this question's end, but let whatever is playing
   *  finish. A new question calls this: "let's move on" must be heard to
   *  the end, and the next question's clips queue up behind it. */
  detach(): void {
    this.onFinished = null;
    this.complete = false;
  }

  /** Cut Harvey off — the candidate switched modes or left the interview. */
  stop(): void {
    for (const source of this.playing) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // already finished
      }
    }
    this.playing.clear();
    this.complete = false;
    this.nextAt = 0;
    this.chain = Promise.resolve();
  }
}

/** One player for the whole interview (ADR 0028). Practice remounts on every
 *  question, and a player per mount knew nothing of the clip still playing:
 *  the next question cut off "let's move on" and could talk over it. */
let harvey: HarveyVoice | null = null;

export function harveyVoice(): HarveyVoice {
  harvey ??= new HarveyVoice();
  return harvey;
}

// --- The candidate speaking -------------------------------------------------

/** One microphone stream for the whole interview, opened by the pre-flight
 *  (ADR 0028). Asking per question put Safari's permission prompt in the middle
 *  of question one and repeated the hardware start-up every turn. */
let mic: MediaStream | null = null;

export async function acquireMicrophone(): Promise<MediaStream> {
  if (mic?.getAudioTracks().some((t) => t.readyState === "live")) return mic;
  mic = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  return mic;
}

/** Turn the microphone off: the interview is over, or was abandoned. */
export function releaseMicrophone(): void {
  mic?.getTracks().forEach((t) => t.stop());
  mic = null;
}

/** A level reading on the shared context. `disconnect` leaves the stream and
 *  the context running for the next turn. */
function tap(stream: MediaStream) {
  const ctx = audioContext();
  if (ctx.state === "suspended") void ctx.resume();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  return {
    /** RMS amplitude, 0..1. */
    level(): number {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += s * s;
      return Math.sqrt(sum / samples.length);
    },
    disconnect: () => source.disconnect(),
  };
}

/** The pre-flight's meter: report the microphone level until stopped. */
export async function watchLevel(onLevel: (level: number) => void): Promise<() => void> {
  const meter = tap(await acquireMicrophone());
  let frame = requestAnimationFrame(function tick() {
    onLevel(meter.level());
    frame = requestAnimationFrame(tick);
  });
  return () => {
    cancelAnimationFrame(frame);
    meter.disconnect();
  };
}

/** The recording formats a browser might give us, best first. Chrome and
 *  Firefox produce WebM/Opus; Safari produces MP4/AAC. The base type is what
 *  the upload ticket is signed for, so it is kept separate from the codec. */
const FORMATS: { mimeType: string; base: string }[] = [
  { mimeType: "audio/webm;codecs=opus", base: "audio/webm" },
  { mimeType: "audio/webm", base: "audio/webm" },
  { mimeType: "audio/mp4", base: "audio/mp4" },
  { mimeType: "audio/ogg;codecs=opus", base: "audio/ogg" },
];

export function pickFormat(
  supported: (type: string) => boolean = (t) => MediaRecorder.isTypeSupported(t),
): { mimeType: string; base: string } | null {
  return FORMATS.find((f) => supported(f.mimeType)) ?? null;
}

export function microphoneSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

export interface Recording {
  blob: Blob;
  contentType: string;
  seconds: number;
  /** False when the clock ran out on someone who never started talking. Saves
   *  uploading and transcribing silence. */
  heardSpeech: boolean;
}

export interface ListenHandle {
  /** End the turn now (the "I'm done" button). */
  stop: () => void;
  /** Throw the recording away (leaving the question, switching to typing). */
  cancel: () => void;
}

export interface ListenOptions {
  onLevel: (level: number) => void;
  onEnd: (recording: Recording, reason: ListenEnd | "manual") => void;
  onError: (message: string) => void;
  /** Dead air went on long enough to be awkward. Fires at most once, and the
   *  microphone stays open — this is Harvey's cue to speak, not the end of the
   *  turn (ADR 0016). */
  onStall?: () => void;
  limits?: ListenLimits;
}

/** Open the microphone and hand back the recording once the candidate stops
 *  talking. The level callback drives the meter; the same samples decide when
 *  the turn is over. */
export async function listen({
  onLevel,
  onEnd,
  onError,
  onStall,
  limits = UNTIMED,
}: ListenOptions): Promise<ListenHandle> {
  const format = pickFormat();
  if (!format) {
    onError("This browser can't record audio. You can still type your answer.");
    return { stop: () => {}, cancel: () => {} };
  }

  let stream: MediaStream;
  try {
    stream = await acquireMicrophone();
  } catch {
    onError("The microphone is blocked. Allow it in your browser, or type your answer.");
    return { stop: () => {}, cancel: () => {} };
  }

  const recorder = new MediaRecorder(stream, { mimeType: format.mimeType, audioBitsPerSecond: 32_000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);

  const meter = tap(stream);

  const startedAt = performance.now();
  let state = LISTENING;
  let threshold = MIN_THRESHOLD;
  let floor = 0;
  let floorSamples = 0;
  let frame = 0;
  let cancelled = false;

  function teardown() {
    // The stream stays open for the next question; releaseMicrophone() ends it.
    cancelAnimationFrame(frame);
    meter.disconnect();
  }

  function finish(reason: ListenEnd | "manual") {
    if (recorder.state === "inactive") return;
    recorder.onstop = () => {
      teardown();
      if (cancelled) return;
      onEnd(
        {
          blob: new Blob(chunks, { type: format!.base }),
          contentType: format!.base,
          seconds: (performance.now() - startedAt) / 1000,
          heardSpeech: state.heardSpeech,
        },
        reason,
      );
    };
    recorder.stop();
  }

  function tick() {
    const level = meter.level();
    onLevel(level);

    const at = performance.now();
    // The first moments are the room, not the answer: use them to set the bar.
    if (at - startedAt < 400) {
      floor += level;
      floorSamples++;
      threshold = Math.min(
        MAX_THRESHOLD,
        Math.max(MIN_THRESHOLD, (floor / Math.max(floorSamples, 1)) * FLOOR_MULTIPLE),
      );
    }

    const was = state;
    state = hearing(state, { level, at, startedAt, threshold, limits });
    if (!was.stalled && state.stalled) onStall?.();
    if (state.ended) {
      finish(state.ended);
      return;
    }
    frame = requestAnimationFrame(tick);
  }

  recorder.start(250); // flush a chunk every 250 ms so nothing is lost on stop
  frame = requestAnimationFrame(tick);

  return {
    stop: () => finish("manual"),
    cancel: () => {
      cancelled = true;
      finish("manual");
    },
  };
}
