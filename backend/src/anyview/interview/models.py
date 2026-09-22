"""Pydantic models for everything that crosses the API boundary.

Phase 0 is stateless: the browser holds a `Session` and posts it back on every
turn, so these models are both the wire format and the engine's state. Field
limits are the input-size caps (a cost guard as much as a validation one).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, get_args

from pydantic import BaseModel, Field

QUESTION_COUNT = 5
MAX_PROBES = 0  # Phase 3 raises this to 2; the state exists now so the machine is complete.

Seniority = Literal["junior", "mid", "senior", "staff", "principal"]
SENIORITIES: tuple[str, ...] = get_args(Seniority)

# How much the interviewer knows, and therefore how far past the resume they
# can push (ADR 0014). Named for the room, because the room is the thing the
# level simulates: a screen reads the page in front of them, a panel has done
# its homework.
Difficulty = Literal["recruiter_screen", "hiring_manager", "panel"]
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
    """One interview's situation: a candidate, a job, and a room (ADR 0014).

    `resume` is what an interviewer would have received. `garden` is the
    candidate's confirmed Digital Garden — everything they know that the
    interviewer did not get — and is filled in only at the difficulty that
    lets the interviewer read it. Two fields, because they are two things;
    the old single slot with a `source` flag was one thing pretending."""

    resume: str = Field(min_length=50, max_length=15_000)
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    seniority: Seniority
    difficulty: Difficulty = "hiring_manager"
    job_description: str | None = Field(default=None, max_length=8_000)
    # The uploaded object the resume text was extracted from, when there is one.
    resume_object: str | None = None
    # The confirmed garden, rendered with [R1]/[P2]/[S3] labels the model can
    # cite. Present at `panel`, or whenever an ideal answer can be improved by
    # it — the report reads it even when the interviewer does not.
    garden: str | None = Field(default=None, max_length=20_000)


class SetupInput(BaseModel):
    """What the browser sends to start (ADR 0014).

    The resume is a property of the user, not a choice made per interview:
    send neither field and the resume on file is used. `resume_object`
    replaces it — that is what the form's "Replace" does — and `resume` is the
    same thing as already-extracted text, which the form does not offer but
    the API accepts so an interview can run with no database behind it."""

    resume: str | None = Field(default=None, max_length=15_000)
    resume_object: str | None = Field(default=None, max_length=200)
    company: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    seniority: Seniority
    difficulty: Difficulty = "hiring_manager"
    job_description: str | None = Field(default=None, max_length=8_000)


# --- The target job ----------------------------------------------------------


class JobParse(BaseModel):
    """What the model pulls out of an uploaded job description (ADR 0014).

    Every field is a suggestion: it pre-fills the same form the manual path
    fills in, and the user confirms it before anything reaches a prompt."""

    company: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    seniority: Seniority | None = None
    responsibilities: list[str] = []
    must_haves: list[str] = []
    nice_to_haves: list[str] = []


class JobDocument(BaseModel):
    """The parse, plus the text it came from. The browser keeps both: the text
    becomes `job_description`, the parse pre-fills the fields."""

    text: str
    parsed: JobParse


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
    # Lines from the resume, or garden entries by label ([S3]). Named for what
    # it is now that the report reads both (ADR 0014).
    cited_lines: list[str]
    has_material: bool


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
    # The room this was conducted in, which is what makes two attempts
    # comparable, and whether the garden was available to the answers.
    difficulty: Difficulty = "hiring_manager"
    garden_used: bool = False
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
        "cited_lines": {"type": "array", "items": {"type": "string"}},
        "has_material": {"type": "boolean"},
    },
    "required": ["answer", "cited_lines", "has_material"],
    "additionalProperties": False,
}

_STRINGS = {"type": "array", "items": {"type": "string"}}

JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {"type": ["string", "null"]},
        "role": {"type": ["string", "null"]},
        # Null is a legitimate answer: plenty of postings never state a level.
        "seniority": {"type": ["string", "null"], "enum": [*SENIORITIES, None]},
        "responsibilities": _STRINGS,
        "must_haves": _STRINGS,
        "nice_to_haves": _STRINGS,
    },
    "required": [
        "company",
        "role",
        "seniority",
        "responsibilities",
        "must_haves",
        "nice_to_haves",
    ],
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
