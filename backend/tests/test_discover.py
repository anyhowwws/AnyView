"""Discover's pure parts: prompts, history trimming, citation filtering. No DB."""

from anyview.brain.discover import (
    DONNA_DELIVERY,
    MAX_HISTORY_TURNS,
    SPOKEN_NOTE,
    DiscoverRequest,
    Turn,
    answer,
    cited,
    for_speech,
    group_labels,
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


# --- speak mode (ADR 0030) ----------------------------------------------------


def test_for_speech_drops_labels_and_markdown():
    assert for_speech("The billing migration [P1] and **on-call** [P1, S1].") == (
        "The billing migration and on-call."
    )
    assert for_speech("- Terraform [K1]\n- Cloud Run\n2. GKE") == "Terraform. Cloud Run. GKE."
    assert for_speech("[P1]") == ""  # nothing left to say: no clip is paid for


def test_a_typed_question_is_never_spoken():
    fake = FakeModel()
    request = DiscoverRequest(conversation_id="conv-12345678", question="What have I led?")
    frames = list(answer(request, garden="G", labels=LABELS, model=fake, voice="Kore"))
    assert "audio" not in {e for e, _ in frames}
    assert [c["call"] for c in fake.calls] == ["discover"]
    assert SPOKEN_NOTE not in fake.calls[0]["user"]


def test_speak_mode_adds_clips_in_donnas_voice_without_the_labels():
    fake = FakeModel()
    request = DiscoverRequest(
        conversation_id="conv-12345678", question="What have I led?", voice=True
    )
    frames = list(answer(request, garden="G", labels=LABELS, model=fake, voice="Kore"))
    events = [e for e, _ in frames]
    assert "audio" in events and events[-1] == "citations"
    assert [c["label"] for c in frames[-1][1]["entities"]] == ["P1", "S1"]  # unchanged
    assert fake.calls[0]["user"].endswith(SPOKEN_NOTE)
    spoken = [c for c in fake.calls if c["call"] == "speak"]
    assert spoken and all(c["system"] == "Kore" for c in spoken)
    for c in spoken:
        assert c["user"].startswith(DONNA_DELIVERY)
        assert "[" not in c["user"]


# --- ranges: the model sometimes cites a run of certificates as one bracket ----

SCREENSHOT = (
    "It also notes a 4/5 self-rating for Amazon Web Services [K44] alongside multiple "
    "AWS certifications [A1–A11, A13]."
)


def test_a_range_is_cited_label_by_label():
    labels = {f"A{n}": f"a-{n}" for n in range(1, 14)} | {"K44": "k-44"}
    assert [c["label"] for c in cited(SCREENSHOT, labels)] == (
        ["K44"] + [f"A{n}" for n in range(1, 12)] + ["A13"]
    )


def test_a_range_is_never_read_aloud():
    assert for_speech(SCREENSHOT) == (
        "It also notes a 4/5 self-rating for Amazon Web Services alongside multiple "
        "AWS certifications."
    )


def test_group_labels_spells_out_ranges_and_refuses_nonsense():
    assert group_labels("A1-3, P2") == ["A1", "A2", "A3", "P2"]
    assert group_labels("A1 — A2") == ["A1", "A2"]
    assert group_labels("A5–A2") == ["A5"]  # backwards
    assert group_labels("A1–P3") == ["A1"]  # across kinds
    assert group_labels("A1–A500") == ["A1"]  # not a citation anyone means


def test_donna_answers_in_english_and_only_about_the_garden():
    # ADR 0044: English only, her own scope, protected topics, distress.
    from anyview.brain.discover import system_prompt

    text = system_prompt("[P1] Something")
    assert "Answer in English" in text
    assert "you can only help with their garden" in text
    assert "pregnancy" in text and "emergency services" in text
