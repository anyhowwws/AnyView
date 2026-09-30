# ruff: noqa: E501 — fixture data reads better unwrapped.
"""Quote matching and target stretches (ADR 0019). Pure functions, no model."""

from anyview.brain.evidence import contains, fold, normalise, spans, within
from anyview.brain.models import Patch, ProjectDraft, RoleDraft

TEXT = (
    "Multi-Cloud Solutions Architect\n"
    "Lenovo PCCW Solutions, Singapore | Apr 2026 – Present\n"
    "• Architected an AI-powered assessment on AWS and Azure using Amazon Bedrock.\n"
    "• Managed Amazon EKS day-2 operations (Helm, IRSA).\n"
    "Cloud Architect\n"
    "Accenture, Singapore | Jul 2021 – Mar 2026\n"
    "• Integrated SSO with Okta, migrating 300+ users."
)


def test_dashes_bullets_quotes_case_and_spacing_fold_together():
    assert normalise("Apr 2026 – Present") == normalise("apr  2026 - present")
    assert normalise("“Owned it”") == normalise('"owned it"')
    assert normalise("ﬁle") == "file"  # NFKC: a ligature is two letters
    assert normalise("AWS · Azure") == "aws azure"


def test_contains_tolerates_an_en_dash_quoted_as_a_hyphen():
    assert contains(TEXT, "Singapore | Apr 2026 - Present")
    assert not contains(TEXT, "Singapore | Apr 2025 - Present")  # words still have to match
    assert not contains(TEXT, "   ")


def test_fold_maps_each_character_back_to_the_original():
    folded, where = fold("A  –  B")
    assert folded == "a - b"
    assert [where[0], where[2], where[4]] == [0, 3, 6]


def _patch() -> Patch:
    return Patch(
        roles=[
            RoleDraft(key="r1", company="Lenovo PCCW", title="Architect", evidence="Lenovo PCCW Solutions, Singapore"),
            RoleDraft(key="r2", company="Accenture", title="Cloud Architect", evidence="Accenture, Singapore"),
        ],
        projects=[
            ProjectDraft(key="p1", role="r1", name="AI assessment", evidence="Architected an AI-powered assessment"),
            ProjectDraft(key="p2", role="r2", name="SSO", evidence="Integrated SSO with Okta"),
            ProjectDraft(key="p9", name="Invented", evidence="not in the text", unverified=True),
        ],
    )  # fmt: skip


def test_a_project_ends_where_the_next_entry_starts_and_a_role_covers_its_projects():
    folded = normalise(TEXT)
    stretch = spans(_patch(), TEXT)
    assert within(folded, "using Amazon Bedrock", *stretch["p1"])
    assert not within(folded, "Amazon EKS day-2", *stretch["p1"])  # the next bullet is not p1's
    assert within(folded, "Amazon EKS day-2 operations", *stretch["r1"])
    assert within(folded, "using Amazon Bedrock", *stretch["r1"])
    assert not within(folded, "Okta", *stretch["r1"])  # Accenture's text, not Lenovo's
    assert within(folded, "Okta", *stretch["r2"])


def test_a_draft_without_a_found_quote_has_no_stretch():
    assert "p9" not in spans(_patch(), TEXT)


def test_a_credentials_stretch_is_its_own_quote_and_only_credentials_get_one():
    from anyview.brain.models import AchievementDraft

    text = "Certified: Terraform Associate · CKA\nWon the 2023 hackathon"
    patch = Patch(
        achievements=[
            AchievementDraft(
                key="a1",
                kind="credential",
                title="HashiCorp Terraform Associate",
                evidence="Terraform Associate",
            ),
            AchievementDraft(
                key="a2", kind="achievement", title="Hackathon", evidence="Won the 2023 hackathon"
            ),
        ]
    )
    folded = normalise(text)
    stretch = spans(patch, text)
    assert within(folded, "Terraform Associate", *stretch["a1"])
    assert not within(folded, "CKA", *stretch["a1"])
    assert "a2" not in stretch


def test_a_quote_stitched_across_two_lines_with_an_invented_separator_is_found():
    """The model joined the title line and the employer line with " | "; every
    word is the document's own and in order (the case that flagged real roles)."""
    text = "Multi-Cloud Solutions Architect\nLenovo PCCW Solutions, Singapore | Apr 2026 – Present\n- Architected"
    assert contains(
        text,
        "Multi-Cloud Solutions Architect | Lenovo PCCW Solutions, Singapore | Apr 2026 – Present",
    )
    assert contains(text, "Multi-Cloud Solutions Architect — Lenovo PCCW Solutions")


def test_stitched_pieces_must_be_adjacent_and_in_order():
    text = "Multi-Cloud Solutions Architect\nsome other words\nLenovo PCCW Solutions"
    assert not contains(
        text, "Multi-Cloud Solutions Architect | Lenovo PCCW Solutions"
    )  # words between
    assert not contains("Lenovo PCCW\nArchitect", "Architect | Lenovo PCCW")  # wrong order
    assert not contains("Architect\nLenovo", "Architect | Accenture")  # a piece that is not there


def test_a_stitched_role_quote_still_anchors_its_stretch():
    text = (
        "Cloud Architect\nAccenture, Singapore | Jul 2021 – Mar 2026\n- Integrated SSO with Okta."
    )
    patch = Patch(
        roles=[
            RoleDraft(
                key="r1",
                company="Accenture",
                title="Cloud Architect",
                evidence="Cloud Architect | Accenture, Singapore | Jul 2021 – Mar 2026",
            )
        ]
    )
    assert within(normalise(text), "Integrated SSO with Okta", *spans(patch, text)["r1"])
