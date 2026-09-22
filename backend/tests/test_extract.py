# ruff: noqa: E501
"""Extraction: prompt shape, schema strictness, and the evidence check. FakeModel only."""

import datetime as dt

from anyview.brain.extract import (
    FIELD_ALIAS,
    NOT_CONTENT,
    PATCH_SCHEMA,
    ExtractionFailed,
    drop_unchanged,
    extraction_system,
    propose,
)
from anyview.brain.models import (
    Achievement,
    AchievementDraft,
    Brain,
    Coverage,
    Education,
    EducationDraft,
    Language,
    LanguageDraft,
    Patch,
    Project,
    ProjectDraft,
    Provenance,
    Role,
    RoleDraft,
    Skill,
    SkillDraft,
    Story,
    StoryDraft,
)
from anyview.llm.fake import DEFAULTS, FakeModel
from tests.conftest import RESUME


def _walk(schema):
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _walk(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _walk(v)


def test_patch_schema_is_closed_and_flat():
    for node in _walk(PATCH_SCHEMA):
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node["properties"])
    assert "$defs" not in PATCH_SCHEMA


def test_system_prompt_carries_the_index_and_the_rules():
    text = extraction_system("[R1] Acme — SRE (2020-01 → now)")
    assert "<brain_index>\n[R1] Acme — SRE" in text
    assert "verbatim quote" in text and "Never create a duplicate" in text
    assert "(empty — this is the first dump)" in extraction_system("")


def test_propose_returns_the_fake_patch_with_evidence_kept():
    fake = FakeModel()
    patch = propose(RESUME, brain_index="", model=fake, session_id="s")
    assert [r.company for r in patch.roles] == ["Acme Corp"]
    assert patch.projects[0].role == "r1"
    assert patch.stories[0].competencies == ["ownership", "failure"]
    call = fake.calls[-1]
    assert call["call"] == "propose" and "<dump>" in call["user"]


def test_drafts_whose_evidence_is_not_in_the_dump_are_dropped_and_links_severed():
    scripted = {
        **DEFAULTS["propose"],
        "roles": [
            {**DEFAULTS["propose"]["roles"][0], "evidence": "this sentence is not in the dump"}
        ],
    }
    patch = propose(RESUME, brain_index="", model=FakeModel({"propose": scripted}), session_id="s")
    assert patch.roles == []
    assert patch.projects[0].role is None  # pointed at the dropped r1
    assert patch.stories[0].role is None


def test_existing_labels_survive_the_link_check():
    scripted = {**DEFAULTS["propose"], "roles": []}
    scripted["projects"] = [{**scripted["projects"][0], "role": "R3"}]
    patch = propose(
        RESUME, brain_index="[R3] x", model=FakeModel({"propose": scripted}), session_id="s"
    )
    assert patch.projects[0].role == "R3"


def test_evidence_check_is_whitespace_and_case_tolerant():
    scripted = {**DEFAULTS["propose"]}
    scripted["skills"] = [
        {**scripted["skills"][0], "evidence": "designed   the TERRAFORM module library"}
    ]
    patch = propose(RESUME, brain_index="", model=FakeModel({"propose": scripted}), session_id="s")
    assert [k.name for k in patch.skills] == ["Terraform"]


def test_malformed_and_failed_replies_are_extraction_failures():
    import pytest

    with pytest.raises(ExtractionFailed):
        propose(
            RESUME, brain_index="", model=FakeModel({"propose": {"roles": "nope"}}), session_id="s"
        )
    with pytest.raises(ExtractionFailed):
        propose(
            RESUME,
            brain_index="",
            model=FakeModel({"propose": "plain text, not a dict"}),
            session_id="s",
        )


# --- Delta detection (ADR 0015) ---------------------------------------------


def _brain(**over) -> Brain:
    empty = {
        k: []
        for k in (
            "roles",
            "projects",
            "stories",
            "skills",
            "achievements",
            "education",
            "languages",
        )
    }
    return Brain(
        **{**empty, **over},
        coverage=Coverage(competencies=[], roles=[], cells={}),
        pending_proposals=0,
    )


SOURCE = Provenance(raw_dump_id="00000000-0000-0000-0000-000000000001", event_id=1)
ROLE = Role(
    id="11111111-1111-1111-1111-111111111111",
    label="R1",
    company="Acme Corp",
    title="Senior Cloud Architect",
    start_date=dt.date(2021, 1, 1),
    end_date=None,
    level="senior",
    source=SOURCE,
)


def _role_draft(**over) -> RoleDraft:
    return RoleDraft(
        **{
            "key": "r1",
            "existing": "R1",
            "company": "Acme Corp",
            "title": "Senior Cloud Architect",
            "start_date": dt.date(2021, 1, 1),
            "end_date": None,
            "level": "senior",
            "evidence": "Acme Corp (2021–present) — Senior Cloud Architect",
            **over,
        }
    )


def test_a_draft_that_restates_a_confirmed_entity_is_dropped():
    kept = drop_unchanged(Patch(roles=[_role_draft()]), _brain(roles=[ROLE]))
    assert kept.is_empty()


def test_whitespace_case_and_a_new_quote_are_not_changes():
    draft = _role_draft(
        company="  ACME   Corp ", title="senior cloud architect", evidence="a different quote"
    )
    assert drop_unchanged(Patch(roles=[draft]), _brain(roles=[ROLE])).is_empty()


def test_a_real_change_survives():
    kept = drop_unchanged(Patch(roles=[_role_draft(level="principal")]), _brain(roles=[ROLE]))
    assert [d.level for d in kept.roles] == ["principal"]


def test_a_draft_naming_an_entity_that_is_not_there_survives():
    """The model referenced a label the brain does not have. That is for the
    user to sort out in the queue, not for a filter to silently discard."""
    kept = drop_unchanged(Patch(roles=[_role_draft(existing="R9")]), _brain(roles=[ROLE]))
    assert len(kept.roles) == 1


def test_a_link_to_a_dropped_draft_is_re_pointed_at_its_label():
    """A project links to its role by patch key. Dropping the role as unchanged
    must not sever that link: the entity it named is still in the brain."""
    project = ProjectDraft(
        key="p1",
        role="r1",
        name="Billing service migration",
        evidence="Led migration of the billing service from VMs to Cloud Run",
    )
    kept = drop_unchanged(Patch(roles=[_role_draft()], projects=[project]), _brain(roles=[ROLE]))
    assert kept.roles == [] and kept.projects[0].role == "R1"


def test_every_draft_field_has_something_to_compare_against():
    """ADR 0015: the comparison walks the draft models, so a field added to a
    draft and its projection is compared the moment it exists — but only if the
    two names line up or FIELD_ALIAS says how. This is that check."""
    pairs = [
        (RoleDraft, Role), (ProjectDraft, Project), (StoryDraft, Story),
        (SkillDraft, Skill), (AchievementDraft, Achievement),
        (EducationDraft, Education), (LanguageDraft, Language),
    ]  # fmt: skip
    for draft, entity in pairs:
        for name in draft.model_fields:
            if name in NOT_CONTENT:
                continue
            target = FIELD_ALIAS.get(name, name)
            assert target in entity.model_fields, (
                f"{draft.__name__}.{name} has no counterpart on {entity.__name__}; "
                f"add it to FIELD_ALIAS or the projection"
            )
