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
    merge,
    propose,
)
from anyview.brain.models import (
    Achievement,
    AchievementDraft,
    Brain,
    Coverage,
    Education,
    EducationDraft,
    Feedback,
    FeedbackDraft,
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
    # Short dump: no segmentation call, one extraction, then the linking pass.
    assert [c["call"] for c in fake.calls] == ["propose", "link"]
    assert "<dump>" in fake.calls[0]["user"]


def test_drafts_whose_evidence_is_not_in_the_dump_are_flagged_not_dropped():
    """ADR 0019: the user sees a draft whose quote could not be found, flagged,
    instead of never learning it existed."""
    scripted = {
        **DEFAULTS["propose"],
        "roles": [
            {**DEFAULTS["propose"]["roles"][0], "evidence": "this sentence is not in the dump"}
        ],
    }
    patch = propose(RESUME, brain_index="", model=FakeModel({"propose": scripted}), session_id="s")
    assert [r.unverified for r in patch.roles] == [True]
    assert patch.projects[0].role == "r1"  # links to it survive; the user decides
    assert patch.projects[0].unverified is False


def test_existing_labels_survive_the_link_check():
    scripted = {**DEFAULTS["propose"], "roles": []}
    scripted["projects"] = [{**scripted["projects"][0], "role": "R3"}]
    patch = propose(
        RESUME, brain_index="[R3] x", model=FakeModel({"propose": scripted}), session_id="s"
    )
    assert patch.projects[0].role == "R3"


def test_existing_of_the_wrong_kind_is_cleared_not_kept():
    # The model recognises the NTU degree from the resume, but points at A3 —
    # the label it was filed under earlier, as an achievement, not education.
    scripted = {
        **DEFAULTS["propose"],
        "education": [
            {
                "key": "e1",
                "existing": "A3",
                "institution": "Acme University",
                "qualification": "B.Sc.",
                "field": None,
                "start_date": None,
                "end_date": None,
                "evidence": "Acme Corp (2021–present) — Senior Cloud Architect",
            },
        ],
    }
    patch = propose(RESUME, brain_index="", model=FakeModel({"propose": scripted}), session_id="s")
    assert patch.education[0].existing is None  # a new draft, not a doomed update to A3


def test_existing_of_the_right_kind_is_kept():
    scripted = {
        **DEFAULTS["propose"],
        "roles": [{**DEFAULTS["propose"]["roles"][0], "existing": "R3"}],
    }
    patch = propose(
        RESUME,
        brain_index="[R3] Acme — SRE",
        model=FakeModel({"propose": scripted}),
        session_id="s",
    )
    assert patch.roles[0].existing == "R3"


def test_a_long_key_on_an_update_does_not_fail_the_upload():
    # A feedback upload came back with "p13_update" style keys on every update,
    # and an 8-character cap rejected the whole proposal as malformed.
    scripted = {
        **DEFAULTS["propose"],
        "roles": [{**DEFAULTS["propose"]["roles"][0], "key": "r13_update", "existing": "R3"}],
    }
    patch = propose(
        RESUME,
        brain_index="[R3] Acme — SRE",
        model=FakeModel({"propose": scripted}),
        session_id="s",
    )
    assert patch.roles[0].key == "r13_update"
    assert patch.roles[0].existing == "R3"


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
            "feedback",
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
        (FeedbackDraft, Feedback),
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


# --- Feedback (a Digital Garden entity kind, complementing stories) ---------

FEEDBACK_QUOTE = (
    'My manager told me after the migration: "You owned that end to end and never '
    'let the team lose momentum."'
)


def test_extraction_system_names_feedback_as_a_tracked_category():
    text = extraction_system("")
    assert "feedback" in text
    assert "given_by" in text and "content" in text


def test_propose_can_return_a_feedback_draft():
    scripted = {**DEFAULTS["propose"], "roles": [], "feedback": []}
    scripted["feedback"] = [
        {
            "key": "f1",
            "existing": None,
            "role": None,
            "project": None,
            "given_by": "Manager, 2024 review",
            "content": FEEDBACK_QUOTE,
            "received_on": "2024-11-01",
            "evidence": FEEDBACK_QUOTE,
        }
    ]
    patch = propose(
        FEEDBACK_QUOTE, brain_index="", model=FakeModel({"propose": scripted}), session_id="s"
    )
    assert [f.given_by for f in patch.feedback] == ["Manager, 2024 review"]
    assert patch.feedback[0].content == FEEDBACK_QUOTE


def test_feedback_with_evidence_not_in_the_dump_is_flagged():
    scripted = {**DEFAULTS["propose"], "roles": [], "feedback": []}
    scripted["feedback"] = [
        {
            "key": "f1",
            "existing": None,
            "role": None,
            "project": None,
            "given_by": "Manager",
            "content": "a quote that does not appear anywhere",
            "received_on": None,
            "evidence": "a quote that does not appear anywhere",
        }
    ]
    patch = propose(RESUME, brain_index="", model=FakeModel({"propose": scripted}), session_id="s")
    assert [f.unverified for f in patch.feedback] == [True]


def _feedback_draft(**over) -> FeedbackDraft:
    return FeedbackDraft(
        **{
            "key": "f1",
            "existing": "F1",
            "role": None,
            "project": None,
            "given_by": "Manager, 2024 review",
            "content": FEEDBACK_QUOTE,
            "received_on": dt.date(2024, 11, 1),
            "evidence": FEEDBACK_QUOTE,
            **over,
        }
    )


FEEDBACK_ENTITY = Feedback(
    id="22222222-2222-2222-2222-222222222222",
    label="F1",
    role_id=None,
    project_id=None,
    given_by="Manager, 2024 review",
    content=FEEDBACK_QUOTE,
    received_on=dt.date(2024, 11, 1),
    source=SOURCE,
)


def test_a_feedback_draft_that_restates_a_confirmed_entry_is_dropped():
    kept = drop_unchanged(Patch(feedback=[_feedback_draft()]), _brain(feedback=[FEEDBACK_ENTITY]))
    assert kept.is_empty()


def test_a_changed_feedback_draft_survives():
    kept = drop_unchanged(
        Patch(feedback=[_feedback_draft(content="a materially different quote entirely")]),
        _brain(feedback=[FEEDBACK_ENTITY]),
    )
    assert len(kept.feedback) == 1


def test_a_feedback_draft_linking_to_a_dropped_role_is_re_pointed():
    feedback = FeedbackDraft(
        key="f1",
        role="r1",
        given_by="Peer",
        content="Quote about the role",
        evidence="Quote about the role",
    )
    kept = drop_unchanged(Patch(roles=[_role_draft()], feedback=[feedback]), _brain(roles=[ROLE]))
    assert kept.roles == [] and kept.feedback[0].role == "R1"


# --- Sections, lists, merging, links (ADR 0019) ------------------------------


def test_the_prompt_defines_the_kinds_and_expands_lists():
    text = extraction_system("")
    assert "Prefer fewer" not in text
    assert "Every item in a list is its own entry" in text
    assert "Never make up a project to hold ongoing work" in text
    assert "`responsibilities`" in text


def test_the_schema_carries_responsibilities_and_role_links():
    items = PATCH_SCHEMA["properties"]
    assert "responsibilities" in items["roles"]["items"]["properties"]
    assert {"projects", "roles", "achievements"} <= set(items["skills"]["items"]["properties"])


def _skill(key: str, name: str, evidence: str, **over) -> dict:
    return {
        "key": key,
        "existing": None,
        "name": name,
        "depth": 3,
        "projects": [],
        "roles": [],
        "evidence": evidence,
        **over,
    }


def test_merge_renumbers_keys_and_keeps_one_of_each_thing():
    experience = Patch.model_validate(
        {
            "roles": [DEFAULTS["propose"]["roles"][0]],
            "projects": [DEFAULTS["propose"]["projects"][0]],
            "skills": [_skill("k1", "Terraform", "Designed the Terraform module library")],
        }
    )
    skills = Patch.model_validate(
        {
            "skills": [
                _skill("k1", "terraform", "Terraform, Kubernetes", existing="K4"),
                _skill("k2", "Kubernetes", "Terraform, Kubernetes"),
            ],
            # References a key this section never defined: dropped, not kept dangling.
            "projects": [
                {**DEFAULTS["propose"]["projects"][0], "key": "p1", "role": "r7", "name": "Other"}
            ],
        }
    )
    merged = merge([experience, skills])
    assert [k.key for k in merged.skills] == ["k1", "k2"]
    assert [k.name for k in merged.skills] == ["Terraform", "Kubernetes"]
    # The experience draft wins, and takes the gap-filling `existing` label.
    assert merged.skills[0].evidence == "Designed the Terraform module library"
    assert merged.skills[0].existing == "K4"
    assert [p.key for p in merged.projects] == ["p1", "p2"]
    assert merged.projects[0].role == "r1" and merged.projects[1].role is None


def test_merge_unions_lists_like_responsibilities():
    a = Patch(roles=[_role_draft(existing=None, responsibilities=["EKS day-2 operations"])])
    b = Patch(
        roles=[
            _role_draft(existing=None, key="r1", responsibilities=["eks day-2 operations", "RFQs"])
        ]
    )
    assert merge([a, b]).roles[0].responsibilities == ["EKS day-2 operations", "RFQs"]


LONG_RESUME = RESUME + "\n" + "\n".join(f"- filler line {n} about nothing much" for n in range(80))


def test_a_long_dump_is_extracted_section_by_section_and_merged():
    lines = LONG_RESUME.splitlines()
    fake = FakeModel(
        {
            "segment": {
                "sections": [
                    {"kind": "experience", "start_line": 1, "end_line": 5},
                    {"kind": "skills", "start_line": 6, "end_line": len(lines)},
                ]
            }
        }
    )
    patch = propose(LONG_RESUME, brain_index="", model=fake, session_id="s")
    calls = [c["call"] for c in fake.calls]
    assert calls[0] == "segment" and calls.count("propose") == 2 and calls[-1] == "link"
    sections = [c["user"] for c in fake.calls if c["call"] == "propose"]
    assert any('<dump section="experience">' in u for u in sections)
    assert any('<dump section="skills">' in u for u in sections)
    # Both sections returned the same scripted patch; the merge keeps one of each.
    assert [r.company for r in patch.roles] == ["Acme Corp"]
    assert len(patch.skills) == 1
    # And the linking pass ran over the merged drafts.
    assert patch.skills[0].roles == ["r1"]
    assert "r1" in patch.skills[0].link_evidence


def test_a_failed_section_fails_the_upload_rather_than_losing_entries():
    import pytest

    fake = FakeModel(
        {
            "segment": {
                "sections": [
                    {"kind": "experience", "start_line": 1, "end_line": 5},
                    {"kind": "skills", "start_line": 6, "end_line": 90},
                ]
            },
            "propose": {"roles": "not a list"},
        }
    )
    with pytest.raises(ExtractionFailed):
        propose(LONG_RESUME, brain_index="", model=fake, session_id="s")


SKILL = Skill(
    id="33333333-3333-3333-3333-333333333333",
    label="K1",
    name="Terraform",
    depth=4,
    project_ids=[],
    role_ids=[ROLE.id],
    achievement_ids=[],
    source=SOURCE,
)


def test_a_confirmed_skill_keeps_its_links_on_re_upload():
    """Absence is not evidence (ADR 0015): a link this dump did not show again
    stays, so an otherwise unchanged skill is dropped, not re-proposed."""
    draft = SkillDraft(key="k1", existing="K1", name="Terraform", depth=4, evidence="Terraform")
    assert drop_unchanged(Patch(skills=[draft]), _brain(roles=[ROLE], skills=[SKILL])).is_empty()


def test_a_new_link_on_a_confirmed_skill_is_a_change_and_keeps_the_old_one():
    draft = SkillDraft(
        key="k1",
        existing="K1",
        name="Terraform",
        depth=4,
        evidence="Terraform",
        projects=["p1"],
        link_evidence={"p1": "q"},
    )
    project = ProjectDraft(key="p1", name="Billing", evidence="Billing")
    kept = drop_unchanged(
        Patch(projects=[project], skills=[draft]), _brain(roles=[ROLE], skills=[SKILL])
    )
    assert kept.skills[0].projects == ["p1"] and kept.skills[0].roles == ["R1"]


def test_unverified_and_link_quotes_are_not_changes():
    draft = _role_draft(unverified=True)
    assert drop_unchanged(Patch(roles=[draft]), _brain(roles=[ROLE])).is_empty()


def test_a_bracketed_abbreviation_is_the_same_skill_and_the_fuller_name_wins():
    experience = Patch(
        skills=[SkillDraft(key="k1", name="RAG", depth=3, evidence="custom RAG pipeline")]
    )
    skills = Patch(
        skills=[
            SkillDraft(
                key="k1", name="Retrieval-Augmented Generation (RAG)", depth=2, evidence="RAG"
            ),
            SkillDraft(key="k2", name="Amazon Bedrock", depth=2, evidence="Bedrock"),
        ]
    )
    merged = merge([experience, skills])
    assert [k.name for k in merged.skills] == [
        "Retrieval-Augmented Generation (RAG)",
        "Amazon Bedrock",
    ]
    assert merged.skills[0].evidence == "custom RAG pipeline"  # the experience quote is kept


def test_only_skills_get_bracket_aliases():
    a = Patch(
        education=[EducationDraft(key="e1", institution="NTU", qualification="B.Sc.", evidence="x")]
    )
    b = Patch(
        education=[
            EducationDraft(
                key="e1",
                institution="Nanyang Technological University (NTU)",
                qualification="B.Sc.",
                evidence="y",
            )
        ]
    )
    assert len(merge([a, b]).education) == 2


def test_a_new_skill_named_like_a_live_one_becomes_an_update_to_it():
    """The database allows one live skill per name; a section read on its own
    cannot know the garden already has "Terraform"."""
    draft = SkillDraft(key="k1", name=" terraform ", depth=4, evidence="Terraform")
    assert drop_unchanged(Patch(skills=[draft]), _brain(roles=[ROLE], skills=[SKILL])).is_empty()
    changed = SkillDraft(key="k1", name="Terraform", depth=5, evidence="Terraform")
    kept = drop_unchanged(Patch(skills=[changed]), _brain(roles=[ROLE], skills=[SKILL]))
    assert kept.skills[0].existing == "K1"


def test_list_sections_think_less_and_each_job_is_told_it_is_one_job():
    lines = LONG_RESUME.splitlines()
    fake = FakeModel(
        {
            "segment": {
                "sections": [
                    {"kind": "experience", "start_line": 1, "end_line": 5, "job": 1},
                    {"kind": "experience", "start_line": 6, "end_line": 9, "job": 2},
                    {"kind": "skills", "start_line": 10, "end_line": len(lines), "job": 0},
                ]
            }
        }
    )
    seen: list[tuple[str, dict]] = []
    propose(
        LONG_RESUME,
        brain_index="",
        model=fake,
        session_id="s",
        on_progress=lambda s, d: seen.append((s, d)),
    )
    reads = [c for c in fake.calls if c["call"] == "propose"]
    assert sum("one job from the experience section" in c["user"] for c in reads) == 2
    assert [s for s, _ in seen].count("section_done") == 3
    assert seen[0][0] == "sections" and len(seen[0][1]["sections"]) == 3


def test_spoken_answers_are_transcribed_as_english():
    from anyview.uploads.extract import ANSWER_SYSTEM

    assert "speaking English" in ANSWER_SYSTEM and "never another language" in ANSWER_SYSTEM
