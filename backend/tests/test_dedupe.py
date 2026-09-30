# ruff: noqa: E501 — fixture data reads better unwrapped.
"""Folding near-duplicate skills (ADR 0021). FakeModel only."""

from anyview.brain.dedupe import Group, checked, near_duplicates
from anyview.brain.extract import fold_duplicates, propose
from anyview.brain.models import Patch, SkillDraft
from anyview.llm.fake import DEFAULTS, FakeModel


def _skills() -> list[SkillDraft]:
    return [
        SkillDraft(key="k1", name="GitLab CI/CD", depth=4, evidence="redesign GitLab CI/CD"),
        SkillDraft(key="k2", name="GitLab", depth=2, evidence="GitLab CI/CD"),
        SkillDraft(key="k3", name="CI/CD", depth=3, evidence="GitLab CI/CD", roles=["r1"]),
        SkillDraft(key="k4", name="GCP", depth=3, evidence="landing zones (AWS & GCP)"),
        SkillDraft(key="k5", name="Kubernetes", depth=3, evidence="EKS"),
        SkillDraft(key="k6", name="Terraform", depth=3, evidence="Terraform", existing="K1"),
        SkillDraft(key="k7", name="Terraform CLI", depth=2, evidence="Terraform", existing="K2"),
        SkillDraft(key="k8", name="Bedrock", depth=2, evidence="Amazon Bedrock", unverified=True),
    ]


def test_parts_fold_into_the_compound_and_the_names_are_kept():
    patch = Patch(skills=_skills())
    folded = fold_duplicates(patch, [Group(keep="k1", merge=("k2", "k3"))], {})
    gitlab = folded.skills[0]
    assert [k.key for k in folded.skills] == ["k1", "k4", "k5", "k6", "k7", "k8"]
    assert gitlab.name == "GitLab CI/CD" and gitlab.evidence == "redesign GitLab CI/CD"
    assert gitlab.merged_from == ["GitLab", "CI/CD"]
    assert gitlab.depth == 4 and gitlab.roles == ["r1"]  # lists are unioned


def test_a_draft_that_is_a_garden_skill_updates_it_under_the_gardens_name():
    patch = Patch(skills=_skills())
    folded = fold_duplicates(patch, [Group(keep="K9", merge=("k4",))], {"K9": "Google Cloud"})
    gcp = next(k for k in folded.skills if k.key == "k4")
    assert gcp.existing == "K9" and gcp.name == "Google Cloud" and gcp.merged_from == ["GCP"]


def test_a_verified_quote_replaces_an_unverified_one():
    skills = _skills()
    skills.append(
        SkillDraft(key="k9", name="Amazon Bedrock", depth=3, evidence="using Amazon Bedrock")
    )
    folded = fold_duplicates(Patch(skills=skills), [Group(keep="k8", merge=("k9",))], {})
    bedrock = next(k for k in folded.skills if k.key == "k8")
    assert bedrock.unverified is False and bedrock.evidence == "using Amazon Bedrock"


def test_only_safe_groups_survive_the_check():
    skills, garden = _skills(), {"K1": "Terraform", "K2": "Terraform CLI", "K9": "Google Cloud"}
    groups = checked(
        [
            {"keep": "k1", "merge": ["k2", "k3"]},  # fine
            {"keep": "k5", "merge": ["k2"]},  # k2 is already in a group
            {"keep": "k6", "merge": ["k7"]},  # joins two confirmed skills, K1 and K2
            {"keep": "K9", "merge": ["k4"]},  # a draft into a garden skill: fine
            {"keep": "k99", "merge": ["k5"]},  # unknown keep
            {"keep": "k5", "merge": ["k5"]},  # nothing to merge
            {"keep": "K1", "merge": ["k7"]},  # k7 already updates K2
        ],
        skills,
        garden,
    )
    assert groups == [Group(keep="k1", merge=("k2", "k3")), Group(keep="K9", merge=("k4",))]


def test_the_call_offers_keys_quotes_and_garden_labels_and_pins_them_by_schema():
    fake = FakeModel({"dedupe": {"groups": [{"keep": "k1", "merge": ["k2"]}]}})
    groups = near_duplicates(
        Patch(skills=_skills()[:2]), garden_skills={"K3": "AWS"}, model=fake, session_id="s"
    )
    assert groups == [Group(keep="k1", merge=("k2",))]
    user = fake.calls[0]["user"]
    assert 'k2: GitLab — "GitLab CI/CD"' in user and "K3: AWS" in user


def test_nothing_to_compare_means_no_call_and_a_failure_means_no_groups():
    fake = FakeModel()
    one = Patch(skills=_skills()[:1])
    assert near_duplicates(one, garden_skills={}, model=fake, session_id="s") == []
    assert fake.calls == []
    two = Patch(skills=_skills()[:2])
    assert (
        near_duplicates(two, garden_skills={}, model=FakeModel(fail="dedupe"), session_id="s") == []
    )


def test_propose_folds_before_it_links():
    """Links land on the survivor: dedupe runs before the linking pass."""
    scripted = {**DEFAULTS["propose"]}
    scripted["skills"] = [
        {**DEFAULTS["propose"]["skills"][0]},
        {**DEFAULTS["propose"]["skills"][0], "key": "k2", "name": "Terraform modules"},
    ]
    fake = FakeModel({"propose": scripted, "dedupe": {"groups": [{"keep": "k1", "merge": ["k2"]}]}})
    from tests.conftest import RESUME

    patch = propose(RESUME, brain_index="", model=fake, session_id="s")
    assert [k.name for k in patch.skills] == ["Terraform"]
    assert patch.skills[0].merged_from == ["Terraform modules"]
    assert [c["call"] for c in fake.calls] == ["propose", "dedupe", "link"]
    assert patch.skills[0].roles == ["r1"]
