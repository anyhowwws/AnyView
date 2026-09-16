import pytest

from anyview.llm.adapter import ModelError
from anyview.llm.fake import DEFAULTS, FakeModel


def test_generate_returns_parsed_dict_for_dict_replies():
    fake = FakeModel({"plan": {"questions": []}})
    reply = fake.generate(system="s", user="u", session_id="sid", call="plan", output_schema={})
    assert reply.data == {"questions": []}
    assert reply.stop_reason == "end_turn"
    assert fake.calls == [{"call": "plan", "session_id": "sid", "system": "s", "user": "u"}]


def test_stream_yields_more_than_one_frame():
    fake = FakeModel()
    frames = list(fake.stream(system="s", user="u", session_id="sid", call="ask"))
    assert len(frames) > 1
    assert "".join(frames) == DEFAULTS["ask"]


def test_fail_raises_model_error_for_named_call_only():
    fake = FakeModel(fail="score")
    fake.generate(system="s", user="u", session_id="sid", call="plan")
    with pytest.raises(ModelError):
        fake.generate(system="s", user="u", session_id="sid", call="score")
