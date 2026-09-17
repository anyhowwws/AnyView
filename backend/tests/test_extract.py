# ruff: noqa: E501
"""Extraction: prompt shape, schema strictness, and the evidence check. FakeModel only."""

from anyview.brain.extract import PATCH_SCHEMA, ExtractionFailed, extraction_system, propose
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
