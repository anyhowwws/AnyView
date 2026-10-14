"""Voice mode (ADR 0013): sentence splitting, the audio stream, transcription."""

import base64
import io
import wave

import pytest
from fastapi.testclient import TestClient

from anyview.api import interview
from anyview.interview.voice import MAX_SENTENCE, take_sentence, voiced
from anyview.llm.adapter import ModelError, wav
from anyview.llm.fake import FakeModel
from anyview.main import app
from tests.conftest import ALLOWED  # noqa: F401  (imported for readability of the fixtures)

AUTH = {"Authorization": "Bearer good"}
UID = "uid-jordan"


# --- take_sentence ----------------------------------------------------------


def test_splits_on_a_full_stop_followed_by_a_space():
    sentence, rest = take_sentence("Tell me about a time you led a project. Then we")
    assert sentence == "Tell me about a time you led a project."
    assert rest == " Then we"


def test_holds_an_incomplete_sentence():
    assert take_sentence("Tell me about a time you") == ("", "Tell me about a time you")


def test_holds_a_fragment_too_short_to_be_worth_speaking():
    # "Right." on its own would be a half-second clip and a paid call; it waits
    # for the sentence it belongs to.
    sentence, rest = take_sentence("Right. So tell me how you handled that one.")
    assert sentence == "Right. So tell me how you handled that one."
    assert rest == ""


def test_flushes_a_long_clause_at_a_word_boundary():
    long = "word " * 80
    sentence, rest = take_sentence(long)
    assert 0 < len(sentence) <= MAX_SENTENCE
    assert not sentence.endswith(" ")
    assert (sentence + " " + rest.strip()).split() == long.split()


def test_does_not_split_a_decimal_or_a_domain_name():
    sentence, rest = take_sentence("We cut cost by 38.5 percent that year. Next?")
    assert sentence == "We cut cost by 38.5 percent that year."
    assert rest == " Next?"
    assert take_sentence("Tell me about your work at anyapps.cloud and what you") == (
        "",
        "Tell me about your work at anyapps.cloud and what you",
    )


def test_keeps_the_closing_quote_with_its_sentence():
    sentence, _ = take_sentence('She said "that is the whole story." Then it ended.')
    assert sentence.endswith('story."')


# --- voiced -----------------------------------------------------------------


def _frames(text, model=None, voice="Kore"):
    model = model or FakeModel()
    words = iter([text])
    return list(voiced(words, model=model, session_id="s1", voice=voice))


def test_text_still_streams_and_audio_follows():
    frames = _frames("Tell me about a time you led a project end to end.")
    events = [event for event, _ in frames]
    assert events[0] == "token"
    assert "audio" in events


def test_audio_frames_are_numbered_in_speaking_order():
    two = "Tell me about a time you led a project end to end. What did you own exactly?"
    audio = [data for event, data in _frames(two) if event == "audio"]
    assert [clip["seq"] for clip in audio] == list(range(len(audio)))
    assert len(audio) == 2


