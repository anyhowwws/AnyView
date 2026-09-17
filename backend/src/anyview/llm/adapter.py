"""The one place the model SDK is imported (ADR 0004, superseded by 0007).

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

from google import genai
from google.genai import errors, types

log = logging.getLogger(__name__)
usage_log = logging.getLogger("anyview.usage")

Effort = Literal["low", "medium", "high"]

# Gemini counts its own reasoning ("thoughts") against max_output_tokens. The
# caller's max_tokens is the budget for the visible answer; the adapter adds
# room for thinking on top so a long think does not truncate a short answer.
_THINKING_ALLOWANCE: dict[Effort, int] = {"low": 2_048, "medium": 6_144, "high": 12_288}

# Finish reasons that mean "the model declined", as opposed to "ran out of room".
_REFUSAL_REASONS = {
    "SAFETY",
    "RECITATION",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "IMAGE_SAFETY",
}


@dataclass(frozen=True)
class Usage:
    """Token counts for one call, as plain ints. `output_tokens` includes the
    model's thinking tokens (billed as output); `thinking_tokens` breaks them
    out. `cache_read` is the part of the input served from Gemini's implicit
    prompt cache (discounted); there is no explicit cache write in this design."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read: int = 0


@dataclass(frozen=True)
class Reply:
    text: str
    stop_reason: str  # "end_turn" | "max_tokens" | "refusal" | "other"
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
    """What the engine depends on. `VertexGemini` and `FakeModel` both satisfy it.
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
        attachment: tuple[bytes, str] | None = None,
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


def _usage_from(meta: Any) -> Usage:
    """Map the SDK's usage metadata (fields are None when absent) to plain ints."""
    if meta is None:
        return Usage()
    answer = meta.candidates_token_count or 0
    thoughts = meta.thoughts_token_count or 0
    return Usage(
        input_tokens=meta.prompt_token_count or 0,
        output_tokens=answer + thoughts,
        thinking_tokens=thoughts,
        cache_read=meta.cached_content_token_count or 0,
    )


def _stop_reason(finish: Any) -> str:
    """Translate Gemini's finish reason into the small vocabulary the engine uses."""
    name = getattr(finish, "name", None) or (str(finish) if finish else "")
    if name == "STOP":
        return "end_turn"
    if name == "MAX_TOKENS":
        return "max_tokens"
    if name in _REFUSAL_REASONS:
        return "refusal"
    return "other"


def _translate(exc: Exception) -> ModelError:
    """Map SDK exceptions to one app exception with a message safe for the UI.
    Most specific first, so a 429 is not swallowed by the generic client branch."""
    if isinstance(exc, errors.APIError):
        if exc.code == 429:
            # Either a rate limit or an exhausted/zero quota. The raw message says
            # which; keep it in the logs.
            log.warning("model rate-limited or over quota: %s", exc.message)
            return ModelError(
                "The model is rate-limited or over quota right now. Please try again in a moment.",
                retryable=True,
            )
        if isinstance(exc, errors.ServerError):
            log.warning("model service error %s: %s", exc.code, exc.message)
            return ModelError("The model service had a problem. Please try again.", retryable=True)
        log.error("model request rejected %s: %s", exc.code, exc.message)
        return ModelError("The request could not be processed.")
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return ModelError("Could not reach the model service. Please try again.", retryable=True)
    log.exception("unexpected model error")
    return ModelError("Unexpected model error.")


class VertexGemini:
    """Gemini on Vertex AI. Auth is Application Default Credentials — locally
    from `gcloud auth application-default login`, on Cloud Run from the
    service account. No API key exists.

    Two models: `model` for judgement calls (plan, score, ideal) and
    `fast_model` for streamed conversational turns, where time-to-first-token
    matters more than depth. The Pro model spent ~450 thinking tokens and 5 s
    on a two-sentence greeting; Flash thinks near-zero at `low`.
    """

    def __init__(
        self, *, project_id: str, region: str, model: str, fast_model: str | None = None
    ) -> None:
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex model access")
        self.model = model
        self.fast_model = fast_model or model
        # Retry transient failures inside the SDK: a 429 "Resource exhausted"
        # in the middle of a ten-call report is a blip, not a quota problem.
        # 4 attempts with exponential backoff (1s, 2s, 4s) then give up.
        retry = types.HttpRetryOptions(
            attempts=4,
            initial_delay=1.0,
            max_delay=8.0,
            http_status_codes=[429, 500, 502, 503, 504],
        )
        self._client = genai.Client(
            vertexai=True,
            project=project_id,
            location=region,
            http_options=types.HttpOptions(retry_options=retry, timeout=120_000),  # ms
        )

    def _config(
        self,
        *,
        system: str,
        effort: Effort,
        max_tokens: int,
        output_schema: dict[str, Any] | None = None,
    ) -> types.GenerateContentConfig:
        # The system text is the stable prefix shared by every call in a session.
        # Gemini caches such prefixes implicitly (no breakpoint to set); hits show
        # up as `cache_read` in the usage line. Volatile content goes in `contents`.
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens + _THINKING_ALLOWANCE[effort],
            thinking_config=types.ThinkingConfig(thinking_level=effort),
        )
        if output_schema is not None:
            # Structured output: the API constrains generation to the schema, so
            # the text is valid JSON. No "please answer in JSON" hoping.
            config.response_mime_type = "application/json"
            config.response_json_schema = output_schema
        return config

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
        # `attachment` is (bytes, mime type) — a PDF the model reads natively.
        # Sent inline; uploads are capped at 10 MB, well inside the request limit.
        contents: Any = user
        if attachment is not None:
            data, mime = attachment
            contents = [types.Part.from_bytes(data=data, mime_type=mime), user]
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=self._config(
                    system=system, effort=effort, max_tokens=max_tokens, output_schema=output_schema
                ),
            )
        except Exception as exc:  # translated below; SDK types are not allowed out
            raise _translate(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = _usage_from(response.usage_metadata)
        _log_usage(
            session_id=session_id, call=call, model=self.model, usage=usage, latency_ms=latency_ms
        )

        # A blocked *prompt* yields no candidates at all; treat it as a refusal.
        if not response.candidates:
            feedback = getattr(response, "prompt_feedback", None)
            log.warning("prompt blocked: %s", getattr(feedback, "block_reason", "unknown"))
            return Reply(text="", stop_reason="refusal", usage=usage)

        stop = _stop_reason(response.candidates[0].finish_reason)
        text = response.text or ""
        data = None
        if output_schema is not None and stop == "end_turn":
            data = json.loads(text)
        return Reply(text=text, stop_reason=stop, usage=usage, data=data)

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
        last_chunk = None
        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.fast_model,
                contents=user,
                config=self._config(system=system, effort=effort, max_tokens=max_tokens),
            ):
                last_chunk = chunk
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            raise _translate(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        # The final chunk carries usage and the finish reason.
        meta = getattr(last_chunk, "usage_metadata", None)
        _log_usage(
            session_id=session_id,
            call=call,
            model=self.fast_model,
            usage=_usage_from(meta),
            latency_ms=latency_ms,
        )
        candidates = getattr(last_chunk, "candidates", None) or []
        if candidates and _stop_reason(candidates[0].finish_reason) == "refusal":
            raise ModelError("The model declined to answer this turn.")
