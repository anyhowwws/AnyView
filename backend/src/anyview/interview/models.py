"""Pydantic models for everything that crosses the API boundary.

Phase 0 is stateless: the browser holds a `Session` and posts it back on every
turn, so these models are both the wire format and the engine's state. Field
limits are the input-size caps (a cost guard as much as a validation one).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

QUESTION_COUNT = 5
MAX_PROBES = 0  # Phase 3 raises this to 2; the state exists now so the machine is complete.

Seniority = Literal["junior", "mid", "senior", "staff", "principal"]
Dimension = Literal["star_completeness", "specificity", "quantified_outcome", "ownership_language"]


class State(StrEnum):
    """Every state in the brief's machine. Phase 0 never enters `probe`."""

    INTAKE = "intake"
    PLAN = "plan"
    ASK = "ask"
    ANSWER = "answer"
    PROBE = "probe"
    NEXT = "next"
    WRAP = "wrap"
    SCORE = "score"
    REPORT = "report"


class Setup(BaseModel):
    resume: str = Field(min_length=50, max_length=15_000)
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    seniority: Seniority
    job_description: str | None = Field(default=None, max_length=8_000)


class Question(BaseModel):
    id: int = Field(ge=1, le=QUESTION_COUNT)
    text: str
    competency: str
    rationale: str  # why this question, for this candidate — shown in the report


class Answer(BaseModel):
    question_id: int = Field(ge=1, le=QUESTION_COUNT)
    text: str = Field(min_length=1, max_length=4_000)


class Session(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    setup: Setup
    state: State = State.INTAKE
    questions: list[Question] = []
    answers: list[Answer] = []
    current: int = 0  # index into `questions` of the question being asked/answered

    @property
    def current_question(self) -> Question | None:
        if 0 <= self.current < len(self.questions):
            return self.questions[self.current]
        return None

    @property
    def previous_answer(self) -> Answer | None:
        return self.answers[-1] if self.answers else None


# --- Report ------------------------------------------------------------------


class DimensionScore(BaseModel):
    dimension: Dimension
    score: int = Field(ge=0, le=4)
    evidence: str


class IdealAnswer(BaseModel):
    answer: str
    cited_resume_lines: list[str]
    resume_has_material: bool


class QuestionReport(BaseModel):
    question: Question
    answer: str
    dimensions: list[DimensionScore] = Field(min_length=4, max_length=4)
    summary: str
    gaps: list[str]
    ideal: IdealAnswer


class Report(BaseModel):
    """Per-dimension scores only. There is deliberately no total field."""

    session_id: str
    company: str
    role: str
    seniority: Seniority
    items: list[QuestionReport]


# --- What the model must return ---------------------------------------------
# Hand-written JSON schemas for structured output. They mirror the Pydantic
# models above but stay flat (no $defs) and closed (additionalProperties: false),
# which is what the API's json_schema format wants. The model's reply is then
# validated *again* through the Pydantic model, so both layers agree.

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "competency": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["text", "competency", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": [
                            "star_completeness",
                            "specificity",
                            "quantified_outcome",
                            "ownership_language",
                        ],
                    },
                    "score": {"type": "integer", "enum": [0, 1, 2, 3, 4]},
                    "evidence": {"type": "string"},
                },
                "required": ["dimension", "score", "evidence"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["dimensions", "summary", "gaps"],
    "additionalProperties": False,
}

IDEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "cited_resume_lines": {"type": "array", "items": {"type": "string"}},
        "resume_has_material": {"type": "boolean"},
    },
    "required": ["answer", "cited_resume_lines", "resume_has_material"],
    "additionalProperties": False,
}


class PlanOutput(BaseModel):
    class Item(BaseModel):
        text: str
        competency: str
        rationale: str

    questions: list[Item] = Field(min_length=QUESTION_COUNT, max_length=QUESTION_COUNT)


class ScoreOutput(BaseModel):
    dimensions: list[DimensionScore] = Field(min_length=4, max_length=4)
    summary: str
    gaps: list[str]
