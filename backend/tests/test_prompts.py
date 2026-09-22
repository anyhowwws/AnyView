import re

from anyview.interview.models import Question
from anyview.interview.prompts import (
    JOB_PARSE_SYSTEM,
    ask_user,
    ideal_user,
    job_parse_user,
    plan_user,
    score_user,
    session_system,
)
from anyview.interview.rubric import HR_RUBRIC, render_anchors

Q = Question(
    id=1, text="Tell me about a time you owned an outcome.", competency="ownership", rationale="r"
)

GARDEN = """## [R1] Senior Cloud Architect at Acme Corp (2021–present)
## Stories
[S1] On-call rota redesign after two Sev-1s (competencies: ownership, failure)
  Result: MTTR dropped from 4h to 50m"""


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


def test_ideal_prompt_forbids_invention(setup):
    text = ideal_user(Q, setup)
    assert "only facts that appear in the resume" in text
    assert "has_material" in text


def test_plan_prompt_asks_for_five(setup):
    assert "exactly 5" in plan_user(setup)


# --- Difficulty decides what the interviewer knows (ADR 0014) ----------------


def test_the_garden_reaches_the_system_prompt_only_at_panel(setup):
    with_garden = setup.model_copy(update={"garden": GARDEN})
    for level in ("recruiter_screen", "hiring_manager"):
        text = session_system(with_garden.model_copy(update={"difficulty": level}))
        assert "<digital_garden>" not in text
        assert "On-call rota redesign" not in text
    panel = session_system(with_garden.model_copy(update={"difficulty": "panel"}))
    assert "<digital_garden>" in panel and "On-call rota redesign" in panel
    assert "done your homework" in panel


def test_each_difficulty_states_its_own_scope(setup):
    screen = session_system(setup.model_copy(update={"difficulty": "recruiter_screen"}))
    manager = session_system(setup.model_copy(update={"difficulty": "hiring_manager"}))
    assert "answerable from the page in front of you" in screen
    assert "never to ask about something the resume\ndoes not evidence" in screen
    assert "does not\nevidence" in manager  # the gap is what a hiring manager probes
    assert "recruiter" not in manager.lower()


def test_the_report_reads_the_garden_at_every_difficulty(setup):
    """The ideal answer is coaching, not simulation. Below panel the garden
    rides in the user turn, where it cannot reach the questions; at panel it is
    already in the cached system text and must not be sent twice."""
    with_garden = setup.model_copy(update={"garden": GARDEN})
    below = ideal_user(Q, with_garden.model_copy(update={"difficulty": "hiring_manager"}))
    assert "<digital_garden>" in below and "the resume and the Digital Garden" in below
    panel = ideal_user(Q, with_garden.model_copy(update={"difficulty": "panel"}))
    assert "<digital_garden>" not in panel
    assert ideal_user(Q, setup).count("<digital_garden>") == 0  # no garden, no block


def test_a_panel_with_an_empty_garden_never_names_one(setup):
    """Nothing to have read is still a panel — but pointing the model at a
    section that is not in the prompt would invite it to invent one."""
    panel = setup.model_copy(update={"difficulty": "panel", "garden": None})
    system, plan = session_system(panel), plan_user(panel)
    assert "<digital_garden>" not in system and "<digital_garden>" not in plan
    assert "no record beyond their CV" in system
    assert "only facts that appear in the resume" in ideal_user(Q, panel)


def test_job_parse_prompt_allows_a_missing_level():
    assert "return null" in JOB_PARSE_SYSTEM
    assert "junior, mid, senior, staff, principal" in JOB_PARSE_SYSTEM
    body = job_parse_user("Staff Engineer, Initech. Must have Terraform.")
    assert "<job_description>" in body and "Must have Terraform." in body
