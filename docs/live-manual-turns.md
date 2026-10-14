# Manual turn-taking on Live — findings

**Status:** experiment, branch `live-manual-turns`, behind `LIVE_TURNS=manual` (default `auto`).
Not run against Vertex. Not deployed. Not an ADR: if it is adopted, it becomes one that amends 0032.

## The question

ADR 0032 found that, with Live's automatic voice activity detection (VAD), barge-in runs one way:
the candidate can interrupt Harvey, Harvey cannot interrupt the candidate. So time-up and
move-on are fixed TTS clips the browser plays over a muted Live session. Its *Alternatives*
section asks whether turning automatic detection off would let Harvey cut in in his own Live
voice. This branch prototypes that.

## What the SDK and the docs say

| Fact | Source |
|---|---|
| `RealtimeInputConfig.automatic_activity_detection = AutomaticActivityDetection(disabled=True)` turns server-side VAD off: "the client must send activity signals". | google-genai 1.75.0, `types.py` (`AutomaticActivityDetection`, `RealtimeInputConfig`) |
| The client sends `send_realtime_input(activity_start=ActivityStart())` and `send_realtime_input(activity_end=ActivityEnd())`; both "can only be sent if automatic … activity detection is disabled". | `types.py` `ActivityStart` / `ActivityEnd`; `live.py` `AsyncSession.send_realtime_input` |
| Both are converted for **Vertex** as well as the Gemini API (`activityStart` / `activityEnd` in `_LiveSendRealtimeInputParameters_to_vertex`; `realtimeInputConfig` passed in the Vertex setup message). | `_live_converters.py` |
| `ActivityHandling`: `START_OF_ACTIVITY_INTERRUPTS` (default, barge-in) or `NO_INTERRUPTION`. `TurnCoverage`: default `TURN_INCLUDES_ONLY_ACTIVITY`, i.e. audio outside a marked turn is not part of it. | `types.py` |
| With VAD off, no `audioStreamEnd` is sent, and an interruption is marked by `activityEnd`. The server adds **no pre-speech padding** and **no silence tolerance**: the client should send audio from just before `activityStart`, and wait at least ~500 ms of silence before `activityEnd`. | [Gemini API Live guide](https://ai.google.dev/gemini-api/docs/live-guide), "Disable automatic VAD" |
| Vertex's own Live pages show `automatic_activity_detection` with `"disabled": False # default`, and do not describe the manual mode or say which models support it. | [Vertex: configure language and voice](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/configure-language-voice) |

**Unknown:** whether `gemini-live-2.5-flash-native-audio` on Vertex accepts manual activity (the
SDK will send it; the docs never name a model), and whether **input transcription** still arrives
in fragments *during* a manual turn or only after `activityEnd`.

## What the prototype does

Server (`LIVE_TURNS=manual`):

- `llm/adapter.py`: `live_config(manual_turns=True)` sets `disabled=True` and keeps proactive audio
  and default barge-in. `LiveSession` gains `activity_start()` / `activity_end()`.
- `api/live.py`: `ready` now says `"turns": "auto"|"manual"`, so the browser follows the server and
  there is no frontend flag. New browser frame `{"type": "activity", "state": "start"|"end"}`,
  ignored on auto. `_Floor` tracks whether the candidate's turn is open, so Live never gets a
  doubled start or a stray end.
- **Text needs a turn too.** With VAD off, `[begin]` is sent as `start → text → end`, or Live
  would never answer it.
- **The cut-in.** On `end` with `time_up`/`move_on`, the API sends a fixed cue (`prompts.CUT_INS`,
  by key; the browser never chooses words) inside the candidate's still-open turn, then ends that
  turn. Harvey replies with one sentence ("Let me stop you there — we need to keep moving", or his
  goodbye on the last question) and calls `finish_question`. `done` follows when his line's
  `turn_complete` arrives, or after `finish_question` plus the usual 4 s, or after 12 s at most
  (`CUT_IN_GRACE_S`). `cut_off` is set exactly as on auto. `manual` (the candidate's "Next
  question") still closes at once.
- `prompts.live_system(manual_turns=True)` swaps one paragraph: the room may send `[time_up]` or
  `[move_on]`, and Harvey cuts in. **On auto the prompt is byte-for-byte the one on `main`**,
  checked for all five questions.

Browser (`lib/live.ts`, new `lib/live-turns.ts`):

- In manual mode, microphone audio goes up **only inside a turn**, plus 300 ms of pre-roll, because
  the server adds no padding.
- At time-up/move-on it sends `end`, stops the mic, and **keeps playing Harvey's Live audio**: no
  clip, no muting. The `stalled` nudge is still the fixed clip in both modes (see "Not done").

## How the browser decides an answer is over

This is the cost the ADR 0032 alternative warned about: Live judged the end of every answer well,
and now `lib/live-turns.ts` does it, from two signals in 100 ms frames.

1. **Mic level against an adaptive threshold.** The threshold is 3× a noise floor, clamped to
   0.012–0.08 (the same numbers as the turn-based path in `voice.ts`). The floor is a
   minimum-tracker: it drops fast to the quiet between words and rises slowly under a steady
   level, so a fan or hum is absorbed in about two seconds while real speech barely moves it.
   While Harvey is audible the threshold doubles, so his voice leaking from the speakers doesn't
   count as the candidate talking over him.
2. **Live's transcript, if it arrives mid-turn.** A real word counts as sound (fragments lag the
   audio). A turn whose last fragment was only a filler ("um", "err…", the ADR 0032 list) gets
   3.5 s instead of 2 s.

A turn **starts** after 250 ms above the threshold and **ends** after 2 s with nothing above it
(3.5 s after a trailing filler). Live's own setting was 1.2 s at low sensitivity.

The dead-air clock (`live-cues.ts`) also counts an open turn as speech in manual mode. That is
the fix ADR 0032 named for the case where transcripts arrive only at the end of a turn.

**Risks, plainly:**

- **Thinking pauses.** Two seconds of silence ends the turn. If Harvey replies straight away, he
  steps on a candidate who was only thinking. Proactive audio *should* let him stay quiet when the
  turn looks unfinished, and the candidate's next word reopens the turn (barge-in cuts him off).
  Expect some of this; Live's VAD had the same trade-off at 1.2 s.
- **A level is not speech.** Typing, a chair, or a cough longer than 250 ms opens a turn. A short
  one then ends after 2 s with nothing in it, and Harvey may answer that silence. Only a real run
  will show how often.
- **Echo.** If echo cancellation leaks Harvey's voice at more than 2× the floor, his own voice opens
  a turn and barge-in cuts him off. Headphones remove this risk; laptop speakers are the case to test.
- **A steady noise above 0.012 at the start** can open one false turn before the floor learns it
  (about two seconds).
- **The filler rule depends on mid-turn transcription,** which is unverified with VAD off. Without
  it, the end of a turn is decided by level alone.
- **Quiet speakers.** A voice near the floor in a noisy room can fall under the 3× threshold and be
  cut off mid-answer. The turn-based path has the same limit.

## Verified vs unverified

Verified locally (no Vertex):

- Backend: 370 tests pass (10 new in `tests/test_live_manual.py`); `ruff check` and
  `ruff format --check` are clean. `FakeLive` with `manual_turns` hears audio only inside a turn,
  answers on `activity_end`, cuts in on `[time_up]`/`[move_on]`, and **raises if it gets activity
  marks on auto**. A test shows the auto path never sends them.
- Frontend: `typecheck`, `lint` and `npm test` pass (78 tests; 9 new in `tests/live-turns.test.mts`).
- The auto path is unchanged: same `live_config` on auto, the same prompt text, the same frames
  apart from the added `turns` field on `ready`.
- Not walked through in a browser: the in-app browser pane cannot open a microphone. To walk it
  through locally, run `api-fake` with `LIVE_TURNS=manual` added to its command, plus `web-fake`.
  Speak, stop for 2 s, and FakeLive answers. Leave the clock to run out mid-sentence and you'll see
  Harvey's cut-in line in the transcript (FakeLive's audio is silence).

