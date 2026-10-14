"""One question of a spoken interview on Gemini Live (ADR 0031): the rules, not the plumbing.

The Live model talks, listens and decides when to follow up. This class holds
what the app decides instead, and turns what was said into the same `Answer`
the typed path produces:

- which question is asked (the planned one; the system text says it verbatim);
- whether a follow-up is allowed (at most `MAX_PROBES`, never after time is up);
- how the question ended: Harvey closing it, or the browser ending it for the
  clock, the silence or the candidate's "next question" (ADR 0032);
- what the candidate said to the question and to each follow-up.

No I/O here, so every rule is testable without a socket. `api/live.py` owns the
socket and calls these methods as events arrive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anyview.interview import engine
from anyview.interview.models import (
    MAX_ANSWER_CHARS,
    MAX_PROBES,
    NO_ANSWER,
    Answer,
    FollowUp,
    Session,
    State,
)
from anyview.interview.prompts import BEGIN, CUT_INS, LIVE_TOOLS, live_system

TOOLS = LIVE_TOOLS

# Why the browser ended a question (ADR 0032). The first two are cut-ins: the
# answer was stopped, not finished. "manual" is the candidate pressing "Next
# question", which is finishing.
END_REASONS = frozenset({"time_up", "move_on", "manual"})


@dataclass
class _Part:
    """One stretch of the candidate talking: to the question itself (`asked` is
    None) or to a follow-up (`asked` is what Harvey asked)."""

    asked: str | None
    heard: list[str] = field(default_factory=list)

    def text(self) -> str:
        # Transcription arrives in fragments that carry their own spacing, so
        # they are joined as-is and then the whitespace is tidied.
        said = " ".join("".join(self.heard).split())
        if len(said) > MAX_ANSWER_CHARS:
            said = said[:MAX_ANSWER_CHARS].rsplit(" ", 1)[0]
        return said or NO_ANSWER


class LiveTurn:
    def __init__(self, session: Session, *, manual_turns: bool = False) -> None:
        engine.require_state(session, State.ASK)
        question = session.current_question
        if question is None:
            raise engine.EngineError("No question to ask.")
        self.question = question
        self.system = live_system(
            session.setup,
            questions=session.questions,
            answers=session.answers,
            index=session.current,
            manual_turns=manual_turns,
        )
        self.manual_turns = manual_turns
        self.parts: list[_Part] = [_Part(asked=None)]
        self.harvey: list[str] = []
        self.finished = False
        self.time_up = False
        self.moved_on = False
        # Manual turns only: the browser has ended the question and Harvey is
        # saying his cut-in line (docs/live-manual-turns.md).
        self.cutting_in = False

    # --- What happened ---------------------------------------------------------

    def heard(self, text: str) -> None:
        """A fragment of the candidate's speech, transcribed."""
        self.parts[-1].heard.append(text)

    def said(self, text: str) -> None:
        """A fragment of what Harvey said, transcribed. Kept for the transcript."""
        self.harvey.append(text)

    begin = BEGIN

    def end(self, reason: str) -> None:
        """The browser ended the question. An unknown reason counts as the
        candidate's own "next question", the one that claims nothing."""
        if reason == "time_up":
            self.time_up = True
        if reason in ("time_up", "move_on"):
            self.moved_on = True

    def cut_in(self, reason: str) -> str | None:
        """With manual turns, a cut-in is Harvey's to say: end the question for
        `reason` and return the cue to send Live, or None when there is none
        (the candidate's own "next question" closes at once, as on auto)."""
        self.end(reason)
        if not self.manual_turns or reason not in CUT_INS:
            return None
        self.cutting_in = True
        return CUT_INS[reason]

    @property
    def follow_ups_used(self) -> int:
        return len(self.parts) - 1

    def tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Answer one of Harvey's tool calls. The reply goes back to the model."""
        if name == "finish_question":
            self.finished = True
            return {"ok": True}
        if name != "ask_follow_up":
            return {"error": f"There is no tool called {name}."}

        question = " ".join(str(args.get("question", "")).split())[:1_000]
        if self.time_up or self.moved_on:
            return {
                "allowed": False,
                "reason": "This question is over. Close it and call finish_question.",
            }
        if self.follow_ups_used >= MAX_PROBES:
            return {
                "allowed": False,
                "reason": "No more follow-ups on this question. Close it and call finish_question.",
            }
        if not question:
            return {"allowed": False, "reason": "Say which question you want to ask."}
        self.parts.append(_Part(asked=question))
        return {"allowed": True, "follow_ups_left": MAX_PROBES - self.follow_ups_used}

    # --- The result --------------------------------------------------------------

    def answer(self) -> Answer:
        """What was said, as the engine's `Answer`. Cut off when the clock or the
        silence ended it, so the next question does not thank them for it."""
        main = self.parts[0].text()
        return Answer(
            question_id=self.question.id,
            text=main,
            cut_off=self.moved_on or main == NO_ANSWER,
            follow_ups=[
                FollowUp(question=part.asked, answer=part.text())
                for part in self.parts[1:]
                if part.asked
            ],
        )
