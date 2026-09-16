import pytest
from pydantic import ValidationError

from anyview.interview.models import (
    IDEAL_SCHEMA,
    PLAN_SCHEMA,
    SCORE_SCHEMA,
    Answer,
    PlanOutput,
    Report,
    ScoreOutput,
    Session,
    Setup,
)


def _walk_objects(schema):
    """Yield every object-typed node in a JSON schema."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _walk_objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _walk_objects(v)


@pytest.mark.parametrize("schema", [PLAN_SCHEMA, SCORE_SCHEMA, IDEAL_SCHEMA])
def test_output_schemas_are_closed_and_flat(schema):
    for node in _walk_objects(schema):
        assert node.get("additionalProperties") is False
        assert set(node["required"]) == set(node["properties"])
    assert "$defs" not in schema


def test_setup_enforces_size_caps(setup):
    with pytest.raises(ValidationError):
        Setup(**{**setup.model_dump(), "resume": "too short"})
    with pytest.raises(ValidationError):
        Setup(**{**setup.model_dump(), "resume": "x" * 15_001})
    with pytest.raises(ValidationError):
        Setup(**{**setup.model_dump(), "seniority": "guru"})
    with pytest.raises(ValidationError):
        Answer(question_id=1, text="")
    with pytest.raises(ValidationError):
        Answer(question_id=1, text="x" * 4_001)


def test_plan_output_requires_exactly_five_questions():
    item = {"text": "q", "competency": "c", "rationale": "r"}
    with pytest.raises(ValidationError):
        PlanOutput(questions=[item] * 4)
    assert len(PlanOutput(questions=[item] * 5).questions) == 5


def test_score_output_requires_exactly_four_dimensions():
    dim = {"dimension": "specificity", "score": 2, "evidence": "e"}
    with pytest.raises(ValidationError):
        ScoreOutput(dimensions=[dim] * 3, summary="s", gaps=[])
    with pytest.raises(ValidationError):
        ScoreOutput(dimensions=[{**dim, "score": 5}] * 4, summary="s", gaps=[])


def test_report_has_no_total_field():
    assert "total" not in Report.model_fields
    assert "score" not in Report.model_fields


def test_session_helpers(setup):
    s = Session(session_id="abcdefgh", setup=setup)
    assert s.current_question is None
    assert s.previous_answer is None