Unverified, needs the real model:

1. Does Vertex accept `disabled: true` with `gemini-live-2.5-flash-native-audio`, and
   `activityStart`/`activityEnd` after it? (If not, the session errors at once, and the browser
   falls back to the turn-based path.)
2. Does `[begin]` sent as `start → text → end` get Harvey to open the question?
3. **The point of the experiment:** at time-up, with the candidate mid-sentence, does Harvey cut in
   within about a second, in his own voice, with one sentence, and call `finish_question`?
4. Does input transcription stream during a manual turn, or arrive only at `activityEnd`?
5. Does proactive audio keep Harvey quiet after a 2 s thinking pause, or does he jump in?
6. Does `tool_call` (`finish_question`) arrive before or after the cut-in line's `turn_complete`?
   The relay handles either order, but it decides whether `done` waits the extra 4 s.
7. Token cost: each extra, shorter turn re-bills the context (ADR 0031). Compare the `live` usage
   rows for one interview on each setting.

## How to try it against the real model

Set `LIVE_TURNS=manual` on the API, either locally on the `api-vertex` launch config or as a Cloud
Run env var. Nothing in Terraform sets it yet, which is deliberate for an experiment. The browser
needs no change: it reads `turns` from `ready`. Unset it to go back to ADR 0032 at once. Use one
timed interview with a short question budget and keep talking past the clock. Then do one run on
laptop speakers and one on headphones.

## Not done (on purpose)

- **The `stalled` nudge is still the fixed clip.** In manual mode Harvey could nudge in his own
  words the same way (a `[silent]` cue in a turn of its own), as ADR 0031 first wanted. That is a
  one-line `CUT_INS` entry and a branch in `live.ts`, once (3) above is known to work.
- `NO_INTERRUPTION` activity handling: not used. Barge-in on Harvey stays; the browser simply stops
  sending the microphone once it has cut in, which gives Harvey the floor without taking it away
  everywhere else.
- No Terraform variable, no ADR, no CLAUDE.md entry. These come with adoption.

## Recommendation

**Test further. Neither adopt nor drop yet.** The SDK supports manual activity on Vertex, and the
prototype is small and flag-gated: roughly 200 changed lines on each side, comments included
(plus `FakeLive` and tests), and the default path is unchanged. But everything that decides whether it is worth having needs the real model:
unverified points 1 and 3 decide whether it works at all, and 4 and 5 decide whether
browser-judged turns are good enough to replace Live's. Run 20 minutes against Vertex
with the setting on. If Harvey's own cut-in lands reliably and thinking pauses aren't stepped on
more than with auto, adopt it in an ADR amending 0032, and move the nudge over as well. If
Vertex refuses the mode, or the end-of-turn judgement is visibly worse, drop the branch: the
fixed clips work today.
