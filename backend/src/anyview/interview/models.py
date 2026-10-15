"""Pydantic models for everything that crosses the API boundary.

Phase 0 is stateless: the browser holds a `Session` and posts it back on every
turn, so these models are both the wire format and the engine's state. Field
limits are the input-size caps (a cost guard as much as a validation one).
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field

QUESTION_COUNT = 5
# Follow-up questions Harvey may ask on one question, in a spoken interview on
# Gemini Live (ADR 0031). He asks for each one through a tool; the API says no
# once the budget is spent. Typed answers have no follow-ups.
MAX_PROBES = 2

# The clock for one answer when the model does not say otherwise, the range it
# is held to, and the pause that counts as an awkward silence rather than a
# thought (ADR 0016).
DEFAULT_ANSWER_SECONDS = 120
MIN_ANSWER_SECONDS = 45
MAX_ANSWER_SECONDS = 300
DEAD_AIR_SECONDS = 10

# Adaptive planning (ADR 0036): between questions, one fast call may reword the
# next question and keeps a short note of what the candidate has said so far.
# These bound what comes back, whatever the model writes.
MAX_QUESTION_CHARS = 400
MAX_NOTES_CHARS = 1_200

# The browser's id for one interview. It names the usage rows and log lines of
# every call made for it, so it is bounded wherever it comes in, not only
# once it reaches a Session.
SessionId = Annotated[str, Field(min_length=8, max_length=64)]

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
    # Whether the clock runs (ADR 0016). Defaults off so a session saved by an
    # older build does not suddenly acquire a countdown mid-interview; the form
    # starts it on, because a real interview has a schedule.
    time_bounded: bool = False
    job_description: str | None = Field(default=None, max_length=8_000)
    # The uploaded object the resume text was extracted from, when there is one.
    resume_object: str | None = None
    # The confirmed garden, rendered with [R1]/[P2]/[S3] labels the model can
    # cite. Present at `panel`, or whenever an ideal answer can be improved by
    # it — the report reads it even when the interviewer does not.
    garden: str | None = Field(default=None, max_length=20_000)
    # One line per garden entry (`Repository.brain_index`), set beside `garden`
    # at Panel. On Live, Harvey reads this instead of the whole garden and looks
    # entries up by label through `ask_follow_up` (ADR 0037).
    garden_index: str | None = Field(default=None, max_length=12_000)


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
    time_bounded: bool = False
    job_description: str | None = Field(default=None, max_length=8_000)
    # How the job was described, so it can be saved for next time (ADR 0025).
    # Optional: an interview runs the same without it, it just is not remembered.
    job: JobInput | None = None


# --- The target job ----------------------------------------------------------


class JobFields(BaseModel):
    """The setup form's structured job fields, one item per line, exactly as
    the form holds them. Stored as-is so a saved job reloads into the form."""

    team: str = Field(default="", max_length=200)
    responsibilities: str = Field(default="", max_length=4_000)
    must_haves: str = Field(default="", max_length=4_000)
    nice_to_haves: str = Field(default="", max_length=4_000)


class JobInput(BaseModel):
    """Which saved job this interview is for, if any, and how it was filled in.

    `id` set: the user picked a saved job, and any change they made to its
    fields is written back to it. `id` empty: a new job, saved on start unless
    it matches one already saved (ADR 0025)."""

    id: str | None = Field(default=None, max_length=36)
    source: Literal["upload", "manual"]
    fields: JobFields = JobFields()


class SavedJob(BaseModel):
    """A target job kept for the next practice run (ADR 0025)."""

    id: str
    company: str
    role: str
    seniority: Seniority
    source: Literal["upload", "manual"]
    job_description: str | None
    fields: JobFields
    created_at: dt.datetime
    last_used_at: dt.datetime


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
    # Set when this exact posting is already saved: the form switches to it,
    # with whatever corrections the user made last time, and no parse call ran.
    saved_job: SavedJob | None = None


class Question(BaseModel):
    id: int = Field(ge=1, le=QUESTION_COUNT)
    text: str
    competency: str
    rationale: str  # why this question, for this candidate — shown in the report
    # How long a strong answer to *this* question needs, decided by the model
    # when it plans (ADR 0016). An opener is not a failure story; giving every
    # question the same clock would be the wrong kind of realism. Only used
    # when the interview is time-bounded.
    seconds: int = Field(
        default=DEFAULT_ANSWER_SECONDS, ge=MIN_ANSWER_SECONDS, le=MAX_ANSWER_SECONDS
    )
    # The wording planned at the start, kept when adaptive planning rewrote
    # `text` after an earlier answer (ADR 0036). None: asked as planned.
    planned: str | None = None


# What the browser records when the clock runs out on silence (ADR 0016).
NO_ANSWER = "(no answer given)"

# A spoken answer is a transcript, and five minutes of talking runs past what
# anyone types. Typed answers keep the form's 4,000.
MAX_ANSWER_CHARS = 8_000


class FollowUp(BaseModel):
    """One follow-up Harvey asked during a spoken answer, and what the candidate
    said to it (ADR 0031). Scored with the answer it followed, as one exchange."""

    question: str = Field(min_length=1, max_length=1_000)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


class Answer(BaseModel):
    question_id: int = Field(ge=1, le=QUESTION_COUNT)
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    # The clock or Harvey ended this answer, not the candidate. The next question
    # then opens without a "thank you" for an answer that had to be cut short (ADR 0028).
    cut_off: bool = False
    # Follow-ups asked in a Live interview, in order. At most MAX_PROBES.
    follow_ups: list[FollowUp] = Field(default=[], max_length=MAX_PROBES)


class Session(BaseModel):
    session_id: SessionId
    setup: Setup
    state: State = State.INTAKE
    questions: list[Question] = []
    answers: list[Answer] = []
    current: int = 0  # index into `questions` of the question being asked/answered
    # The carry-over note (ADR 0036): what the candidate has said so far, in a few
    # lines, rewritten after each answer. Harvey reads it on Live, so a later
    # question can refer back to an earlier one. Facts only, never a judgement.
    notes: str = Field(default="", max_length=MAX_NOTES_CHARS)

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
    follow_ups: list[FollowUp] = []
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
                    "seconds": {"type": "integer"},
                },
                "required": ["text", "competency", "rationale", "seconds"],
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

ADAPT_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {"type": "string"},
        "rewrite": {"type": "boolean"},
        "text": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["notes", "rewrite", "text", "rationale"],
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
        # Deliberately unconstrained here; `engine.start` clamps it into
        # `Question`'s range. A model asking for twenty minutes on one question
        # should cost that question its clock, not the whole interview a retry.
        seconds: int = DEFAULT_ANSWER_SECONDS

    questions: list[Item] = Field(min_length=QUESTION_COUNT, max_length=QUESTION_COUNT)


class AdaptOutput(BaseModel):
    """What the planner returns between questions (ADR 0036). Unbounded here on
    purpose: `engine.adapt` trims and checks it, so an overlong note costs the
    note its tail, not the interview its next question."""

    notes: str
    rewrite: bool
    text: str = ""
    rationale: str = ""


class ScoreOutput(BaseModel):
    dimensions: list[DimensionScore] = Field(min_length=4, max_length=4)
    summary: str
    gaps: list[str]
