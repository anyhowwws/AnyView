"""A scripted stand-in for the real model.

Same four methods as `VertexGemini`, no network, no tokens. Tests use it to
drive the engine and the API deterministically; `ANYVIEW_FAKE_MODEL=1` runs the
whole app on it for a browser walk-through that costs nothing.

Replies are keyed by the `call` name (`plan`, `ask`, `score`, `ideal`,
`parse_job`, `transcribe`, `discover`, `segment`, `dedupe`, `link`) so a test can script
one kind of call without caring about the others. `speak` returns silence of a
plausible length instead of a reply, and `live` a scripted conversation (`FakeLive`).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from anyview.llm.adapter import (
    LIVE_INPUT_RATE,
    LIVE_OUTPUT_RATE,
    PCM_SAMPLE_RATE,
    Effort,
    LiveEvent,
    ModelError,
    Reply,
    Usage,
    _log_usage,
    spoken_prompt,
    wav,
)

_FAKE_USAGE = Usage(input_tokens=100, output_tokens=50, thinking_tokens=20, cache_read=80)


class FakeModel:
    def __init__(
        self, replies: dict[str, Any] | None = None, *, fail: str | None = None, delay: float = 0
    ) -> None:
        # `replies[call]` is a dict (returned as parsed JSON) or a str (returned as text).
        # `fail` names a call that should raise ModelError, to exercise error paths.
        self.replies = replies or {}
        self.fail = fail
        self.calls: list[dict[str, Any]] = []  # every invocation, for assertions
        self.delay = delay  # seconds per call, so a local run shows progress (ANYVIEW_FAKE_DELAY_S)
        self.live_sessions: list[FakeLive] = []  # every Live conversation opened, for assertions

    model = "fake"

    def _record(self, call: str, session_id: str, system: str, user: str) -> None:
        self.calls.append({"call": call, "session_id": session_id, "system": system, "user": user})
        if self.delay:
            time.sleep(self.delay)
        if self.fail == call:
            raise ModelError("fake failure", retryable=True)
        # Same usage plumbing as the real adapter (log line + sink), fake numbers.
        _log_usage(
            session_id=session_id, call=call, model=self.model, usage=_FAKE_USAGE, latency_ms=1
        )

    def generate(
        self,
        *,
        system: str,
        user: str,
        session_id: str,
        call: str,
        output_schema: dict[str, Any] | None = None,
        effort: Effort = "high",
        max_tokens: int = 4096,
        attachment: tuple[bytes, str] | None = None,
        fast: bool = False,
    ) -> Reply:
        self._record(call, session_id, system, user)
        if fast:
            self.calls[-1]["fast"] = True
        if attachment is not None:
            self.calls[-1]["attachment"] = (len(attachment[0]), attachment[1])
        reply = self.replies.get(call, DEFAULTS[call])
        if isinstance(reply, dict):
            return Reply(
                text=json.dumps(reply), stop_reason="end_turn", usage=_FAKE_USAGE, data=reply
            )
        return Reply(text=str(reply), stop_reason="end_turn", usage=_FAKE_USAGE)

    def stream(
        self,
        *,
        system: str,
        user: str,
        session_id: str,
        call: str,
        effort: Effort = "low",
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        self._record(call, session_id, system, user)
        text = str(self.replies.get(call, DEFAULTS[call]))
        # Yield word by word so streaming code paths see more than one frame.
        for i, word in enumerate(text.split(" ")):
            yield word if i == 0 else " " + word

    def speak(
        self, *, text: str, session_id: str, voice: str = "Charon", style: str | None = None
    ) -> bytes:
        """Silence, one real WAV file, lasting about as long as the words would.

        A browser decodes it like any other clip, so the whole voice path —
        queueing, playback, "Harvey has finished, your turn" — can be walked
        through locally with nothing but a microphone.
        """
        self._record("speak", session_id, voice, spoken_prompt(text, style))
        seconds = min(len(text) / SPOKEN_CHARS_PER_SECOND, 30)
        return wav(bytes(2 * int(PCM_SAMPLE_RATE * seconds)))

    def live(
        self,
        *,
        system: str,
        tools: list[dict[str, Any]],
        session_id: str,
        voice: str = "Charon",
        manual_turns: bool = False,
    ) -> AbstractAsyncContextManager[FakeLive]:
        """A scripted Live conversation (ADR 0031): see `FakeLive`."""
        self._record("live", session_id, system, voice)
        session = FakeLive(
            system,
            session_id=session_id,
            manual_turns=manual_turns,
            follow_ups=self.replies.get("live_follow_ups", 1),
            answer=str(self.replies.get("live_answer", DEFAULTS["transcribe"])),
        )
        self.live_sessions.append(session)

        @asynccontextmanager
        async def opened() -> AsyncIterator[FakeLive]:
            yield session

        return opened()


# Roughly conversational pace: ~150 words a minute at ~5.5 characters a word.
SPOKEN_CHARS_PER_SECOND = 14

# The fake "hears" an answer once this much microphone audio has arrived:
# four seconds at 16 kHz, 16-bit. A real microphone streams silence too, so a
# local walk-through answers itself; tests send exactly this much.
FAKE_ANSWER_BYTES = 4 * LIVE_INPUT_RATE * 2
FAKE_FOLLOW_UP = "What was the measurable outcome, in your own words?"


def _between(text: str, start: str, end: str) -> str:
    head, _, rest = text.partition(start)
    return rest.partition(end)[0].strip() if rest else ""


class FakeLive:
    """Harvey on Live, scripted. It asks the question in `<question>` when it
    gets `[begin]`, takes enough microphone audio as an answer, asks for
    `follow_ups` follow-ups through the tool, then closes the question: silently,
    or with a goodbye on the last question, as the real prompt asks (ADR 0032).
    Audio out is silence of a realistic length.

    With `manual_turns` (docs/live-manual-turns.md) it behaves as Live does with
    its own detection off: it hears audio and text only inside an
    `activity_start`/`activity_end` pair, answers when the turn ends rather
    than after four seconds, and cuts in on `[time_up]`/`[move_on]`. Activity
    marks sent to it without manual turns raise, as Vertex is documented to
    refuse them. `signals` records the order of marks and text for tests."""

    def __init__(
        self,
        system: str,
        *,
        session_id: str,
        follow_ups: int,
        answer: str,
        manual_turns: bool = False,
    ) -> None:
        self.question = _between(system, "<question>", "</question>") or "Tell me about yourself."
        self.last = "This is the last question" in system
        self.session_id = session_id
        self.follow_ups = follow_ups
        self.answer = answer
        self.manual_turns = manual_turns
        self.signals: list[str] = []
        self._active = False
        self._pending_cue: str | None = None
        self.sent_text: list[str] = []
        self.tool_results: list[tuple[str, dict[str, Any]]] = []
        self._queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue()
        self._heard = 0
        self._asked = 0
        self._listening = False
        self._closed = False

    async def _say(self, text: str) -> None:
        seconds = min(len(text) / SPOKEN_CHARS_PER_SECOND, 10)
        pcm = bytes(2 * int(LIVE_OUTPUT_RATE * seconds))
        for start in range(0, len(pcm), 9_600):  # 200 ms chunks, as Live sends them
            await self._queue.put(LiveEvent("audio", audio=pcm[start : start + 9_600]))
        await self._queue.put(LiveEvent("harvey_text", text=text))
        await self._queue.put(LiveEvent("turn_complete"))
        _log_usage(
            session_id=self.session_id, call="live", model="fake", usage=_FAKE_USAGE, latency_ms=1
        )

    async def _call(self, name: str, **args: Any) -> None:
        await self._queue.put(
            LiveEvent("tool_call", call_id=f"call-{len(self.tool_results)}", name=name, args=args)
        )

    async def send_audio(self, pcm: bytes) -> None:
        if not self._listening or (self.manual_turns and not self._active):
            return  # with manual turns, audio outside a turn is not input
        self._heard += len(pcm)
        if not self.manual_turns and self._heard >= FAKE_ANSWER_BYTES:
            await self._answered()

    async def _answered(self) -> None:
        self._listening = False
        self._heard = 0
        await self._queue.put(LiveEvent("candidate_text", text=self.answer))
        if self._asked < self.follow_ups:
            await self._call("ask_follow_up", question=FAKE_FOLLOW_UP, reason="no outcome")
        else:
            await self._close()

    async def activity_start(self) -> None:
        if not self.manual_turns:
            raise ModelError("activity_start sent with automatic activity detection on")
        self.signals.append("start")
        self._active = True

    async def activity_end(self) -> None:
        if not self.manual_turns:
            raise ModelError("activity_end sent with automatic activity detection on")
        self.signals.append("end")
        self._active = False
        cue, self._pending_cue = self._pending_cue, None
        if cue is not None:
            await self._cue(cue)
        elif self._listening and self._heard > 0:
            await self._answered()

    async def _close(self) -> None:
        if self.last:
            await self._say("That's all my questions. Thanks for your time today.")
        await self._call("finish_question")

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)
        if not self.manual_turns:
            await self._cue(text)
            return
        self.signals.append("text:" + text.split("]")[0] + "]")
        # Manual turns: text is part of the turn, answered when the turn ends.
        if self._active:
            self._pending_cue = text

    async def _cue(self, text: str) -> None:
        if text.startswith("[begin]"):
            await self._say(self.question)
            self._listening = True
        elif self.manual_turns and text.startswith(("[time_up]", "[move_on]")):
            self._listening = False
            line = (
                "That's all my questions. Thanks for your time today."
                if self.last
                else "Let me stop you there — we need to keep moving."
            )
            await self._say(line)
            await self._call("finish_question")

    async def send_tool_result(self, call_id: str, name: str, result: dict[str, Any]) -> None:
        self.tool_results.append((name, result))
        if name == "ask_follow_up":
            self._asked += 1
            if result.get("allowed"):
                await self._say(FAKE_FOLLOW_UP)
                self._listening = True
            else:
                await self._close()
        elif name == "finish_question":
            await self._queue.put(LiveEvent("turn_complete"))

    async def events(self) -> AsyncIterator[LiveEvent]:
        while (event := await self._queue.get()) is not None:
            yield event


def default_plan(count: int) -> dict[str, Any]:
    # Mirrors the real plan's shape, opener included (ADR 0016): question one is
    # "tell me about yourself" and gets a shorter clock than a failure story.
    competencies = ["background", "ownership", "ambiguity", "conflict", "failure"]
    questions = [
        {
            "text": f"Tell me about a time you demonstrated {competencies[i % 5]}.",
            "competency": competencies[i % 5],
            "rationale": "Scripted by FakeModel.",
            "seconds": 150,
        }
        for i in range(count)
    ]
    if questions:
        questions[0] = {
            "text": "So, to get us started — tell me about yourself.",
            "competency": "background",
            "rationale": "Scripted by FakeModel.",
            "seconds": 90,
        }
    return {"questions": questions}


DEFAULTS: dict[str, Any] = {
    # A plausible brain patch for the resume in tests/conftest.py. Evidence quotes
    # are verbatim fragments of that resume so the evidence check keeps them.
    "propose": {
        "roles": [
            {
                "key": "r1",
                "existing": None,
                "company": "Acme Corp",
                "title": "Senior Cloud Architect",
                "start_date": "2021-01-01",
                "end_date": None,
                "level": "senior",
                "responsibilities": ["Maintain the Terraform module library for 6 product teams"],
                "evidence": "Acme Corp (2021–present) — Senior Cloud Architect",
            },  # fmt: skip
        ],
        "projects": [
            {
                "key": "p1",
                "existing": None,
                "role": "r1",
                "name": "Billing service migration to Cloud Run",
                "problem": None,
                "action": "Led migration of the billing service from VMs to Cloud Run",
                "result": "cutting monthly infra cost 38%",
                "tech": ["Cloud Run"],
                "metrics": ["-38% monthly infra cost"],
                "evidence": (
                    "Led migration of the billing service from VMs to Cloud Run, "
                    "cutting monthly infra cost 38%."
                ),
            },  # fmt: skip
        ],
        "stories": [
            {
                "key": "s1",
                "existing": None,
                "role": "r1",
                "project": None,
                "title": "On-call rota redesign after two Sev-1s",
                "situation": "two Sev-1 incidents",
                "task": None,
                "action": "Ran the on-call rota redesign",
                "result": "MTTR dropped from 4h to 50m",
                "competencies": ["ownership", "failure"],
                "evidence": (
                    "Ran the on-call rota redesign after two Sev-1 incidents; "
                    "MTTR dropped from 4h to 50m."
                ),
            },  # fmt: skip
        ],
        "skills": [
            {
                "key": "k1",
                "existing": None,
                "name": "Terraform",
                "depth": 4,
                "projects": [],
                "evidence": "Designed the Terraform module library now used by 6 product teams.",
            },  # fmt: skip
        ],
        "achievements": [],
    },
    # Only dumps over 2,000 characters are segmented. This split (two jobs,
    # then everything else as skills) is enough for a local walk-through to
    # show several parts being read; tests script their own ranges.
    "segment": {
        "sections": [
            {"kind": "experience", "start_line": 1, "end_line": 3, "job": 1},
            {"kind": "experience", "start_line": 4, "end_line": 6, "job": 2},
            {"kind": "skills", "start_line": 7, "end_line": 9999, "job": 0},
        ]
    },
    # No near-duplicates among the scripted skills (ADR 0021).
    "dedupe": {"groups": []},
    # One checked link: the Terraform bullet sits inside the Acme role's text.
    "link": {
        "links": [
            {
                "skill": "k1",
                "target": "r1",
                "evidence": "Designed the Terraform module library now used by 6 product teams.",
            }
        ]
    },
    "extract": (
        "Jordan Lee — Cloud Solutions Architect\n\nAcme Corp (2021–present) — Senior Cloud "
        "Architect\n- Led migration of the billing service from VMs to Cloud Run, cutting monthly "
        "infra cost 38%.\n- Designed the Terraform module library now used by 6 product teams."
    ),
    "plan": default_plan(5),
    # A plausible read of a job description for the role in tests/conftest.py.
    "parse_job": {
        "company": "Initech",
        "role": "Cloud Architect",
        "seniority": "senior",
        "responsibilities": ["Own the platform roadmap"],
        "must_haves": ["Terraform", "Strong communication with product teams"],
        "nice_to_haves": ["Cloud Run"],
    },
    "transcribe": (
        "I led the billing service migration to Cloud Run. The situation was that our VM "
        "estate was costing about forty thousand a month, and I owned the platform budget. "
        "I ran the migration over two quarters and cut monthly infra cost by thirty-eight "
        "percent."
    ),
    # Cites two real labels from the default patch, repeats one, and invents
    # [P9], so the citation filter has something to drop.
    "discover": (
        "You led the billing service migration to Cloud Run [P1], and the on-call rota "
        "redesign [S1] is your clearest ownership story. [P1, S1] both sit under your Acme "
        "role. Nothing in your garden mentions Bedrock [P9]."
    ),
    "ask": "Thanks for that.",
    "score": {
        "dimensions": [
            {
                "dimension": "star_completeness",
                "score": 3,
                "evidence": "Situation, task, action present; result thin.",
            },
            {
                "dimension": "specificity",
                "score": 2,
                "evidence": "Named the team but not the system.",
            },
            {"dimension": "quantified_outcome", "score": 1, "evidence": "No numbers given."},
            {
                "dimension": "ownership_language",
                "score": 3,
                "evidence": "Used 'I' for the key decisions.",
            },
        ],
        "summary": "A solid structure that needs a measurable result.",
        "gaps": ["Add the metric that changed as a result."],
    },
    "ideal": {
        "answer": "Based on the resume: at Acme I led the migration of the billing service...",
        "cited_lines": ["Led migration of billing service to Cloud Run"],
        "has_material": True,
    },
}
