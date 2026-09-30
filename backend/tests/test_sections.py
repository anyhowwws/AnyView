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
