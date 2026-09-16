"""The one place the Anthropic SDK is imported (ADR 0004).

Two operations, plain Python in and out:

    generate(...) -> Reply      one complete response, optionally parsed JSON
    stream(...)   -> Iterator   text deltas as they arrive; usage at the end

Everything else in the app talks in `str`, `dict`, and the small dataclasses
below. No SDK object leaves this module. This is an indirection layer, not a
framework: it does not compose prompts or retry business logic.

Every call writes exactly one usage line to the `anyview.usage` logger as JSON.
In Phase 0 that is the "usage row" (Cloud Logging picks it up); Phase 1 writes
the same fields to a table.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

import anthropic

log = logging.getLogger(__name__)
usage_log = logging.getLogger("anyview.usage")

Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Usage:
    """Token counts for one call, as plain ints. `cache_read` is the part of the
    input served from the prompt cache (~10% price); `cache_write` is what was
    newly cached this call (~125% price)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass(frozen=True)
class Reply:
    text: str
    stop_reason: str  # "end_turn" | "max_tokens" | "refusal" | ...
    usage: Usage
    data: dict[str, Any] | None = None  # parsed JSON when output_schema was given

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class ModelError(Exception):
    """Anything that stops us getting a usable reply. `user_message` is safe to
    show in the browser; the original exception is chained for logs."""

    def __init__(self, user_message: str, *, retryable: bool = False) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable


class Model(Protocol):
    """What the engine depends on. `VertexClaude` and `FakeModel` both satisfy it.
    A Protocol is a structural interface: any class with these two methods fits,
    no inheritance needed."""

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
    ) -> Reply: ...

    def stream(
        self,
        *,
        system: str,
        user: str,
        session_id: str,
        call: str,
        effort: Effort = "low",
        max_tokens: int = 1024,
    ) -> Iterator[str]: ...


def _log_usage(*, session_id: str, call: str, model: str, usage: Usage, latency_ms: int) -> None:
    usage_log.info(
        json.dumps(
            {
                "session_id": session_id,
                "call": call,
                "model": model,
                "latency_ms": latency_ms,
                **asdict(usage),
            },
            sort_keys=True,
        )
    )


def _usage_from(sdk_usage: Any) -> Usage:
    # The SDK returns None for cache fields when caching was not involved.
    return Usage(
        input_tokens=sdk_usage.input_tokens or 0,
        output_tokens=sdk_usage.output_tokens or 0,
        cache_read=getattr(sdk_usage, "cache_read_input_tokens", None) or 0,
        cache_write=getattr(sdk_usage, "cache_creation_input_tokens", None) or 0,
    )


def _translate(exc: Exception) -> ModelError:
    """Map SDK exceptions to one app exception with a message safe for the UI.
    Most specific first, so a 429 is not swallowed by the generic status branch."""
    if isinstance(exc, anthropic.RateLimitError):
        return ModelError(
            "The model is busy right now. Please try again in a moment.", retryable=True
        )
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500:
            return ModelError("The model service had a problem. Please try again.", retryable=True)
        log.error("model request rejected: %s", exc.message)
        return ModelError("The request could not be processed.")
    if isinstance(exc, anthropic.APIConnectionError):
        return ModelError("Could not reach the model service. Please try again.", retryable=True)
    return ModelError("Unexpected model error.")


class VertexClaude:
    """Claude on Vertex AI. Auth is Application Default Credentials — locally
    from `gcloud auth application-default login`, on Cloud Run from the
    service account. No API key exists."""

    def __init__(self, *, project_id: str, region: str, model: str) -> None:
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex model access")
        self.model = model
        self._client = anthropic.AnthropicVertex(project_id=project_id, region=region)

    def _system_block(self, system: str) -> list[dict[str, Any]]:
        # The system text is the stable prefix of every call in a session, so it
        # is the cache breakpoint. Volatile content (the answer being scored, the
        # question being asked) goes in the user turn, after the breakpoint.
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

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
    ) -> Reply:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": self._system_block(system),
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        if output_schema is not None:
            # Structured output: the API guarantees the text block is valid JSON
            # matching the schema. No prefill, no "please answer in JSON" hoping.
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": output_schema}

        started = time.monotonic()
        try:
            message = self._client.messages.create(**kwargs)
        except Exception as exc:  # translated below; SDK types are not allowed out
            raise _translate(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = _usage_from(message.usage)
        _log_usage(
            session_id=session_id, call=call, model=self.model, usage=usage, latency_ms=latency_ms
        )

        text = "".join(block.text for block in message.content if block.type == "text")
        data = None
        if output_schema is not None and message.stop_reason == "end_turn":
            data = json.loads(text)
        return Reply(
            text=text, stop_reason=message.stop_reason or "end_turn", usage=usage, data=data
        )

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
        started = time.monotonic()
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=self._system_block(system),
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
            ) as stream:
                # `yield` inside the `with` keeps the connection open while the
                # caller consumes deltas. The final message (with usage) is only
                # available after the stream is exhausted.
                yield from stream.text_stream
                final = stream.get_final_message()
        except Exception as exc:
            raise _translate(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_usage(
            session_id=session_id,
            call=call,
            model=self.model,
            usage=_usage_from(final.usage),
            latency_ms=latency_ms,
        )
        if final.stop_reason == "refusal":
            raise ModelError("The model declined to answer this turn.")
