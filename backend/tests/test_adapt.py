"""Adaptive planning between questions (ADR 0036): the planner may reword the
next question and keeps the carry-over note, inside limits the server sets."""

import time

import pytest

from anyview.interview import engine
from anyview.interview.live import LiveTurn
from anyview.interview.models import MAX_NOTES_CHARS, NO_ANSWER, Answer, FollowUp, State
from anyview.interview.prompts import adapt_user
from anyview.llm.fake import FakeModel


def _after_first(setup, fake, text="I led the billing migration to Cloud Run."):
    session = engine.start(setup, session_id="sess-0001", model=fake)
    return engine.submit_answer(session, Answer(question_id=1, text=text))


def _rewrite(text="Tell me about a time you owned something nobody asked you to.", **extra):
    return {
        "notes": "Led the billing migration to Cloud Run.",
        "rewrite": True,
        "text": text,
        "rationale": "They already covered the migration.",
        **extra,
    }


def test_a_rewrite_changes_only_the_next_questions_wording(setup):
    fake = FakeModel({"adapt": _rewrite()})
    before = _after_first(setup, fake)
    after = engine.adapt(before, model=fake)

    old, new = before.questions[1], after.questions[1]
    assert new.text == "Tell me about a time you owned something nobody asked you to."
    assert new.planned == old.text
    assert (new.id, new.competency, new.seconds) == (old.id, old.competency, old.seconds)
    assert after.questions[2:] == before.questions[2:]
    assert len(after.questions) == len(before.questions)
    assert after.notes == "Led the billing migration to Cloud Run."
    assert after.state == State.ASK and after.current == 1
    assert fake.calls[-1]["call"] == "adapt" and fake.calls[-1]["fast"]


def test_keeping_the_question_still_updates_the_note(setup):
    fake = FakeModel()
    before = _after_first(setup, fake)
    after = engine.adapt(before, model=fake)
    assert after.questions == before.questions
    assert after.questions[1].planned is None
    assert after.notes.startswith("Scripted by FakeModel")


def test_a_second_rewrite_keeps_the_first_plan(setup):
    fake = FakeModel({"adapt": _rewrite()})
    once = engine.adapt(_after_first(setup, fake), model=fake)
    fake.replies["adapt"] = _rewrite("Something else entirely?")
    twice = engine.adapt(once, model=fake)
    assert twice.questions[1].text == "Something else entirely?"
    assert twice.questions[1].planned == once.questions[1].planned


@pytest.mark.parametrize("text", ["", "   "])
def test_an_empty_rewrite_asks_as_planned(setup, text):
    fake = FakeModel({"adapt": _rewrite(text)})
    before = _after_first(setup, fake)
    after = engine.adapt(before, model=fake)
    assert after.questions == before.questions
    assert after.notes  # the note is still worth keeping


def test_overlong_output_is_trimmed_not_refused(setup):
    fake = FakeModel({"adapt": _rewrite("word " * 200, notes="line of notes\n" * 400)})
    after = engine.adapt(_after_first(setup, fake), model=fake)
    assert len(after.questions[1].text) <= 400
    assert len(after.notes) <= MAX_NOTES_CHARS
    # The trimmed session is still one the browser can post back.
    engine.submit_answer(after, Answer(question_id=2, text="x"))


def test_a_failed_planner_leaves_the_session_alone(setup):
    fake = FakeModel(fail="adapt")
    before = _after_first(setup, fake)
    assert engine.adapt(before, model=fake) == before


def test_a_malformed_reply_leaves_the_session_alone(setup):
    fake = FakeModel({"adapt": {"rewrite": "maybe"}})
    before = _after_first(setup, fake)
    assert engine.adapt(before, model=fake) == before


def test_a_slow_planner_is_not_waited_for(setup):
    fake = FakeModel()
    before = _after_first(setup, fake)
    fake.delay = 0.5
    started = time.monotonic()
    assert engine.adapt(before, model=fake, deadline=0.05) == before
    assert time.monotonic() - started < 0.4


def test_no_call_after_silence(setup):
    fake = FakeModel()
    before = _after_first(setup, fake, text=NO_ANSWER)
    calls = len(fake.calls)
    assert engine.adapt(before, model=fake) == before
    assert len(fake.calls) == calls


def test_adapt_needs_a_session_between_questions(setup):
    fake = FakeModel()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    assert engine.adapt(session, model=fake) == session  # nothing answered yet
    for i in range(5):
        session = engine.submit_answer(session, Answer(question_id=i + 1, text="x"))
    with pytest.raises(engine.EngineError):
        engine.adapt(session, model=fake)  # wrap: no next question


# --- What the planner and Harvey read ------------------------------------------


def test_the_planner_reads_the_whole_exchange_and_the_note(setup):
    fake = FakeModel()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    session = engine.submit_answer(
        session,
        Answer(
            question_id=1,
            text="I run platform at Acme.",
            follow_ups=[FollowUp(question="What changed?", answer="MTTR fell to 50m.")],
        ),
    )
    session = session.model_copy(update={"notes": "Runs platform at Acme."})
    text = adapt_user(
        session.setup, questions=session.questions, answers=session.answers, notes=session.notes
    )
    assert "I run platform at Acme." in text and "MTTR fell to 50m." in text
    assert "Runs platform at Acme." in text
    assert session.questions[1].text in text
    assert f"`{session.questions[1].competency}`" in text


def test_harvey_reads_the_note_instead_of_old_excerpts(setup):
    fake = FakeModel()
    session = engine.start(setup, session_id="sess-0001", model=fake)
    for i in range(2):
        session = engine.submit_answer(session, Answer(question_id=i + 1, text=f"answer {i + 1}"))
    without = LiveTurn(session).system
    assert "They said: answer 1" in without

    noted = LiveTurn(session.model_copy(update={"notes": "Led the billing migration."})).system
    assert "<notes>\nLed the billing migration.\n</notes>" in noted
    assert "They said: answer 2" in noted  # the last answer, for the bridge
    assert "They said: answer 1" not in noted
