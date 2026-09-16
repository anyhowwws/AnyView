"""The HR/screening rubric, as data.

Each dimension has an explicit anchor for every score 0–4. The anchors are
rendered verbatim into the scoring prompt: an LLM judge given "rate 0–4"
inflates; one given "a 2 means the answer described a situation but no action
the candidate took" does not. Changing a grade's meaning means changing the
text here, and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RubricDimension:
    key: str
    label: str
    anchors: dict[int, str]


HR_RUBRIC: tuple[RubricDimension, ...] = (
    RubricDimension(
        key="star_completeness",
        label="STAR completeness",
        anchors={
            0: "No recognisable situation, task, action, or result.",
            1: "A situation is mentioned but there is no task, action, or result.",
            2: "The answer describes a situation and task but no action taken by the candidate.",
            3: (
                "Situation, task, and the candidate's actions are present; "
                "the result is missing or vague."
            ),
            4: "Situation, task, the candidate's actions, and a clear result are all present.",
        },
    ),
    RubricDimension(
        key="specificity",
        label="Specificity",
        anchors={
            0: "Entirely generic; could be said about any job.",
            1: "Names a company or team but nothing about what was actually built or decided.",
            2: "Some concrete detail (a system, a decision, a constraint) but mostly general.",
            3: "Mostly concrete: named systems, real constraints, specific decisions.",
            4: "Fully concrete throughout; a listener could retell the story with the same facts.",
        },
    ),
    RubricDimension(
        key="quantified_outcome",
        label="Quantified outcome",
        anchors={
            0: "No outcome stated.",
            1: "An outcome is claimed but with no measure at all ('it went well').",
            2: "A direction is given without a number ('reduced latency', 'saved money').",
            3: "One concrete number or measure of the result.",
            4: "Before/after or comparative numbers that make the impact unambiguous.",
        },
    ),
    RubricDimension(
        key="ownership_language",
        label="Ownership language",
        anchors={
            0: "Only 'we' or passive voice; the candidate's own role is invisible.",
            1: "Mostly 'we'; the candidate's contribution is implied but never stated.",
            2: "Mixed 'I' and 'we'; the candidate's part is stated for at least one step.",
            3: (
                "The candidate's decisions and actions are clearly theirs; "
                "team credit is given where due."
            ),
            4: (
                "Unambiguous ownership of the key decisions, "
                "with honest attribution of what others did."
            ),
        },
    ),
)

INTERVIEWER_PERSONA = (
    "You are Maya, a warm and experienced recruiter running a screening interview. "
    "You are encouraging, concise, and genuinely curious. You never give feedback or "
    "scores during the interview; you listen, acknowledge briefly, and ask the next question."
)


def render_anchors() -> str:
    """The rubric as text for the scoring prompt. Deterministic, so it caches."""
    lines: list[str] = []
    for dim in HR_RUBRIC:
        lines.append(f"## {dim.label} (`{dim.key}`)")
        for score in range(5):
            lines.append(f"- {score}: {dim.anchors[score]}")
        lines.append("")
    return "\n".join(lines).rstrip()
