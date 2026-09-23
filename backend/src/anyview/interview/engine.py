"""The interview state machine.

    intake → plan → ask → answer → probe (≤ max_probes) → next → ask …
                                                        ↘ wrap → score → report

Transport-agnostic: text comes in as `str`, tokens go out as an iterator of
`str`, and the model is anything satisfying `Model`. HTTP/SSE lives in
`anyview.api`; voice can replace it later without touching this file.

Persisted states — the ones a `Session` can be in between requests — are
`ask`, `wrap`, and `report`. The others are passed through inside one call
so every transition in the brief's diagram is visible in `TRANSITIONS`.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from pydantic import ValidationError

from anyview.interview.models import (
    IDEAL_SCHEMA,
    MAX_ANSWER_SECONDS,
    MAX_PROBES,
    MIN_ANSWER_SECONDS,
    PLAN_SCHEMA,
    QUESTION_COUNT,
    SCORE_SCHEMA,
    Answer,
    IdealAnswer,
    PlanOutput,
    Question,
    QuestionReport,
    Report,
    ScoreOutput,
    Session,
    Setup,
    State,
)
from anyview.interview.prompts import ask_user, ideal_user, plan_user, score_user, session_system
from anyview.llm.adapter import Model, Reply

TRANSITIONS: dict[State, set[State]] = {
    State.INTAKE: {State.PLAN},
    State.PLAN: {State.ASK},
    State.ASK: {State.ANSWER},
    State.ANSWER: {State.PROBE, State.NEXT},
    State.PROBE: {State.ANSWER},
    State.NEXT: {State.ASK, State.WRAP},
    State.WRAP: {State.SCORE},
    State.SCORE: {State.REPORT},
    State.REPORT: set(),
}


class EngineError(Exception):
    """A request that does not fit the session's state or the model's output.
    `status` is the HTTP status the API layer should use."""

    def __init__(self, user_message: str, *, status: int = 409) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def _move(session: Session, to: State) -> Session:
    if to not in TRANSITIONS[session.state]:
        raise EngineError(f"Cannot move from {session.state} to {to}.")
    return session.model_copy(update={"state": to})


def require_state(session: Session, *states: State) -> None:
    if session.state not in states:
        expected = " or ".join(s.value for s in states)
        raise EngineError(f"This session is in state '{session.state}', expected {expected}.")


def _structured(reply: Reply, what: str) -> dict:
    """Turn a Reply into the dict the caller asked for, or explain why not."""
    if reply.refused:
        raise EngineError(f"The model declined to {what}.", status=502)
    if reply.truncated or reply.data is None:
        raise EngineError(f"The model's {what} output was incomplete. Please retry.", status=502)
    return reply.data


# --- Transitions ---------------------------------------------------------------


def start(setup: Setup, *, session_id: str, model: Model) -> Session:
    """intake → plan → ask. One structured call plans all questions up front."""
    session = Session(session_id=session_id, setup=setup)
    session = _move(session, State.PLAN)

    reply = model.generate(
        system=session_system(setup),
        user=plan_user(setup),
        session_id=session_id,
        call="plan",
        output_schema=PLAN_SCHEMA,
        effort="high",
        max_tokens=4096,
    )
    try:
        plan = PlanOutput.model_validate(_structured(reply, "plan the interview"))
    except ValidationError as exc:
        raise EngineError(
            "The interview plan came back malformed. Please retry.", status=502
        ) from exc

    questions = [
        Question(
            id=i + 1,
            text=item.text,
            competency=item.competency,
            rationale=item.rationale,
            # The model picks the clock; this keeps a stray one sane.
            seconds=max(MIN_ANSWER_SECONDS, min(MAX_ANSWER_SECONDS, item.seconds)),
        )
        for i, item in enumerate(plan.questions)
    ]
    session = session.model_copy(update={"questions": questions, "current": 0})
    return _move(session, State.ASK)


def ask(session: Session, *, model: Model) -> Iterator[str]:
    """Stream what the interviewer says for the current question. Does not change
    state: the session stays in `ask` until an answer arrives."""
    require_state(session, State.ASK)
    question = session.current_question
    if question is None:
        raise EngineError("No question to ask.")
    previous = session.previous_answer.text if session.previous_answer else None
    yield from model.stream(
        system=session_system(session.setup),
        user=ask_user(question, index=session.current, previous_answer=previous),
        session_id=session.session_id,
        call="ask",
        effort="low",
        max_tokens=400,
    )


def submit_answer(session: Session, answer: Answer) -> Session:
    """ask → answer → next → ask | wrap. Pure: no model call in Phase 0
    (probing is off), so this is where the brief's probe branch will plug in."""
    require_state(session, State.ASK)
    question = session.current_question
    if question is None or answer.question_id != question.id:
        raise EngineError(
            f"Expected an answer to question {question.id if question else '?'}, "
            f"got one for question {answer.question_id}."
        )

    session = _move(session, State.ANSWER)
    session = session.model_copy(update={"answers": [*session.answers, answer]})

    probes_used = 0  # Phase 3: count follow-ups asked for this question
    if probes_used < MAX_PROBES:
        pass  # Phase 3: _move(session, State.PROBE) and stream a follow-up

    session = _move(session, State.NEXT)
    if len(session.answers) < QUESTION_COUNT:
        session = session.model_copy(update={"current": session.current + 1})
        return _move(session, State.ASK)
    return _move(session, State.WRAP)


def _score_one(
    session: Session, system: str, question: Question, answer: Answer, *, model: Model
) -> QuestionReport:
    """Two structured calls for one answer: the rubric score, and the ideal
    answer grounded in whatever record the setup carries."""
    score_reply = model.generate(
        system=system,
        user=score_user(question, answer.text),
        session_id=session.session_id,
        call="score",
        output_schema=SCORE_SCHEMA,
        effort="high",
        max_tokens=2048,
    )
    ideal_reply = model.generate(
        system=system,
        user=ideal_user(question, session.setup),
        session_id=session.session_id,
        call="ideal",
        output_schema=IDEAL_SCHEMA,
        effort="high",
        max_tokens=2048,
    )
    try:
        score = ScoreOutput.model_validate(_structured(score_reply, "score the answer"))
        ideal = IdealAnswer.model_validate(_structured(ideal_reply, "write the ideal answer"))
    except ValidationError as exc:
        raise EngineError("A score came back malformed. Please retry.", status=502) from exc

    return QuestionReport(
        question=question,
        answer=answer.text,
        dimensions=score.dimensions,
        summary=score.summary,
        gaps=score.gaps,
        ideal=ideal,
    )


def finish(session: Session, *, model: Model) -> Report:
    """wrap → score → report. The five answers are scored concurrently: each
    takes 20–40 s on the model and none depends on another, so wall time is
    one answer's worth, not five. The SDK client is thread-safe, and
    `pool.map` returns results in question order whichever finishes first."""
    require_state(session, State.WRAP)
    if len(session.answers) != len(session.questions):
        raise EngineError("Every question needs an answer before scoring.")
    session = _move(session, State.SCORE)

    system = session_system(session.setup)
    pairs = list(zip(session.questions, session.answers, strict=True))
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        items = list(pool.map(lambda qa: _score_one(session, system, *qa, model=model), pairs))

    _move(session, State.REPORT)
    return Report(
        session_id=session.session_id,
        company=session.setup.company,
        role=session.setup.role,
        seniority=session.setup.seniority,
        difficulty=session.setup.difficulty,
        garden_used=bool(session.setup.garden and session.setup.garden.strip()),
        items=items,
    )
