"""A scripted stand-in for the real model.

Same two methods as `VertexGemini`, no network, no tokens. Tests use it to
drive the engine and the API deterministically; `ANYVIEW_FAKE_MODEL=1` runs the
whole app on it for a browser walk-through that costs nothing.

Replies are keyed by the `call` name (`plan`, `ask`, `score`, `ideal`) so a
test can script one kind of call without caring about the others.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from anyview.llm.adapter import Effort, ModelError, Reply, Usage

_FAKE_USAGE = Usage(input_tokens=100, output_tokens=50, thinking_tokens=20, cache_read=80)


class FakeModel:
    def __init__(self, replies: dict[str, Any] | None = None, *, fail: str | None = None) -> None:
        # `replies[call]` is a dict (returned as parsed JSON) or a str (returned as text).
        # `fail` names a call that should raise ModelError, to exercise error paths.
        self.replies = replies or {}
        self.fail = fail
        self.calls: list[dict[str, Any]] = []  # every invocation, for assertions

    def _record(self, call: str, session_id: str, system: str, user: str) -> None:
        self.calls.append({"call": call, "session_id": session_id, "system": system, "user": user})
        if self.fail == call:
            raise ModelError("fake failure", retryable=True)

    def generate(
        self,
        *,
        system: str,
        user: str,
        session_id: str,
        call: str,
        output_schema: dict[str, Any] | None = None,
        effort: Effort = "high",
        max_tokens: int = 4096,
        attachment: tuple[bytes, str] | None = None,
    ) -> Reply:
        self._record(call, session_id, system, user)
        if attachment is not None:
            self.calls[-1]["attachment"] = (len(attachment[0]), attachment[1])
        reply = self.replies.get(call, DEFAULTS[call])
        if isinstance(reply, dict):
            return Reply(
                text=json.dumps(reply), stop_reason="end_turn", usage=_FAKE_USAGE, data=reply
            )
        return Reply(text=str(reply), stop_reason="end_turn", usage=_FAKE_USAGE)

    def stream(
        self,
        *,
        system: str,
        user: str,
        session_id: str,
        call: str,
        effort: Effort = "low",
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        self._record(call, session_id, system, user)
        text = str(self.replies.get(call, DEFAULTS[call]))
        # Yield word by word so streaming code paths see more than one frame.
        for i, word in enumerate(text.split(" ")):
            yield word if i == 0 else " " + word


def default_plan(count: int) -> dict[str, Any]:
    competencies = ["ownership", "ambiguity", "conflict", "failure", "influence"]
    return {
        "questions": [
            {
                "text": f"Tell me about a time you demonstrated {competencies[i % 5]}.",
                "competency": competencies[i % 5],
                "rationale": "Scripted by FakeModel.",
            }
            for i in range(count)
        ]
    }


DEFAULTS: dict[str, Any] = {
    "extract": (
        "Jordan Lee — Cloud Solutions Architect\n\nAcme Corp (2021–present) — Senior Cloud "
        "Architect\n- Led migration of the billing service from VMs to Cloud Run, cutting monthly "
        "infra cost 38%.\n- Designed the Terraform module library now used by 6 product teams."
    ),
    "plan": default_plan(5),
    "ask": "Thanks for that. Next: tell me about a time you led a project end to end.",
    "score": {
        "dimensions": [
            {
                "dimension": "star_completeness",
                "score": 3,
                "evidence": "Situation, task, action present; result thin.",
            },
            {
                "dimension": "specificity",
                "score": 2,
                "evidence": "Named the team but not the system.",
            },
            {"dimension": "quantified_outcome", "score": 1, "evidence": "No numbers given."},
            {
                "dimension": "ownership_language",
                "score": 3,
                "evidence": "Used 'I' for the key decisions.",
            },
        ],
        "summary": "A solid structure that needs a measurable result.",
        "gaps": ["Add the metric that changed as a result."],
    },
    "ideal": {
        "answer": "Based on the resume: at Acme I led the migration of the billing service...",
        "cited_resume_lines": ["Led migration of billing service to Cloud Run"],
        "resume_has_material": True,
    },
}
