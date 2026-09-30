# ruff: noqa: E501 — fixture data reads better unwrapped.
"""Finding a dump's sections (ADR 0019). FakeModel only."""

from anyview.brain.sections import MIN_CHARS, Section, from_ranges, segment
from anyview.llm.fake import FakeModel

LINES = [
    "Jordan Lee",  # 1
    "EXPERIENCE",  # 2
    "Acme Corp — Architect",  # 3
    "- Led the migration",  # 4
    "SKILLS",  # 5
    "Terraform, Kubernetes",  # 6
    "CERTIFICATIONS",  # 7
    "AWS SA Pro",  # 8
    "Acme Corp — earlier bullet",  # 9, experience again: a two-column layout
]


def test_every_line_lands_in_exactly_one_section_experience_first():
    sections = from_ranges(
        LINES,
        [
            {"kind": "skills", "start_line": 5, "end_line": 6},
            {"kind": "experience", "start_line": 2, "end_line": 4},
            {"kind": "certifications", "start_line": 7, "end_line": 8},
            {"kind": "experience", "start_line": 9, "end_line": 9},
        ],
    )
    assert [s.kind for s in sections] == ["experience", "skills", "certifications"]
    # The two experience ranges are read together, in document order.
    assert sections[0].text.splitlines() == LINES[1:4] + [LINES[8]]


def test_overlaps_go_to_the_first_claim_and_ranges_are_clamped():
    sections = from_ranges(
        LINES,
        [
            {"kind": "experience", "start_line": -3, "end_line": 5},
            {"kind": "skills", "start_line": 5, "end_line": 99},
        ],
    )
    by_kind = {s.kind: s.text.splitlines() for s in sections}
    assert by_kind["experience"] == LINES[0:5]  # line 5 was claimed first
    assert by_kind["skills"] == LINES[5:]


def test_unclaimed_lines_go_to_other_and_a_long_other_is_kept():
    long_line = "Interests: " + "x" * 250
    lines = [*LINES, long_line]
    sections = from_ranges(
        lines,
        [
            {"kind": "experience", "start_line": 2, "end_line": 4},
            {"kind": "skills", "start_line": 5, "end_line": 6},
        ],
    )
    other = next(s for s in sections if s.kind == "other")
    assert long_line in other.text and "AWS SA Pro" in other.text


def test_one_real_section_means_no_split():
    assert from_ranges(LINES, [{"kind": "experience", "start_line": 1, "end_line": 9}]) == []
    assert from_ranges(LINES, []) == []


def test_a_short_dump_is_never_segmented():
    fake = FakeModel()
    assert segment("short text", model=fake, session_id="s") == []
    assert fake.calls == []


def test_a_long_dump_asks_the_fast_model_for_numbered_ranges():
    text = "\n".join(LINES) + "\n" + "- filler bullet\n" * (MIN_CHARS // 10)
    fake = FakeModel(
        {
            "segment": {
                "sections": [
                    {"kind": "experience", "start_line": 1, "end_line": 4},
                    {"kind": "skills", "start_line": 5, "end_line": 6},
                ]
            }
        }
    )
    sections = segment(text, model=fake, session_id="s")
    assert [s.kind for s in sections][:2] == ["experience", "skills"]
    call = fake.calls[0]
    assert call["call"] == "segment" and call.get("fast") is True
    assert "3: Acme Corp — Architect" in call["user"]


def test_a_failed_segmentation_falls_back_to_one_call():
    text = "x\n" * MIN_CHARS
    assert segment(text, model=FakeModel(fail="segment"), session_id="s") == []


def test_section_is_plain_data():
    assert Section(kind="skills", text="Terraform") == Section(kind="skills", text="Terraform")


JOBS = [
    "EXPERIENCE",  # 1
    "Multi-Cloud Solutions Architect",  # 2
    "Lenovo PCCW | Apr 2026 - Present",  # 3
    "- Architected the assessment",  # 4
    "SKILLS",  # 5
    "Terraform",  # 6
    "Cloud Architect",  # 7
    "Accenture | Jul 2021 - Mar 2026",  # 8
    "- Integrated SSO",  # 9
]


def test_each_job_is_its_own_section_named_by_its_first_line():
    sections = from_ranges(
        JOBS,
        [
            {"kind": "experience", "start_line": 1, "end_line": 1, "job": 0},
            {"kind": "experience", "start_line": 2, "end_line": 4, "job": 1},
            {"kind": "skills", "start_line": 5, "end_line": 6, "job": 0},
            {"kind": "experience", "start_line": 7, "end_line": 9, "job": 2},
        ],
    )
    assert [(s.kind, s.label) for s in sections] == [
        ("experience", "Multi-Cloud Solutions Architect"),
        ("experience", "Cloud Architect"),
        ("skills", ""),
    ]
    assert sections[0].text.startswith("EXPERIENCE\nMulti-Cloud")  # the heading joins job one
    assert sections[0].one_job and not sections[2].one_job


def test_a_single_job_stays_one_experience_section():
    sections = from_ranges(
        JOBS,
        [
            {"kind": "experience", "start_line": 1, "end_line": 4, "job": 1},
            {"kind": "skills", "start_line": 5, "end_line": 9, "job": 0},
        ],
    )
    assert [(s.kind, s.label) for s in sections] == [("experience", ""), ("skills", "")]
