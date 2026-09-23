"""Discover's pure parts: prompts, history trimming, citation filtering. No DB."""

from anyview.brain.discover import (
    MAX_HISTORY_TURNS,
    DiscoverRequest,
    Turn,
    answer,
    cited,
    system_prompt,
    user_prompt,
)
from anyview.llm.fake import FakeModel

LABELS = {"R1": "role-1", "P1": "proj-1", "S1": "story-1"}


def test_cited_keeps_real_labels_in_first_mention_order():
    text = "See [S1] and [P1]. Again [P1, S1], and [R1,P1]. Not [P9], not [X], not P1."
    assert [c["label"] for c in cited(text, LABELS)] == ["S1", "P1", "R1"]
    assert cited(text, LABELS)[0] == {"label": "S1", "id": "story-1", "kind": "story"}


def test_cited_drops_invented_labels():
    assert cited("Your Bedrock project [P9] and [K4].", LABELS) == []


def test_system_prompt_carries_the_garden_and_the_rules():
    s = system_prompt("## [R1] Architect at Acme")
    assert "<digital_garden>\n## [R1] Architect at Acme\n</digital_garden>" in s
    assert "Never invent" in s and "list every match" in s


def test_user_prompt_without_history_is_just_the_question():
    assert user_prompt([], "What have I done with Bedrock?") == "What have I done with Bedrock?"


def test_user_prompt_keeps_only_recent_turns():
    history = [Turn(role="user" if i % 2 == 0 else "donna", text=f"turn {i}") for i in range(30)]
    u = user_prompt(history, "And then?")
    assert "turn 29" in u and f"turn {30 - MAX_HISTORY_TURNS}" in u
    assert f"turn {29 - MAX_HISTORY_TURNS}" not in u
    assert u.endswith("The candidate now asks: And then?")
    assert "Donna: turn 29" in u and "Candidate: turn 28" in u


def test_answer_streams_tokens_then_citations():
    fake = FakeModel()
    request = DiscoverRequest(conversation_id="conv-12345678", question="What have I led?")
    frames = list(answer(request, garden="G", labels=LABELS, model=fake))
    events = [e for e, _ in frames]
    assert set(events[:-1]) == {"token"} and events[-1] == "citations"
    text = "".join(d["text"] for e, d in frames if e == "token")
    assert "[P9]" in text  # the model's words pass through unedited…
    assert [c["label"] for c in frames[-1][1]["entities"]] == ["P1", "S1"]  # …links do not
    call = fake.calls[0]
    assert call["call"] == "discover" and call["session_id"] == "discover-conv-12345678"
