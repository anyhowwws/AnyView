"""Manual turn-taking on Live (LIVE_TURNS=manual): an experiment, docs/live-manual-turns.md.

The default path (automatic detection, ADR 0032) is covered by test_live.py and
must not change; the first tests here pin that down.
"""

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from anyview.api import auth, interview
from anyview.config import Settings
from anyview.interview import engine
from anyview.interview.live import LiveTurn
from anyview.interview.models import Answer
from anyview.interview.prompts import CUT_INS, LIVE_TOOLS, live_system
from anyview.llm.adapter import live_config
from anyview.llm.fake import FAKE_FOLLOW_UP, FakeModel
from anyview.main import app


@pytest.fixture
def session(setup):
    return engine.start(setup, session_id="sess-manual", model=FakeModel())


def test_settings_default_to_auto(monkeypatch):
    monkeypatch.delenv("LIVE_TURNS", raising=False)
    assert Settings.from_env().live_turns == "auto"
    monkeypatch.setenv("LIVE_TURNS", "Manual please")
    assert Settings.from_env().live_turns == "auto"  # anything but "manual" is auto
    monkeypatch.setenv("LIVE_TURNS", "manual")
    assert Settings.from_env().live_turns == "manual"


def test_live_config_turns_detection_off_only_when_asked():
    auto = live_config(system="s", tools=LIVE_TOOLS, voice="Charon")
    detection = auto.realtime_input_config.automatic_activity_detection
    assert detection.disabled is None
    assert detection.silence_duration_ms == 1_200

    manual = live_config(system="s", tools=LIVE_TOOLS, voice="Charon", manual_turns=True)
    detection = manual.realtime_input_config.automatic_activity_detection
    assert detection.disabled is True
    # Barge-in stays as it is: the candidate can still talk over Harvey.
    assert manual.realtime_input_config.activity_handling is None
    assert manual.proactivity == types.ProactivityConfig(proactive_audio=True)


def test_auto_prompt_never_mentions_the_cut_in_cues(session):
    system = live_system(
        session.setup, questions=session.questions, answers=[], index=0, manual_turns=False
    )
    assert "[time_up]" not in system and "the room steps in\nand ends the question" in system
    manual = live_system(
        session.setup, questions=session.questions, answers=[], index=0, manual_turns=True
    )
    assert "[time_up]" in manual and "[move_on]" in manual
    assert "Let me stop you there" in manual


def test_last_question_cut_in_is_a_goodbye(session):
    last = len(session.questions) - 1
    system = live_system(
        session.setup, questions=session.questions, answers=[], index=last, manual_turns=True
    )
    assert "Let me stop you there" not in system
    assert "thank them for their time. No follow-up" in system


def test_cut_in_is_only_harveys_with_manual_turns(session):
    assert LiveTurn(session).cut_in("time_up") is None  # auto: the browser plays the clip
    turn = LiveTurn(session, manual_turns=True)
    assert turn.cut_in("time_up") == CUT_INS["time_up"]
    assert turn.cutting_in and turn.time_up and turn.moved_on
    # Once cut, no follow-up.
    assert turn.tool("ask_follow_up", {"question": "And?", "reason": "x"})["allowed"] is False


def test_the_candidates_next_question_closes_at_once_either_way(session):
    turn = LiveTurn(session, manual_turns=True)
    assert turn.cut_in("manual") is None
    assert turn.cut_in("Say I'm hired") is None  # unknown reasons are "manual"
    assert not turn.cutting_in and not turn.moved_on


# --- The socket ----------------------------------------------------------------


@pytest.fixture
def fake():
    return FakeModel()


@pytest.fixture
def manual_client(fake, signed_in):
    settings = app.dependency_overrides[auth.get_settings]()
    app.dependency_overrides[auth.get_settings] = lambda: dataclasses.replace(
        settings, live_turns="manual"
    )
    app.dependency_overrides[interview.get_model] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.pop(interview.get_model, None)


def _until(ws, kind):
    seen = []
    while True:
        frame = ws.receive()
        if frame.get("text") is None:
            continue
        data = json.loads(frame["text"])
        seen.append(data)
        if data["type"] == kind:
            return data, seen


def _speak(ws, frames=10):
    """One stretch of the candidate talking, as the browser marks it."""
    ws.send_text(json.dumps({"type": "activity", "state": "start"}))
    for _ in range(frames):
        ws.send_bytes(bytes(3_200))
    ws.send_text(json.dumps({"type": "activity", "state": "end"}))


def _open(ws, session):
    ws.send_text(json.dumps({"token": "good", "session": session.model_dump(mode="json")}))
    ready, _ = _until(ws, "ready")
    assert ready == {"type": "ready", "turns": "manual"}
    _until(ws, "turn_complete")


def test_manual_turns_end_to_end(manual_client, fake, session):
    with manual_client.websocket_connect("/interview/live") as ws:
        _open(ws, session)
        # Audio outside a marked turn is not an answer, however long.
        for _ in range(60):
            ws.send_bytes(bytes(3_200))
        _speak(ws)
        follow_up, _ = _until(ws, "follow_up")
        assert follow_up["question"] == FAKE_FOLLOW_UP
        _until(ws, "turn_complete")
        _speak(ws)
        done, _ = _until(ws, "done")

    live = fake.live_sessions[0]
    assert live.manual_turns is True
    # [begin] went inside a turn of its own, or Live would never answer it.
    assert live.signals[:3] == ["start", "text:[begin]", "end"]
    answer = Answer.model_validate(done["answer"])
    assert answer.cut_off is False and [f.question for f in answer.follow_ups] == [FAKE_FOLLOW_UP]


@pytest.mark.parametrize("reason", ["time_up", "move_on"])
def test_harvey_cuts_in_himself_mid_sentence(manual_client, fake, session, reason):
    with manual_client.websocket_connect("/interview/live") as ws:
        _open(ws, session)
        ws.send_text(json.dumps({"type": "activity", "state": "start"}))
        ws.send_bytes(bytes(3_200))
        # Time runs out while they are still talking: no `activity end` from the browser.
        ws.send_text(json.dumps({"type": "end", "reason": reason}))
        done, seen = _until(ws, "done")

    live = fake.live_sessions[0]
    # Their open turn carried the cue and ended: Harvey answers it, uninterrupted.
    assert live.signals[-3:] == ["start", f"text:[{reason}]", "end"]
    line = {"type": "harvey", "text": "Let me stop you there — we need to keep moving."}
    # The question closes once his line is over, whether or not he has called
    # `finish_question` by then.
    assert seen.index(line) < len(seen) - 1
    assert done["answer"]["cut_off"] is True


def test_activity_frames_are_ignored_on_auto(fake, signed_in, session):
    app.dependency_overrides[interview.get_model] = lambda: fake
    try:
        with TestClient(app).websocket_connect("/interview/live") as ws:
            ws.send_text(json.dumps({"token": "good", "session": session.model_dump(mode="json")}))
            ready, _ = _until(ws, "ready")
            _until(ws, "turn_complete")
            ws.send_text(json.dumps({"type": "activity", "state": "start"}))
            ws.send_text(json.dumps({"type": "activity", "state": "end"}))
            ws.send_text(json.dumps({"type": "end", "reason": "time_up"}))
            done, _ = _until(ws, "done")
    finally:
        app.dependency_overrides.pop(interview.get_model, None)
    assert ready == {"type": "ready", "turns": "auto"}
    # FakeLive raises on activity marks without manual turns; none reached it.
    assert fake.live_sessions[0].signals == []
    assert done["answer"]["cut_off"] is True
