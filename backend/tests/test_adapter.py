"""Tests for the adapter's pure parts. Nothing here talks to Agent Platform."""

import json
from types import SimpleNamespace

import httpx
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
        (httpx.ReadTimeout("slow"), True, "too long"),
        (httpx.ConnectError("refused"), True, "reach"),
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
    """The SDK's Live message shapes, mapped to LiveEvents (ADR 0031)."""
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


# --- The report's calls fail fast and fall back (ADR 0039) --------------------


class _Stub:
    """A stand-in for the SDK client: answers each call from a script, and
    remembers which model and per-request options each call used."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.levels = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append((model, config.http_options))
        self.levels.append(config.thinking_config.thinking_level)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(
            usage_metadata=None,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"))],
            text=step,
        )


def _vertex(stub):
    model = VertexGemini.__new__(VertexGemini)  # skip __init__: no client needed
    model.model, model.fast_model, model.fallback_model = "pro", "lite", "flash"
    model._client = stub
    return model


def _ask(model, **extra):
    return model.generate(system="s", user="u", session_id="sess-0001", call="score", **extra)


def test_a_plain_call_uses_the_clients_defaults_and_never_falls_back():
    stub = _Stub(_api_error(503))
    with pytest.raises(ModelError):
        _ask(_vertex(stub))
    assert [(m, o) for m, o in stub.calls] == [("pro", None)]


def test_a_fallback_call_has_a_tight_timeout_and_one_retry_budget():
    stub = _Stub("fine")
    assert _ask(_vertex(stub), fallback=True).text == "fine"
    ((model, options),) = stub.calls
    assert model == "pro"
    assert options.timeout == adapter.TIGHT_TIMEOUT_MS
    assert options.retry_options.attempts == adapter.TIGHT_ATTEMPTS


def test_a_call_with_a_deadline_gets_one_long_try_then_the_tight_fallback():
    stub = _Stub(_api_error(504), "from flash")
    assert (
        _ask(_vertex(stub), fallback=True, deadline_ms=adapter.EXTRACT_DEADLINE_MS).text
        == "from flash"
    )
    (_, first), (_, second) = stub.calls
    assert first.timeout == adapter.EXTRACT_DEADLINE_MS and first.retry_options.attempts == 1
    assert second.timeout == adapter.TIGHT_TIMEOUT_MS  # the fallback is not given the long one


@pytest.mark.parametrize("failure", [_api_error(504), _api_error(429), httpx.ReadTimeout("slow")])
def test_a_struggling_model_hands_the_call_to_the_fallback(failure, caplog):
    stub = _Stub(failure, "from flash")
    with caplog.at_level("WARNING"):
        assert _ask(_vertex(stub), fallback=True, effort="high").text == "from flash"
    assert [m for m, _ in stub.calls] == ["pro", "flash"]
    assert "trying flash" in caplog.text
    # The judgement model was asked at the caller's effort; the fallback at the quick one.
    assert stub.levels == [types.ThinkingLevel.HIGH, types.ThinkingLevel.LOW]


def test_a_failing_fallback_is_the_error_the_caller_sees():
    stub = _Stub(_api_error(504), _api_error(429))
    with pytest.raises(ModelError, match="rate-limited"):
        _ask(_vertex(stub), fallback=True)
    assert len(stub.calls) == 2  # one try on each model, no more


def test_a_bad_request_is_not_sent_to_the_fallback():
    stub = _Stub(_api_error(400))
    with pytest.raises(ModelError, match="could not be processed"):
        _ask(_vertex(stub), fallback=True)
    assert [m for m, _ in stub.calls] == ["pro"]
