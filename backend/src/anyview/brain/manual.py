"""Entries added by hand (ADR 0022).

The user fills in a form on /brain instead of writing a capture for Donna to
read. There is nothing to extract and nothing to review: the form *is* the
reviewed entry. What it still needs is provenance, so the form becomes the
text of a raw dump, and the entry becomes a one-draft Patch whose evidence is
that text. From there it takes the same path as a confirmed proposal.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from anyview.brain.models import (
    AchievementDraft,
    Draft,
    EducationDraft,
    EntityKind,
    FeedbackDraft,
    LanguageDraft,
    Patch,
    ProjectDraft,
    RoleDraft,
    SkillDraft,
    StoryDraft,
)

# Each kind's draft class and the Patch list it goes in.
DRAFTS: dict[EntityKind, tuple[type[Draft], str]] = {
    "role": (RoleDraft, "roles"),
    "project": (ProjectDraft, "projects"),
    "story": (StoryDraft, "stories"),
    "skill": (SkillDraft, "skills"),
    "achievement": (AchievementDraft, "achievements"),
    "education": (EducationDraft, "education"),
    "language": (LanguageDraft, "languages"),
    "feedback": (FeedbackDraft, "feedback"),
}

# Draft bookkeeping, set here rather than by the form.
_NOT_FROM_FORM = {"key", "existing", "evidence", "unverified", "link_evidence", "merged_from"}


class BadEntry(ValueError):
    """The form's fields do not make a valid entry. The message is for the user."""


def source_text(kind: EntityKind, fields: dict[str, Any]) -> str:
    """The form as the dump will keep it: one "Label: value" line per filled
    field, so "Show source" reads like what the user typed."""
    lines = [f"{kind.capitalize()} added by hand"]
    for name, value in fields.items():
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if str(v).strip())
        if value is None or str(value).strip() == "":
            continue
        lines.append(f"{name.replace('_', ' ').capitalize()}: {value}")
    return "\n".join(lines)


def patch_for(kind: EntityKind, fields: dict[str, Any], evidence: str) -> Patch:
    """A Patch holding this one entry. Raises BadEntry for unknown fields or
    values the draft model refuses (an empty title, a depth of 9, …)."""
    cls, group = DRAFTS[kind]
    allowed = set(cls.model_fields) - _NOT_FROM_FORM
    unknown = set(fields) - allowed
    if unknown:
        raise BadEntry(f"A {kind} has no {', '.join(sorted(unknown))}.")
    try:
        draft = cls(key="m1", evidence=evidence[:1000], **fields)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or kind
        raise BadEntry(f"{where.replace('_', ' ').capitalize()}: {first['msg']}.") from exc
    return Patch(**{group: [draft]})
