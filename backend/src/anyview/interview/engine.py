"""The interview state machine.

    intake → plan → ask → answer → probe (≤ max_probes) → next → ask …
                                                        ↘ wrap → score → report

Between two questions `adapt` may reword the next one and keeps the carry-over
note (ADR 0036); it is a refinement of `ask`, not a state of its own.

Transport-agnostic: text comes in as `str`, tokens go out as an iterator of
`str`, and the model is anything satisfying `Model`. HTTP/SSE lives in
`anyview.api`; voice can replace it later without touching this file.

Persisted states — the ones a `Session` can be in between requests — are
`ask`, `wrap`, and `report`. The others are passed through inside one call
so every transition in the brief's diagram is visible in `TRANSITIONS`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeout

from pydantic import ValidationError

from anyview.interview.models import (
    ADAPT_SCHEMA,
    IDEAL_SCHEMA,
    MAX_ANSWER_SECONDS,
    MAX_NOTES_CHARS,
    MAX_PROBES,
    MAX_QUESTION_CHARS,
    MIN_ANSWER_SECONDS,
    NO_ANSWER,
    PLAN_SCHEMA,
    QUESTION_COUNT,
    SCORE_SCHEMA,
    AdaptOutput,
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
from anyview.interview.prompts import (
    adapt_user,
    ideal_user,
    lead_in,
    plan_user,
    score_user,
    session_system,
)
from anyview.llm.adapter import Model, ModelError, Reply

log = logging.getLogger(__name__)

# How long the next question may wait for the planner (ADR 0036). The fast model
# answers in one to three seconds; past this, the planned question is asked.
ADAPT_DEADLINE_S = 6.0

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


def ask(session: Session, *, spoken: bool = False) -> Iterator[str]:
    """What the interviewer says for the current question: a fixed lead-in
    chosen by how the last turn ended, then the planned question word for word
    (ADR 0026, 0028). No model call. Does not change state: the session stays in
    `ask` until an answer arrives. A generator still, so the route streams it
    the same way it always has."""
    require_state(session, State.ASK)
    question = session.current_question
    if question is None:
        raise EngineError("No question to ask.")
    opening = lead_in(index=session.current, previous=session.previous_answer, spoken=spoken)
    yield " ".join(part for part in (opening, question.text.strip()) if part)


def submit_answer(session: Session, answer: Answer) -> Session:
    """ask → answer → (probe → answer)* → next → ask | wrap. Pure: no model call.

    Follow-ups happen inside a spoken Live turn (ADR 0031), where Harvey asks
    for each one and the API holds him to `MAX_PROBES`; they arrive here
    already answered, carried on the `Answer`. The probe transitions are walked
    so the machine stays the one in the brief."""
    require_state(session, State.ASK)
    question = session.current_question
    if question is None or answer.question_id != question.id:
        raise EngineError(
            f"Expected an answer to question {question.id if question else '?'}, "
            f"got one for question {answer.question_id}."
        )

    session = _move(session, State.ANSWER)
    session = session.model_copy(update={"answers": [*session.answers, answer]})

    if len(answer.follow_ups) > MAX_PROBES:
        raise EngineError(f"At most {MAX_PROBES} follow-ups per question.", status=422)
    for _ in answer.follow_ups:
        session = _move(_move(session, State.PROBE), State.ANSWER)

    session = _move(session, State.NEXT)
    if len(session.answers) < QUESTION_COUNT:
        session = session.model_copy(update={"current": session.current + 1})
        return _move(session, State.ASK)
    return _move(session, State.WRAP)


def _tidy(text: str, limit: int) -> str:
    """Whitespace collapsed, and cut at a word boundary under `limit`."""
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    return text


def _tidy_notes(text: str) -> str:
    """The note keeps its lines; each is tidied, and the whole is held to its cap."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    notes = "\n".join(line for line in lines if line)
    if len(notes) > MAX_NOTES_CHARS:
        notes = notes[:MAX_NOTES_CHARS].rsplit("\n", 1)[0]
    return notes


def _adapt_call(session: Session, *, model: Model) -> AdaptOutput:
    reply = model.generate(
        # The same system text as the plan and the report, so it is a cache hit,
        # and it gives the planner exactly what the interviewer knows: the garden
        # only at Panel.
        system=session_system(session.setup),
        user=adapt_user(
            session.setup,
            questions=session.questions,
            answers=session.answers,
            notes=session.notes,
        ),
        session_id=session.session_id,
        call="adapt",
        output_schema=ADAPT_SCHEMA,
        effort="low",
        max_tokens=1024,
        fast=True,
    )
    return AdaptOutput.model_validate(_structured(reply, "adapt the next question"))


