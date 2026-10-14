"""Shapes of the brain (ADR 0002).

Three layers, from the model to the database:

  Patch (drafts)   — what the model proposes from one dump. Entities carry a
                     temporary `key` ("r1", "p2") so they can reference each
                     other before they have ids, or an `existing` label
                     ("R3") when the dump updates something already in the
                     brain. Every draft carries `evidence`: the verbatim
                     quote from the dump that justifies it.
  ConfirmedPatch   — the same after the user reviewed it. Same shape; the
                     user may have edited fields or dropped drafts.
  Event payload    — fully resolved: real UUIDs everywhere, no keys, no
                     labels. This is what replay applies.

Labels ("R1", "P3", "S2") are the short handles prompts use; they are
computed per user from the projection, never stored.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

EntityKind = Literal[
    "role", "project", "story", "skill", "achievement", "education", "language", "feedback"
]
KINDS: tuple[EntityKind, ...] = (
    "role",
    "project",
    "story",
    "skill",
    "achievement",
    "education",
    "language",
    "feedback",
)
LABEL_PREFIX: dict[EntityKind, str] = {
    "role": "R",
    "project": "P",
    "story": "S",
    "skill": "K",
    "achievement": "A",
    "education": "E",
    "language": "L",
    "feedback": "F",
}


# --- Drafts: what the model proposes ---------------------------------------


class Draft(BaseModel):
    key: str = Field(min_length=1, max_length=8)  # temp handle within the patch
    existing: str | None = None  # label of the entity this updates, e.g. "R2"
    evidence: str = Field(min_length=1, max_length=1000)
    # True when `evidence` could not be found in the dump (ADR 0019). The draft
    # is kept for the user to judge instead of being dropped unseen.
    unverified: bool = False


class RoleDraft(Draft):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    level: str | None = Field(default=None, max_length=80)
    # Ongoing work in the role; bounded work is a project (ADR 0019).
    responsibilities: list[str] = []


class ProjectDraft(Draft):
    role: str | None = None  # a role draft key ("r1") or an existing label ("R2")
    name: str = Field(min_length=1, max_length=200)
    problem: str | None = None
    action: str | None = None
    result: str | None = None
    tech: list[str] = []
    metrics: list[str] = []


class StoryDraft(Draft):
    role: str | None = None
    project: str | None = None
    title: str = Field(min_length=1, max_length=200)
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    competencies: list[str] = []


class SkillDraft(Draft):
    name: str = Field(min_length=1, max_length=100)
    depth: int = Field(ge=1, le=5)
    projects: list[str] = []  # evidence: project keys or labels
    roles: list[str] = []  # evidence: role keys or labels (ADR 0019)
    achievements: list[str] = []  # credentials that evidence it: keys or labels (ADR 0020)
    # Link target (key or label) -> the verbatim quote that justified the link.
    # Shown in the review queue; not stored on confirmation.
    link_evidence: dict[str, str] = {}
    # Other names this skill was found under and folded into it (ADR 0021):
    # "GCP" into "Google Cloud". Shown in the review queue; not stored.
    merged_from: list[str] = []


class AchievementDraft(Draft):
    kind: Literal["achievement", "credential"] = "achievement"
    title: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    achieved_on: dt.date | None = None


class EducationDraft(Draft):
    institution: str = Field(min_length=1, max_length=200)
    qualification: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start_date: dt.date | None = None
    end_date: dt.date | None = None


class LanguageDraft(Draft):
    name: str = Field(min_length=1, max_length=100)
    proficiency: str | None = Field(default=None, max_length=100)


class FeedbackDraft(Draft):
    role: str | None = None  # a role draft key ("r1") or an existing label ("R2")
    project: str | None = None
    given_by: str = Field(min_length=1, max_length=200)  # who said it, or where it came from
    content: str = Field(min_length=1, max_length=2000)  # the feedback itself, verbatim or close
    received_on: dt.date | None = None


class Patch(BaseModel):
    roles: list[RoleDraft] = []
    projects: list[ProjectDraft] = []
    stories: list[StoryDraft] = []
    skills: list[SkillDraft] = []
    achievements: list[AchievementDraft] = []
    education: list[EducationDraft] = []
    languages: list[LanguageDraft] = []
    feedback: list[FeedbackDraft] = []

    def is_empty(self) -> bool:
        return not (
            self.roles
            or self.projects
            or self.stories
            or self.skills
            or self.achievements
            or self.education
            or self.languages
            or self.feedback
        )


# --- The brain as the app reads it ------------------------------------------


class Provenance(BaseModel):
    raw_dump_id: str
    event_id: int


class Role(BaseModel):
    id: str
    label: str
    company: str
    title: str
    start_date: dt.date | None
    end_date: dt.date | None
    level: str | None
    responsibilities: list[str] = []
    source: Provenance


class Project(BaseModel):
    id: str
    label: str
    role_id: str | None
    name: str
    problem: str | None
    action: str | None
    result: str | None
    tech: list[str]
    metrics: list[str]
    source: Provenance


class Story(BaseModel):
    id: str
    label: str
    role_id: str | None
    project_id: str | None
    title: str
    situation: str | None
    task: str | None
    action: str | None
    result: str | None
    competencies: list[str]
    source: Provenance


class Skill(BaseModel):
    id: str
    label: str
    name: str
    depth: int
    project_ids: list[str]
    role_ids: list[str] = []
    achievement_ids: list[str] = []
    source: Provenance


class Achievement(BaseModel):
    id: str
    label: str
    kind: Literal["achievement", "credential"]
    title: str
    issuer: str | None
    achieved_on: dt.date | None
    source: Provenance


class Education(BaseModel):
    id: str
    label: str
    institution: str
    qualification: str | None
    field: str | None
    start_date: dt.date | None
    end_date: dt.date | None
    source: Provenance


class Language(BaseModel):
    id: str
    label: str
    name: str
    proficiency: str | None
    source: Provenance


class Feedback(BaseModel):
    id: str
    label: str
    role_id: str | None
    project_id: str | None
    given_by: str
    content: str
    received_on: dt.date | None
    source: Provenance


class Competency(BaseModel):
    key: str
    label: str


Strength = Literal["none", "weak", "strong"]


class Coverage(BaseModel):
    """competency × role → evidence strength. `cells[competency][role_id]`;
    the role id "other" collects stories with no role."""

    competencies: list[Competency]
    roles: list[Role]
    cells: dict[str, dict[str, Strength]]


class Brain(BaseModel):
    roles: list[Role]
    projects: list[Project]
    stories: list[Story]
    skills: list[Skill]
    achievements: list[Achievement]
    education: list[Education]
    languages: list[Language]
    feedback: list[Feedback]
    coverage: Coverage
    pending_proposals: int


class RawDump(BaseModel):
    id: str
    kind: Literal["text", "resume_pdf", "resume_docx"]
    text: str
    object_name: str | None
    created_at: dt.datetime


class Proposal(BaseModel):
    id: str
    raw_dump_id: str
    status: Literal["pending", "confirmed", "discarded"]
    patch: Patch
    model: str
    created_at: dt.datetime
    resolved_at: dt.datetime | None
    # Filled in for the queue so it can name the source without sending its text.
    dump_kind: Literal["text", "resume_pdf", "resume_docx"] | None = None


JobStatus = Literal["queued", "running", "done", "failed"]


class IngestJob(BaseModel):
    """One dump on its way to a proposal (ADR 0034). The browser polls this;
    the worker Cloud Tasks calls writes it."""

    id: str
    source: Literal["text", "upload"]
    status: JobStatus
    # The `progress` frames so far (ADR 0019's shapes), oldest first.
    progress: list[dict] = Field(default_factory=list)
    attempts: int = 0
    error: str | None = None
    error_status: int | None = None
    # Filled in once the job is done, so the browser needs no second request.
    proposal: Proposal | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class Event(BaseModel):
    id: int
    seq: int
    kind: Literal["patch_confirmed", "entity_edited", "entity_retired"]
    payload: dict
    raw_dump_id: str | None
    proposal_id: str | None
    created_at: dt.datetime


# Fields a user may edit in place, per kind. Anything else is refused.
EDITABLE: dict[EntityKind, frozenset[str]] = {
    "role": frozenset({"company", "title", "start_date", "end_date", "level", "responsibilities"}),
    "project": frozenset({"name", "problem", "action", "result", "tech", "metrics", "role_id"}),
    "story": frozenset(
        {"title", "situation", "task", "action", "result", "competencies", "role_id", "project_id"}
    ),
    "skill": frozenset({"name", "depth", "project_ids", "role_ids", "achievement_ids"}),
    "achievement": frozenset({"kind", "title", "issuer", "achieved_on"}),
    "education": frozenset({"institution", "qualification", "field", "start_date", "end_date"}),
    "language": frozenset({"name", "proficiency"}),
    "feedback": frozenset({"given_by", "content", "received_on", "role_id", "project_id"}),
}
