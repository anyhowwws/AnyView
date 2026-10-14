"""Tests for the adapter's pure parts. Nothing here talks to Vertex."""

import json
from types import SimpleNamespace

import pytest
from google.genai import errors, types

from anyview.llm import adapter
from anyview.llm.adapter import ModelError, Usage, VertexGemini


def test_usage_from_sdk_folds_thoughts_into_output_and_treats_none_as_zero():
    meta = SimpleNamespace(
        prompt_token_count=120,
        candidates_token_count=30,
        thoughts_token_count=200,
        cached_content_token_count=None,
    )
    assert adapter._usage_from(meta) == Usage(120, 230, 200, 0)
    assert adapter._usage_from(None) == Usage()


def test_usage_sink_receives_the_same_record_and_cannot_break_the_call(caplog, monkeypatch):
    seen = []
    monkeypatch.setattr(adapter, "usage_sink", seen.append)
    adapter._log_usage(
        session_id="s1", call="ask", model="m", usage=Usage(1, 2, 3, 4), latency_ms=5
    )
    assert seen == [
        {"session_id": "s1", "call": "ask", "model": "m", "latency_ms": 5, "input_tokens": 1,
         "output_tokens": 2, "thinking_tokens": 3, "cache_read": 4}
    ]  # fmt: skip

    def boom(record):
        raise RuntimeError("db down")

    monkeypatch.setattr(adapter, "usage_sink", boom)
    caplog.set_level("ERROR")
    adapter._log_usage(
        session_id="s1", call="ask", model="m", usage=Usage(), latency_ms=0
    )  # no raise
    assert "usage sink failed" in caplog.text


def test_usage_log_line_is_json_with_fixed_fields(caplog):
    caplog.set_level("INFO", logger="anyview.usage")
    adapter._log_usage(
        session_id="s1",
        call="score",
        model="gemini-3.1-pro-preview",
        usage=Usage(10, 5, 2, 8),
        latency_ms=42,
    )
    record = json.loads(caplog.records[-1].getMessage())
    assert record == {
        "session_id": "s1",
        "call": "score",
        "model": "gemini-3.1-pro-preview",
        "latency_ms": 42,
        "input_tokens": 10,
        "output_tokens": 5,
        "thinking_tokens": 2,
        "cache_read": 8,
    }


@pytest.mark.parametrize(
    "finish, expected",
    [
        (types.FinishReason.STOP, "end_turn"),
        (types.FinishReason.MAX_TOKENS, "max_tokens"),
        (types.FinishReason.SAFETY, "refusal"),
        (types.FinishReason.PROHIBITED_CONTENT, "refusal"),
        (types.FinishReason.OTHER, "other"),
        (None, "other"),
    ],
)
def test_stop_reason_translation(finish, expected):
    assert adapter._stop_reason(finish) == expected


def _api_error(code: int) -> errors.APIError:
    body = {"error": {"message": "x", "status": "TEST"}}
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, body)


@pytest.mark.parametrize(
    "exc, retryable, phrase",
    [
        (_api_error(429), True, "over quota"),
        (_api_error(503), True, "problem"),
        (_api_error(400), False, "could not be processed"),
        (ConnectionError("down"), True, "reach"),
        (ValueError("weird"), False, "Unexpected"),
    ],
)
def test_translate_maps_sdk_errors_to_model_error(exc, retryable, phrase):
    err = adapter._translate(exc)
    assert isinstance(err, ModelError)
    assert err.retryable is retryable
    assert phrase in err.user_message


def test_config_adds_thinking_allowance_and_sets_schema():
    model = VertexGemini.__new__(VertexGemini)  # skip __init__: no client needed
    schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    cfg = model._config(system="sys", effort="high", max_tokens=1000, output_schema=schema)
    assert cfg.system_instruction == "sys"
    assert cfg.max_output_tokens == 1000 + adapter._THINKING_ALLOWANCE["high"]
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.HIGH
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema == schema

    plain = model._config(system="sys", effort="low", max_tokens=400)
    assert plain.response_mime_type is None


def test_vertex_client_requires_project_id():
    with pytest.raises(RuntimeError):
        VertexGemini(project_id="", region="global", model="gemini-3.1-pro-preview")


def test_live_messages_become_plain_events(caplog):
    """The SDK's Live message shapes, mapped to LiveEvents (ADR 0030)."""
    from google.genai import types

    from anyview.llm.adapter import _VertexLive

    message = types.LiveServerMessage(
        server_content=types.LiveServerContent(
            model_turn=types.Content(
                parts=[types.Part(inline_data=types.Blob(data=b"\x01\x02", mime_type="audio/pcm"))]
            ),
            output_transcription=types.Transcription(text="Tell me"),
            input_transcription=types.Transcription(text="I led"),
            interrupted=True,
            turn_complete=True,
        ),
        tool_call=types.LiveServerToolCall(
            function_calls=[types.FunctionCall(id="c1", name="finish_question", args={})]
        ),
        usage_metadata=types.UsageMetadata(
            prompt_token_count=900, response_token_count=40, thoughts_token_count=10
        ),
    )
    live = _VertexLive(None, model="live-model", session_id="sess-1")
    with caplog.at_level("INFO", logger="anyview.usage"):
        events = live._translate(message)
    assert [e.kind for e in events] == [
        "audio",
        "harvey_text",
        "candidate_text",
        "interrupted",
        "turn_complete",
        "tool_call",
    ]
    assert events[0].audio == b"\x01\x02" and events[-1].call_id == "c1"
    row = json.loads(caplog.records[-1].message)
    assert row["call"] == "live" and row["input_tokens"] == 900 and row["output_tokens"] == 50
