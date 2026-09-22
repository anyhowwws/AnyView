import pytest

from anyview.interview import engine
from anyview.interview.engine import TRANSITIONS, EngineError
from anyview.interview.models import Answer, Session, State
from anyview.llm.adapter import ModelError
from anyview.llm.fake import FakeModel


def _walk(setup, fake):
    """Run a whole interview and return (session, report)."""
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i in range(5):
        text = "".join(engine.ask(session, model=fake))
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

    # 1 plan + 5 ask + 5 score + 5 ideal, all tagged with the session id
    calls = [c["call"] for c in fake.calls]
    assert calls.count("plan") == 1 and calls.count("ask") == 5
    assert calls.count("score") == 5 and calls.count("ideal") == 5
    assert {c["session_id"] for c in fake.calls} == {"sess-0001"}


def test_ask_uses_previous_answer_after_the_first_question(setup):
    fake = FakeModel()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    list(engine.ask(session, model=fake))
    assert "first question" in fake.calls[-1]["user"]
    session = engine.submit_answer(session, Answer(question_id=1, text="my first answer"))
    list(engine.ask(session, model=fake))
    assert "my first answer" in fake.calls[-1]["user"]


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
        list(engine.ask(session, model=FakeModel()))


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
    """Ten model calls that each take 0.2s must not take 2s end to end."""
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
    assert elapsed < 1.0, f"took {elapsed:.2f}s — scoring is not concurrent"
