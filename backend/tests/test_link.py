# ruff: noqa: E501 — fixture data reads better unwrapped.
"""Linking skills to where they were used (ADR 0019). FakeModel only."""

from anyview.brain.link import link_skills
from anyview.brain.models import Patch, ProjectDraft, RoleDraft, SkillDraft
from anyview.llm.fake import FakeModel

TEXT = (
    "SKILLS: Terraform, Kubernetes, Python\n"
    "Lenovo PCCW Solutions | Apr 2026 – Present\n"
    "- Managed Amazon EKS day-2 operations (Helm, IRSA) for customer clusters.\n"
    "- Built the assessment platform with Terraform and Amazon Bedrock.\n"
)


def _patch() -> Patch:
    return Patch(
        roles=[RoleDraft(key="r1", company="Lenovo PCCW", title="Architect", evidence="Lenovo PCCW Solutions | Apr 2026 - Present")],
        projects=[ProjectDraft(key="p1", role="r1", name="Assessment platform", evidence="Built the assessment platform")],
        skills=[
            SkillDraft(key="k1", name="Terraform", depth=3, evidence="Terraform, Kubernetes", projects=["P7", "p9"]),
            SkillDraft(key="k2", name="Kubernetes", depth=3, evidence="Kubernetes"),
            SkillDraft(key="k3", name="Python", depth=2, evidence="Python"),
        ],
    )  # fmt: skip


def _link(skill: str, target: str, evidence: str) -> dict:
    return {"skill": skill, "target": target, "evidence": evidence}


def test_checked_links_land_on_projects_and_roles_with_their_quotes():
    fake = FakeModel(
        {
            "link": {
                "links": [
                    _link("k1", "p1", "with Terraform and Amazon Bedrock"),
                    _link("k2", "r1", "Managed Amazon EKS day-2 operations"),
                ]
            }
        }
    )
    patch = link_skills(_patch(), TEXT, model=fake, session_id="s")
    terraform, kubernetes, python = patch.skills
    assert terraform.projects == ["P7", "p1"]  # the label from extraction is kept
    assert terraform.link_evidence == {"p1": "with Terraform and Amazon Bedrock"}
    assert kubernetes.roles == ["r1"] and kubernetes.projects == []
    assert python.projects == [] and python.roles == []
    # The model saw each target's own text, in the candidate's wording.
    assert 'key="p1" kind="project"' in fake.calls[0]["user"]
    assert "Apr 2026 – Present" in fake.calls[0]["user"]


def test_a_quote_outside_the_target_is_dropped():
    fake = FakeModel(
        {
            "link": {
                "links": [
                    _link("k3", "r1", "Terraform, Kubernetes, Python"),  # the skills list
                    _link("k2", "p1", "Managed Amazon EKS"),  # another bullet, not p1's
                    _link("k1", "p5", "Terraform"),  # no such target
                    _link("k9", "p1", "Terraform"),  # no such skill
                ]
            }
        }
    )
    patch = link_skills(_patch(), TEXT, model=fake, session_id="s")
    assert all(k.projects in ([], ["P7"]) and k.roles == [] for k in patch.skills)


def test_a_failed_link_call_leaves_skills_unlinked_not_the_upload_failed():
    patch = link_skills(_patch(), TEXT, model=FakeModel(fail="link"), session_id="s")
    assert patch.skills[0].projects == ["P7"] and patch.skills[1].roles == []


def test_no_targets_means_no_call():
    fake = FakeModel()
    patch = Patch(skills=[SkillDraft(key="k1", name="Go", depth=2, evidence="Go")])
    link_skills(patch, "Go", model=fake, session_id="s")
    assert fake.calls == []