def adapt(session: Session, *, model: Model, deadline: float = ADAPT_DEADLINE_S) -> Session:
    """Between two questions (ADR 0036): rewrite the carry-over note, and let the
    planner reword the next question. The server sets the limits, not the model:

    - only the next question can change, and only its wording and rationale; its
      id, competency and clock stay as planned, so the plan's coverage holds;
    - the question count never changes, and neither do follow-ups (`MAX_PROBES`);
    - the wording planned at the start is kept on `Question.planned`;
    - anything that goes wrong — the model fails, refuses, is slow, or returns an
      empty question — leaves the session as it was. The interview never waits
      on, or breaks for, the planner.

    Needs a session in `ask` with at least one answer, i.e. what `submit_answer`
    returns between two questions."""
    require_state(session, State.ASK)
    question = session.current_question
    if question is None or not session.answers:
        return session
    last = session.previous_answer
    if last is not None and last.text.strip() == NO_ANSWER and not last.follow_ups:
        return session  # nothing was said, so there is nothing to note or adapt to

    # A thread so the wait can be bounded: the SDK's own timeout is for the slow
    # calls. Not a `with` block, because leaving one waits for the thread; a call
    # that overruns finishes in the background and its result is dropped.
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        output = pool.submit(_adapt_call, session, model=model).result(timeout=deadline)
    except FutureTimeout:
        log.warning(
            "adapt: no answer in %.0fs for %s; asking as planned", deadline, session.session_id
        )
        return session
    except (ModelError, EngineError, ValidationError) as exc:
        log.warning("adapt failed for %s: %s; asking as planned", session.session_id, exc)
        return session
    finally:
        pool.shutdown(wait=False)

    update: dict = {"notes": _tidy_notes(output.notes) or session.notes}
    text = _tidy(output.text, MAX_QUESTION_CHARS)
    if output.rewrite and text and text != question.text.strip():
        rewritten = question.model_copy(
            update={
                "text": text,
                "rationale": _tidy(output.rationale, MAX_QUESTION_CHARS) or question.rationale,
                # Rewritten twice keeps the first plan, not the first rewrite.
                "planned": question.planned or question.text,
            }
        )
        questions = list(session.questions)
        questions[session.current] = rewritten
        update["questions"] = questions
    return session.model_copy(update=update)


def _score_one(
    session: Session,
    system: str,
    question: Question,
    answer: Answer,
    *,
    model: Model,
    relevant: str = "",
) -> QuestionReport:
    """Two structured calls for one answer: the rubric score, and the ideal
    answer grounded in whatever record the setup carries. Neither reads the
    other, so they run side by side: the score in a helper thread, the ideal
    answer in this one. `.result()` waits for the score and re-raises any
    error it hit, exactly as if it had been called here."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        score_future = pool.submit(
            model.generate,
            system=system,
            user=score_user(question, answer.text, answer.follow_ups),
            session_id=session.session_id,
            call="score",
            output_schema=SCORE_SCHEMA,
            effort="high",
            max_tokens=2048,
            fallback=True,
        )
        ideal_reply = model.generate(
            system=system,
            user=ideal_user(question, session.setup, relevant),
            session_id=session.session_id,
            call="ideal",
            output_schema=IDEAL_SCHEMA,
            effort="high",
            max_tokens=2048,
            fallback=True,
        )
        score_reply = score_future.result()
    try:
        score = ScoreOutput.model_validate(_structured(score_reply, "score the answer"))
        ideal = IdealAnswer.model_validate(_structured(ideal_reply, "write the ideal answer"))
    except ValidationError as exc:
        raise EngineError("A score came back malformed. Please retry.", status=502) from exc

    return QuestionReport(
        question=question,
        answer=answer.text,
        follow_ups=answer.follow_ups,
        dimensions=score.dimensions,
        summary=score.summary,
        gaps=score.gaps,
        ideal=ideal,
    )


def begin_scoring(session: Session) -> Report:
    """wrap → score. Checks the session can be scored and returns the report's
    header with no items yet. Separate from the scoring itself so a streamed
    route can refuse a bad session with a plain 4xx before the stream opens."""
    require_state(session, State.WRAP)
    if len(session.answers) != len(session.questions):
        raise EngineError("Every question needs an answer before scoring.")
    _move(session, State.SCORE)
    return Report(
        session_id=session.session_id,
        company=session.setup.company,
        role=session.setup.role,
        seniority=session.setup.seniority,
        difficulty=session.setup.difficulty,
        garden_used=bool(session.setup.garden and session.setup.garden.strip()),
        items=[],
    )


def score_as_ready(
    session: Session, *, model: Model, relevant: dict[int, str] | None = None
) -> Iterator[tuple[int, QuestionReport]]:
    """Score every answer concurrently and yield `(index, item)` as each one
    finishes — in finishing order, not question order. Each takes 20–40 s on
    the model and none depends on another, so the wall time is the slowest
    answer's, and a caller can show the first result long before the last.
    The SDK client is thread-safe. Call `begin_scoring` first.

    `relevant` maps a question id to the garden entries nearest it, for a
    garden too big to read whole (ADR 0038)."""
    relevant = relevant or {}
    system = session_system(session.setup)
    pairs = list(zip(session.questions, session.answers, strict=True))
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        # future → its question's position, so a result can be put back in place.
        futures = {
            pool.submit(
                _score_one,
                session,
                system,
                question,
                answer,
                model=model,
                relevant=relevant.get(question.id, ""),
            ): i
            for i, (question, answer) in enumerate(pairs)
        }
        for future in as_completed(futures):
            yield futures[future], future.result()


def finish(session: Session, *, model: Model, relevant: dict[int, str] | None = None) -> Report:
    """wrap → score → report, all at once: `score_as_ready` collected back into
    question order."""
    report = begin_scoring(session)
    items: list[QuestionReport | None] = [None] * len(session.questions)
    for i, item in score_as_ready(session, model=model, relevant=relevant):
        items[i] = item
    # The transitions are checked, not stored: the browser owns the session.
    _move(_move(session, State.SCORE), State.REPORT)
    return report.model_copy(update={"items": items})
