"""Time-bounded interviews and the opener (ADR 0016)."""

import pytest
from fastapi.testclient import TestClient

from anyview.api import interview
from anyview.interview import engine
from anyview.interview.models import (
    DEFAULT_ANSWER_SECONDS,
    MAX_ANSWER_SECONDS,
    MIN_ANSWER_SECONDS,
    QUESTION_COUNT,
    Question,
    Setup,
)
from anyview.llm.fake import FakeModel, default_plan
from anyview.main import app
from tests.conftest import RESUME


@pytest.fixture
def client(signed_in, store):
    model = FakeModel()
    app.dependency_overrides[interview.get_model] = lambda: model
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(interview.get_model, None)


def test_a_question_carries_its_own_clock(setup):
    session = engine.start(setup, session_id="session-1", model=FakeModel())
    assert len(session.questions) == QUESTION_COUNT
    assert all(45 <= q.seconds <= 300 for q in session.questions)


def test_the_opener_gets_less_time_than_a_story(setup):
    session = engine.start(setup, session_id="session-1", model=FakeModel())
    opener, *rest = session.questions
    assert opener.seconds < min(q.seconds for q in rest)


def test_a_plan_without_seconds_still_loads():
    # An older saved session, or a model that omits the field: the question
    # takes the default clock rather than failing to parse.
    q = Question(id=1, text="Tell me about yourself.", competency="background", rationale="why")
    assert q.seconds == DEFAULT_ANSWER_SECONDS


@pytest.mark.parametrize("seconds", [44, 301])
def test_an_unreasonable_clock_is_rejected(seconds):
    with pytest.raises(ValueError):
        Question(id=1, text="t", competency="c", rationale="r", seconds=seconds)


@pytest.mark.parametrize(
    ("asked", "given"), [(20, MIN_ANSWER_SECONDS), (1200, MAX_ANSWER_SECONDS), (90, 90)]
)
def test_a_stray_clock_from_the_model_is_clamped_not_fatal(setup, asked, given):
    # One odd number must cost that question its clock, not fail the interview.
    plan = default_plan(QUESTION_COUNT)
    for item in plan["questions"]:
        item["seconds"] = asked
    session = engine.start(setup, session_id="session-1", model=FakeModel({"plan": plan}))
    assert {q.seconds for q in session.questions} == {given}


def test_time_bounded_is_off_unless_asked_for(setup):
    assert setup.time_bounded is False


def test_time_bounded_rides_on_the_setup(setup):
    timed = Setup(**{**setup.model_dump(), "time_bounded": True})
    session = engine.start(timed, session_id="session-1", model=FakeModel())
    assert session.setup.time_bounded is True


def test_the_plan_prompt_asks_for_an_opener_and_a_clock(setup):
    model = FakeModel()
    engine.start(setup, session_id="session-1", model=model)
    planned = next(c for c in model.calls if c["call"] == "plan")["user"]
    assert "tell me about" in planned.lower()
    assert "`seconds`" in planned


def test_the_clock_survives_the_trip_through_the_start_route(client, store):
    # SetupInput -> Setup is a field-by-field copy, which is exactly the kind of
    # mapping a new field falls out of.
    r = client.post(
        "/interview/start",
        json={
            "session_id": "session-timed",
            "setup": {
                "resume": RESUME,
                "company": "Initech",
                "role": "Cloud Architect",
                "seniority": "senior",
                "time_bounded": True,
            },
        },
        headers={"Authorization": "Bearer good"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["setup"]["time_bounded"] is True


def test_the_clock_is_off_when_the_browser_does_not_ask_for_it(client, store):
    r = client.post(
        "/interview/start",
        json={
            "session_id": "session-untimed",
            "setup": {
                "resume": RESUME,
                "company": "Initech",
                "role": "Cloud Architect",
                "seniority": "senior",
            },
        },
        headers={"Authorization": "Bearer good"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["setup"]["time_bounded"] is False
