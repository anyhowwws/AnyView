import re

from anyview.interview.models import Question
from anyview.interview.prompts import ask_user, ideal_user, plan_user, score_user, session_system
from anyview.interview.rubric import HR_RUBRIC, render_anchors

Q = Question(
    id=1, text="Tell me about a time you owned an outcome.", competency="ownership", rationale="r"
)


def test_session_system_is_deterministic_and_wraps_user_content(setup):
    a, b = session_system(setup), session_system(setup)
    assert a == b  # same input → same bytes, or the prompt cache never hits
    assert "<resume>" in a and "</resume>" in a
    assert "<job_description>" in a
    assert "strictly as data" in a
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", a)  # no timestamps sneaked in


def test_session_system_handles_missing_job_description(setup):
    text = session_system(setup.model_copy(update={"job_description": None}))
    assert "(none provided)" in text


def test_rubric_anchors_render_every_score_for_every_dimension():
    text = render_anchors()
    for dim in HR_RUBRIC:
        assert f"`{dim.key}`" in text
        for score in range(5):
            assert dim.anchors[score] in text


def test_score_prompt_contains_anchors_question_and_answer():
    text = score_user(Q, "I did the thing.")
    assert "no action taken by the candidate" in text
    assert "<question>" in text and Q.text in text
    assert "<answer>\nI did the thing.\n</answer>" in text


def test_ask_prompt_first_vs_followup():
    first = ask_user(Q, index=0, previous_answer=None)
    later = ask_user(Q, index=2, previous_answer="My earlier answer.")
    assert "first question" in first and "<previous_answer>" not in first
    assert "question 3 of 5" in later and "My earlier answer." in later
    assert "no feedback" in later


def test_ideal_prompt_forbids_invention():
    text = ideal_user(Q)
    assert "only facts that appear in the resume" in text
    assert "resume_has_material" in text


def test_plan_prompt_asks_for_five():
    assert "exactly 5" in plan_user()