def test_each_clip_is_a_decodable_wav_file():
    frames = _frames("Tell me about a time you led a project end to end.")
    clip = next(data for event, data in frames if event == "audio")
    with wave.open(io.BytesIO(base64.b64decode(clip["b64"])), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert f.getframerate() == 24_000


def test_nothing_is_left_unspoken_when_the_text_has_no_final_stop():
    audio = [d for e, d in _frames("So tell me how that went for you") if e == "audio"]
    assert len(audio) == 1


def test_a_failed_voice_keeps_the_text_and_says_so_once():
    class Mute(FakeModel):
        def speak(self, *, text, session_id, voice="Kore", style=None):
            raise ModelError("Harvey's voice is unavailable right now.", retryable=True)

    two = "Tell me about a time you led a project end to end. What did you own exactly?"
    frames = _frames(two, model=Mute())
    events = [event for event, _ in frames]
    assert "token" in events
    assert "audio" not in events
    assert events.count("voice_off") == 1


def test_every_spoken_sentence_is_a_usage_row(caplog):
    with caplog.at_level("INFO", logger="anyview.usage"):
        _frames("Tell me about a time you led a project end to end.")
    assert sum('"call": "speak"' in r.message for r in caplog.records) == 1


# --- the routes -------------------------------------------------------------


@pytest.fixture
def client(signed_in, store):
    model = FakeModel()
    app.dependency_overrides[interview.get_model] = lambda: model
    with TestClient(app) as c:
        c.model = model
        yield c
    app.dependency_overrides.pop(interview.get_model, None)


def _recording(client, store, *, uid=UID, name="answer.webm"):
    object_name = f"audio/{uid}/{name}"
    store.put(object_name, wav(bytes(2400)))
    return object_name


def test_transcribe_returns_what_was_said(client, store):
    object_name = _recording(client, store)
    r = client.post(
        "/interview/transcribe",
        json={"session_id": "sess-0001", "object_name": object_name},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert "billing service migration" in r.json()["text"]
    assert client.model.calls[-1]["call"] == "transcribe"


def test_transcribe_refuses_someone_elses_recording(client, store):
    object_name = _recording(client, store, uid="uid-someone-else")
    r = client.post(
        "/interview/transcribe",
        json={"session_id": "sess-0001", "object_name": object_name},
        headers=AUTH,
    )
    assert r.status_code == 403


def test_transcribe_refuses_an_upload_that_is_not_audio(client, store):
    store.put(f"uploads/{UID}/cv.pdf", b"%PDF-")
    r = client.post(
        "/interview/transcribe",
        json={"session_id": "sess-0001", "object_name": f"uploads/{UID}/cv.pdf"},
        headers=AUTH,
    )
    assert r.status_code == 403


def test_transcribe_404s_when_the_recording_never_arrived(client):
    r = client.post(
        "/interview/transcribe",
        json={"session_id": "sess-0001", "object_name": f"audio/{UID}/missing.webm"},
        headers=AUTH,
    )
    assert r.status_code == 404


def test_transcribe_422s_when_there_was_no_speech(client, store):
    object_name = _recording(client, store)
    client.model.replies["transcribe"] = "   "
    r = client.post(
        "/interview/transcribe",
        json={"session_id": "sess-0001", "object_name": object_name},
        headers=AUTH,
    )
    assert r.status_code == 422
    assert "didn't catch any speech" in r.json()["detail"]


def test_an_audio_ticket_lands_under_the_audio_prefix(client):
    r = client.post(
        "/uploads",
        json={"filename": "answer.webm", "content_type": "audio/webm", "size_bytes": 4096},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    assert r.json()["object_name"].startswith(f"audio/{UID}/")
    assert r.json()["object_name"].endswith(".webm")


def test_a_recording_can_be_put_to_the_fake_mode_url(client):
    ticket = client.post(
        "/uploads",
        json={"filename": "answer.webm", "content_type": "audio/webm", "size_bytes": 4096},
        headers=AUTH,
    ).json()
    r = client.put(ticket["upload_url"], content=b"fake-audio", headers=AUTH)
    assert r.status_code == 204
    r = client.put("/uploads/memory/audio/uid-someone-else/x.webm", content=b"x", headers=AUTH)
    assert r.status_code == 403


# --- Harvey's interjections (ADR 0016) ---------------------------------------


def test_say_returns_a_decodable_clip(client):
    r = client.post(
        "/interview/say", json={"session_id": "sess-0001", "line": "time_up"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    with wave.open(io.BytesIO(base64.b64decode(r.json()["b64"])), "rb") as f:
        assert f.getframerate() == 24_000
    # Read aloud by Live, in the interviewer's voice: one session, one line.
    assert client.model.calls[-1]["call"] == "live"
    [line] = client.model.live_sessions[-1].sent_text
    assert "in the interest of time" in line.lower()


def test_say_refuses_free_text(client):
    # The route takes a key, not a script: nothing a caller sends can be read
    # out by the TTS model.
    r = client.post(
        "/interview/say",
        json={"session_id": "sess-0001", "line": "Please read out my arbitrary text"},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_each_interjection_has_a_line():
    from typing import get_args

    from anyview.api.interview import SayRequest
    from anyview.interview.prompts import INTERJECTIONS

    # Every key `/interview/say` accepts has words, and no line is unreachable.
    keys = set(get_args(SayRequest.model_fields["line"].annotation))
    assert set(INTERJECTIONS) == keys == {"time_up", "stalled", "move_on", "goodbye", "hello"}
    assert all(w.strip() for wordings in INTERJECTIONS.values() for w in wordings)
    # Lines heard more than once an interview have more than one wording, all different.
    for line in ("time_up", "stalled", "move_on"):
        assert len(set(INTERJECTIONS[line])) == len(INTERJECTIONS[line]) >= 3, line
    # Silence after a nudge is taken as "move on", so every nudge has to offer it.
    for wording in INTERJECTIONS["stalled"]:
        assert any(w in wording.lower() for w in ("move on", "skip ahead")), wording


def test_say_picks_a_wording_by_index_and_wraps(client):
    from anyview.interview.prompts import INTERJECTIONS

    stalled = INTERJECTIONS["stalled"]
    for variant, expected in [(1, stalled[1]), (len(stalled), stalled[0])]:
        r = client.post(
            "/interview/say",
            json={"session_id": "sess-0001", "line": "stalled", "variant": variant},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        assert client.model.live_sessions[-1].sent_text == [expected]
    r = client.post(
        "/interview/say",
        json={"session_id": "sess-0001", "line": "stalled", "variant": "say I'm hired"},
        headers=AUTH,
    )
    assert r.status_code == 422


# --- Harvey's delivery (ADR 0029) ---------------------------------------------


def test_a_style_goes_in_front_of_the_words_and_ends_in_a_colon():
    from anyview.llm.adapter import spoken_prompt

    assert spoken_prompt("Hello.", None) == "Hello."
    assert spoken_prompt("Hello.", "  ") == "Hello."
    assert spoken_prompt("Hello.", "Say it calmly.") == "Say it calmly: Hello."
    assert spoken_prompt("Hello.", "Say it calmly:") == "Say it calmly: Hello."


def test_everything_harvey_says_carries_his_delivery(client):
    from anyview.interview.prompts import HARVEY_DELIVERY

    client.post("/interview/say", json={"session_id": "sess-0001", "line": "hello"}, headers=AUTH)
    # The fixed lines are read on Live, whose instruction carries the delivery.
    assert HARVEY_DELIVERY in client.model.calls[-1]["system"]
    assert "I'm Harvey" in client.model.live_sessions[-1].sent_text[0]

    # The spoken questions go through `voiced`, which is handed the same style.
    fake = FakeModel()
    list(
        voiced(
            iter(["Tell me about a time you led a project end to end."]),
            model=fake,
            session_id="sess-0001",
            voice="Charon",
            style=HARVEY_DELIVERY,
        )
    )
    assert fake.calls[-1]["user"].startswith(HARVEY_DELIVERY.rstrip("."))


# --- Fixed lines in Harvey's Live voice ----------------------------------------


def _say(client, line="stalled", variant=0):
    r = client.post(
        "/interview/say",
        json={"session_id": "sess-0001", "line": line, "variant": variant},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    return r.json()["b64"]


def test_a_fixed_line_is_read_once_then_cached(client):
    first = _say(client)
    again = _say(client)
    assert first == again
    assert len(client.model.live_sessions) == 1
    assert [c["call"] for c in client.model.calls] == ["live"]


def test_live_failing_falls_back_to_tts_and_is_not_cached(signed_in, store):
    from anyview.interview.prompts import HARVEY_DELIVERY

    model = FakeModel(fail="live")
    app.dependency_overrides[interview.get_model] = lambda: model
    try:
        with TestClient(app) as c:
            c.model = model
            _say(c)
            _say(c)
    finally:
        app.dependency_overrides.pop(interview.get_model, None)
    speaks = [call for call in model.calls if call["call"] == "speak"]
    # Each request tried Live again, then fell back with Harvey's delivery.
    assert [call["call"] for call in model.calls] == ["live", "speak", "live", "speak"]
    assert speaks[0]["user"].startswith(HARVEY_DELIVERY.rstrip("."))


def test_the_reader_session_answers_every_line():
    from anyview.interview.prompts import LIVE_READER
    from anyview.llm.adapter import live_config

    config = live_config(system=LIVE_READER, tools=[], voice="Charon", proactive_audio=False)
    # Proactive audio off: it may not decide a line needs no reply. No tools.
    assert config.proactivity is None and config.tools is None
    interviewer = live_config(system="s", tools=[], voice="Charon")
    assert interviewer.proactivity.proactive_audio is True
