"""Tests for the adapter's pure parts. Nothing here talks to Vertex."""

import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from anyview.llm import adapter
from anyview.llm.adapter import ModelError, Usage, VertexClaude


def test_usage_from_sdk_treats_missing_cache_fields_as_zero():
    sdk_usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=30,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
    )
    assert adapter._usage_from(sdk_usage) == Usage(120, 30, 0, 0)


def test_usage_log_line_is_json_with_fixed_fields(caplog):
    caplog.set_level("INFO", logger="anyview.usage")
    adapter._log_usage(
        session_id="s1",
        call="score",
        model="claude-opus-5",
        usage=Usage(10, 5, 8, 0),
        latency_ms=42,
    )
    record = json.loads(caplog.records[-1].getMessage())
    assert record == {
        "session_id": "s1",
        "call": "score",
        "model": "claude-opus-5",
        "latency_ms": 42,
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read": 8,
        "cache_write": 0,
    }


def _status_error(status: int) -> anthropic.APIStatusError:
    # Build the SDK's exception the way the SDK would, from a fake HTTP response.
    request = httpx.Request("POST", "https://example.invalid/v1/messages")
    response = httpx.Response(status, request=request, json={"error": {"message": "x"}})
    cls = {429: anthropic.RateLimitError, 400: anthropic.BadRequestError}.get(
        status, anthropic.APIStatusError
    )
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    "exc, retryable, phrase",
    [
        (_status_error(429), True, "busy"),
        (_status_error(503), True, "problem"),
        (_status_error(400), False, "could not be processed"),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://x.invalid")),
            True,
            "reach",
        ),
        (ValueError("weird"), False, "Unexpected"),
    ],
)
def test_translate_maps_sdk_errors_to_model_error(exc, retryable, phrase):
    err = adapter._translate(exc)
    assert isinstance(err, ModelError)
    assert err.retryable is retryable
    assert phrase in err.user_message


def test_vertex_client_requires_project_id():
    with pytest.raises(RuntimeError):
        VertexClaude(project_id="", region="global", model="claude-opus-5")
