import pytest

from anyview.interview import engine
from anyview.interview.engine import TRANSITIONS, EngineError
from anyview.interview.models import NO_ANSWER, Answer, Session, State
from anyview.interview.prompts import OPENER
from anyview.llm.adapter import ModelError
from anyview.llm.fake import FakeModel


def _walk(setup, fake):
    """Run a whole interview and return (session, report)."""
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i in range(5):
        text = "".join(engine.ask(session))
        assert text
        session = engine.submit_answer(session, Answer(question_id=i + 1, text=f"answer {i + 1}"))
    return session, engine.finish(session, model=fake)


def test_every_brief_state_is_reachable_in_the_transition_table():
    reachable = {State.INTAKE} | {t for targets in TRANSITIONS.values() for t in targets}
    assert reachable == set(State)


def test_full_walk_produces_five_questions_and_a_report(setup):
    fake = FakeModel()
    session, report = _walk(setup, fake)

    assert session.state == State.WRAP
    assert [q.id for q in session.questions] == [1, 2, 3, 4, 5]
    assert len(report.items) == 5
    for item in report.items:
        assert len(item.dimensions) == 4
        assert {d.dimension for d in item.dimensions} == {
            "star_completeness",
            "specificity",
            "quantified_outcome",
            "ownership_language",
        }
        assert item.ideal.has_material is True
    assert not hasattr(report, "total")

    # 1 plan + 5 score + 5 ideal, all tagged with the session id. Asking is a
    # fixed lead-in plus the planned question, so it makes no call (ADR 0028).
    calls = [c["call"] for c in fake.calls]
    assert calls.count("plan") == 1 and calls.count("ask") == 0
    assert calls.count("score") == 5 and calls.count("ideal") == 5
    assert {c["session_id"] for c in fake.calls} == {"sess-0001"}


def test_ask_opens_with_a_fixed_line_then_the_planned_question(setup):
    session = engine.start(setup, session_id="sess-0001", model=FakeModel())
    first = "".join(engine.ask(session, spoken=True))
    assert first == f"{OPENER} {session.questions[0].text}"

    answered = engine.submit_answer(session, Answer(question_id=1, text="my answer"))
    said = "".join(engine.ask(answered, spoken=True))
    assert said.endswith(answered.questions[1].text) and said.split()[0] in {
        "Thank",
        "Thanks",
        "Okay,",
        "Got",
    }


@pytest.mark.parametrize(
    "answer",
    [
        Answer(question_id=1, text="I was halfway through", cut_off=True),
        Answer(question_id=1, text=NO_ANSWER),
    ],
)
def test_after_a_cut_in_there_is_no_thank_you(setup, answer):
    session = engine.start(setup, session_id="sess-0001", model=FakeModel())
    session = engine.submit_answer(session, answer)
    # Spoken, her "let's move on" interjection already said it.
    assert "".join(engine.ask(session, spoken=True)) == session.questions[1].text
    # On screen, the words are needed.
    assert (
        "".join(engine.ask(session, spoken=False)) == f"Let's move on. {session.questions[1].text}"
    )


def test_answer_for_wrong_question_is_rejected(setup):
    session = engine.start(setup, session_id="sess-0001", model=FakeModel())
    with pytest.raises(EngineError) as exc:
        engine.submit_answer(session, Answer(question_id=3, text="x"))
    assert exc.value.status == 409


def test_finish_before_wrap_is_rejected(setup):
    session = engine.start(setup, session_id="sess-0001", model=FakeModel())
    with pytest.raises(EngineError):
        engine.finish(session, model=FakeModel())


def test_ask_after_wrap_is_rejected(setup):
    session, _ = _walk(setup, FakeModel())
    with pytest.raises(EngineError):
        list(engine.ask(session))


def test_malformed_plan_is_a_502(setup):
    fake = FakeModel(
        {"plan": {"questions": [{"text": "q", "competency": "c", "rationale": "r"}] * 4}}
    )
    with pytest.raises(EngineError) as exc:
        engine.start(setup, session_id="sess-0001", model=fake)
    assert exc.value.status == 502


def test_model_failure_propagates_as_model_error(setup):
    fake = FakeModel(fail="score")
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i in range(5):
        session = engine.submit_answer(session, Answer(question_id=i + 1, text="a"))
    with pytest.raises(ModelError):
        engine.finish(session, model=fake)


def test_session_round_trips_through_json(setup):
    """The browser holds the session between requests, so it must survive JSON."""
    session = engine.start(setup, session_id="sess-0001", model=FakeModel())
    again = Session.model_validate_json(session.model_dump_json())
    assert again == session


def test_finish_scores_answers_concurrently(setup):
    """Ten model calls that each take 0.2s must not take 2s end to end — nor
    0.4s, which is what running each answer's score and ideal in turn costs."""
    import time

    class SlowFake(FakeModel):
        def generate(self, **kwargs):
            time.sleep(0.2)
            return super().generate(**kwargs)

    fake = SlowFake()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i in range(5):
        session = engine.submit_answer(session, Answer(question_id=i + 1, text="a"))
    started = time.monotonic()
    report = engine.finish(session, model=fake)
    elapsed = time.monotonic() - started
    assert [item.question.id for item in report.items] == [1, 2, 3, 4, 5]
    assert elapsed < 0.35, f"took {elapsed:.2f}s — scoring is not concurrent"


def test_score_as_ready_yields_each_answer_as_it_finishes(setup):
    """Question 1 is slow on purpose: the other four must come out first, each
    tagged with its own position so the caller can put it back in place."""
    import time

    class Q1IsSlow(FakeModel):
        def generate(self, **kwargs):
            if "answer one" in kwargs["user"]:
                time.sleep(0.3)
            return super().generate(**kwargs)

    fake = Q1IsSlow()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i, text in enumerate(["answer one", "b", "c", "d", "e"]):
        session = engine.submit_answer(session, Answer(question_id=i + 1, text=text))
    header = engine.begin_scoring(session)
    assert header.items == []
    order = [(i, item.question.id) for i, item in engine.score_as_ready(session, model=fake)]
    assert order[-1] == (0, 1)
    assert sorted(order) == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]


def test_the_reports_calls_may_fall_back_and_others_may_not(setup):
    # ADR 0039: score and ideal fail fast and fall back; planning does not.
    fake = FakeModel()
    session, _ = _walk(setup, fake)
    by_call = {}
    for call in fake.calls:
        by_call.setdefault(call["call"], set()).add(call.get("fallback", False))
    assert by_call["score"] == {True} and by_call["ideal"] == {True}
    assert by_call["plan"] == {False}
