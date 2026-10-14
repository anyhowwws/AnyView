"""The one place the model SDK is imported (ADR 0004, superseded by 0007).

Four operations, plain Python in and out:

    generate(...) -> Reply      one complete response, optionally parsed JSON
    stream(...)   -> Iterator   text deltas as they arrive; usage at the end
    speak(...)    -> bytes      one sentence spoken aloud, as a WAV file (ADR 0013)
    live(...)     -> LiveSession  a two-way spoken conversation on Gemini Live (ADR 0030)

Everything else in the app talks in `str`, `dict`, and the small dataclasses
below. No SDK object leaves this module. This is an indirection layer, not a
framework: it does not compose prompts or retry business logic.

Every call writes exactly one usage line to the `anyview.usage` logger as JSON.
In Phase 0 that is the "usage row" (Cloud Logging picks it up); Phase 1 writes
the same fields to a table.
"""

from __future__ import annotations

import io
import json
import logging
import time
import wave
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from google import genai
from google.genai import errors, types

log = logging.getLogger(__name__)
usage_log = logging.getLogger("anyview.usage")

# Optional second destination for usage rows (the database, once one exists).
# main.py sets it; the adapter never imports the repository.
UsageSink = Callable[[dict[str, Any]], None]
usage_sink: UsageSink | None = None

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


# --- Live (ADR 0030) ----------------------------------------------------------
# What a Live session hands back, as plain data. `kind` says which fields mean
# something: audio carries `audio` (24 kHz 16-bit mono PCM), the two transcript
# kinds carry `text`, a tool call carries `call_id`, `name` and `args`.

LiveKind = Literal[
    "audio", "harvey_text", "candidate_text", "tool_call", "interrupted", "turn_complete"
]

# The microphone audio a Live session takes: raw 16-bit little-endian PCM, mono.
LIVE_INPUT_RATE = 16_000
LIVE_OUTPUT_RATE = 24_000


@dataclass(frozen=True)
class LiveEvent:
    kind: LiveKind
    audio: bytes = b""
    text: str = ""
    call_id: str = ""
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)


class LiveSession(Protocol):
    """One open Live conversation. `async` because it is a socket held open for
    minutes: the API relays the browser's microphone in while it relays
    Harvey's voice out, and neither may wait for the other."""

    async def send_audio(self, pcm: bytes) -> None: ...

    async def send_text(self, text: str) -> None: ...

    async def send_tool_result(self, call_id: str, name: str, result: dict[str, Any]) -> None: ...

    def events(self) -> AsyncIterator[LiveEvent]: ...


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
        fast: bool = False,
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

    def speak(
        self, *, text: str, session_id: str, voice: str, style: str | None = None
    ) -> bytes: ...

    def live(
        self, *, system: str, tools: list[dict[str, Any]], session_id: str, voice: str
    ) -> AbstractAsyncContextManager[LiveSession]: ...


def spoken_prompt(text: str, style: str | None) -> str:
    """The prompt a TTS model speaks. A style is plain-language direction put in
    front of the words, ending in a colon: "<how to say it>: <what to say>".
    Gemini TTS follows it as delivery rather than reading it out; a blank line
    in its place left the delivery nearly unchanged when measured (ADR 0029)."""
    if not style or not style.strip():
        return text
    return f"{style.strip().rstrip('.:')}: {text}"


def _log_usage(*, session_id: str, call: str, model: str, usage: Usage, latency_ms: int) -> None:
    record = {
        "session_id": session_id,
        "call": call,
        "model": model,
        "latency_ms": latency_ms,
        **asdict(usage),
    }
    usage_log.info(json.dumps(record, sort_keys=True))
    if usage_sink is not None:
        try:
            usage_sink(record)
        except Exception:  # a usage row must never fail the call it describes
            log.exception("usage sink failed")


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


def _live_usage_from(meta: Any) -> Usage:
    """Live reports usage with different field names from generate_content:
    `response_token_count` rather than `candidates_token_count`."""
    if meta is None:
        return Usage()
    answer = meta.response_token_count or 0
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


# --- Audio (ADR 0013) -------------------------------------------------------

# What Gemini's TTS models return when nothing says otherwise: raw 16-bit
# little-endian PCM, one channel. The mime type carries the sample rate, e.g.
# "audio/L16;rate=24000".
PCM_SAMPLE_RATE = 24_000


def _rate_from(mime: str | None) -> int:
    """Pull `rate=N` out of an audio mime type, falling back to the documented
    24 kHz. The parameters are `;`-separated, so this is a split, not a regex."""
    for part in (mime or "").split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key == "rate" and value.isdigit():
            return int(value)
    return PCM_SAMPLE_RATE


def wav(pcm: bytes, *, rate: int = PCM_SAMPLE_RATE) -> bytes:
    """Wrap raw PCM in a WAV container so a browser can decode it directly.

    The model hands back headerless samples, which no `<audio>` element or
    `decodeAudioData` call will touch. `wave` is in the standard library and
    writes the 44-byte header for us — no dependency, no bit-twiddling.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)  # 16-bit samples
        out.setframerate(rate)
        out.writeframes(pcm)
    return buffer.getvalue()


def _audio_part(response: Any) -> Any | None:
    """The first inline audio blob in a response, or None if it carries none."""
    for candidate in response.candidates or []:
        for part in getattr(candidate.content, "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data:
                return blob
    return None


class VertexGemini:
    """Gemini on Vertex AI. Auth is Application Default Credentials — locally
    from `gcloud auth application-default login`, on Cloud Run from the
    service account. No API key exists.

    Three models: `model` for judgement calls (plan, score, ideal),
    `fast_model` for streamed conversational turns, where time-to-first-token
    matters more than depth, and `tts_model` for Harvey's voice. The Pro model
    spent ~450 thinking tokens and 5 s on a two-sentence greeting; Flash thinks
    near-zero at `low`.
    """

    def __init__(
        self,
        *,
        project_id: str,
        region: str,
        model: str,
        fast_model: str | None = None,
        tts_model: str | None = None,
        live_model: str | None = None,
        live_region: str | None = None,
    ) -> None:
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex model access")
        self.model = model
        self.fast_model = fast_model or model
        # Live models are served from regions, not from `global` (ADR 0030), so
        # they get their own client; it is built on first use.
        self.live_model = live_model or "gemini-live-2.5-flash-native-audio"
        self._project_id = project_id
        self._live_region = live_region or "us-central1"
        self._live_client: genai.Client | None = None
        # A third model, for speech. Text models cannot synthesise audio and TTS
        # models cannot hold a conversation, so this is its own id (ADR 0013).
        self.tts_model = tts_model or "gemini-2.5-flash-preview-tts"
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
        fast: bool = False,
    ) -> Reply:
        # `attachment` is (bytes, mime type) — a PDF the model reads natively.
        # `fast` sends a mechanical call (finding a dump's sections, ADR 0019)
        # to the fast model instead of the judgement model.
        model = self.fast_model if fast else self.model
        # Sent inline; uploads are capped at 10 MB, well inside the request limit.
        contents: Any = user
        if attachment is not None:
            data, mime = attachment
            contents = [types.Part.from_bytes(data=data, mime_type=mime), user]
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=model,
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
            session_id=session_id, call=call, model=model, usage=usage, latency_ms=latency_ms
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

    def speak(
        self, *, text: str, session_id: str, voice: str = "Charon", style: str | None = None
    ) -> bytes:
        """One line of dialogue as a WAV file, spoken by a prebuilt Vertex voice.

        A TTS model takes no system instruction and does no thinking, so this
        builds its own config rather than reusing `_config`. `response_modalities`
        is what asks for audio instead of text; `voice` names one of Vertex's
        prebuilt speakers (Harvey's default is set by HARVEY_VOICE). `style` directs
        the delivery: see `spoken_prompt`.
        """
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=self.tts_model,
                contents=spoken_prompt(text, style),
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                        )
                    ),
                ),
            )
        except Exception as exc:
            raise _translate(exc) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        # Audio output is billed as output tokens, so it lands in the usage log
        # beside every other call. No exceptions, including this one.
        _log_usage(
            session_id=session_id,
            call="speak",
            model=self.tts_model,
            usage=_usage_from(response.usage_metadata),
            latency_ms=latency_ms,
        )

        blob = _audio_part(response)
        if blob is None:
            log.warning("tts returned no audio for %d characters", len(text))
            raise ModelError("Harvey's voice is unavailable right now.", retryable=True)
        return wav(blob.data, rate=_rate_from(blob.mime_type))

    # --- Live (ADR 0030) -------------------------------------------------------

    def live(
        self, *, system: str, tools: list[dict[str, Any]], session_id: str, voice: str = "Charon"
    ) -> AbstractAsyncContextManager[LiveSession]:
        """Open a spoken conversation. Use as `async with model.live(...) as session:`.

        Harvey speaks in a prebuilt voice and hears through the session's own
        voice-activity detection. `tools` are plain JSON-schema function
        declarations; the caller answers each call with `send_tool_result`.
        Both sides are transcribed, so the caller gets text without a second
        model call."""
        if self._live_client is None:
            self._live_client = genai.Client(
                vertexai=True, project=self._project_id, location=self._live_region
            )
        config = live_config(system=system, tools=tools, voice=voice)
        return self._live_session(config, session_id=session_id)

    @asynccontextmanager
    async def _live_session(
        self, config: types.LiveConnectConfig, *, session_id: str
    ) -> AsyncIterator[LiveSession]:
        assert self._live_client is not None
        try:
            async with self._live_client.aio.live.connect(
                model=self.live_model, config=config
            ) as session:
                yield _VertexLive(session, model=self.live_model, session_id=session_id)
        except ModelError:
            raise
        except Exception as exc:
            raise _translate(exc) from exc


def live_config(*, system: str, tools: list[dict[str, Any]], voice: str) -> types.LiveConnectConfig:
    """The Live session's settings (ADR 0030). A function of its own so a test
    can build it without credentials."""
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=system,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        tools=[
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters_json_schema=tool["parameters"],
                    )
                    for tool in tools
                ]
            )
        ],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Interview answers are full of thinking pauses. A low end-of-speech
        # sensitivity and a long silence before "they stopped" keep Harvey
        # from jumping in mid-thought; proactive audio lets him stay quiet
        # when a pause does end a turn.
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                silence_duration_ms=1_200,
            )
        ),
        proactivity=types.ProactivityConfig(proactive_audio=True),
    )


class _VertexLive:
    """`LiveSession` over the SDK's async session. SDK objects stay in here."""

    def __init__(self, session: Any, *, model: str, session_id: str) -> None:
        self._session = session
        self._model = model
        self._session_id = session_id
        self._started = time.monotonic()

    async def send_audio(self, pcm: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={LIVE_INPUT_RATE}")
        )

    async def send_text(self, text: str) -> None:
        # Realtime text, not `send_client_content`: newer Live models accept
        # client content only to seed history before the conversation starts.
        await self._session.send_realtime_input(text=text)

    async def send_tool_result(self, call_id: str, name: str, result: dict[str, Any]) -> None:
        await self._session.send_tool_response(
            function_responses=[types.FunctionResponse(id=call_id, name=name, response=result)]
        )

    async def events(self) -> AsyncIterator[LiveEvent]:
        # `receive()` yields one model turn and stops at its end, so it is read
        # in a loop. A pass that yields nothing means the server closed.
        while True:
            got = False
            try:
                async for message in self._session.receive():
                    got = True
                    for event in self._translate(message):
                        yield event
            except Exception as exc:
                raise _translate(exc) from exc
            if not got:
                return

    def _translate(self, message: Any) -> list[LiveEvent]:
        out: list[LiveEvent] = []
        if message.usage_metadata is not None:
            # Live bills the whole session context on every turn; one usage row
            # per report keeps that visible beside every other call.
            _log_usage(
                session_id=self._session_id,
                call="live",
                model=self._model,
                usage=_live_usage_from(message.usage_metadata),
                latency_ms=int((time.monotonic() - self._started) * 1000),
            )
        content = message.server_content
        if content is not None:
            for part in getattr(content.model_turn, "parts", None) or []:
                blob = getattr(part, "inline_data", None)
                if blob is not None and blob.data:
                    out.append(LiveEvent("audio", audio=blob.data))
            if content.output_transcription and content.output_transcription.text:
                out.append(LiveEvent("harvey_text", text=content.output_transcription.text))
            if content.input_transcription and content.input_transcription.text:
                out.append(LiveEvent("candidate_text", text=content.input_transcription.text))
            if content.interrupted:
                out.append(LiveEvent("interrupted"))
            if content.turn_complete:
                out.append(LiveEvent("turn_complete"))
        if message.tool_call is not None:
            for call in message.tool_call.function_calls or []:
                out.append(
                    LiveEvent(
                        "tool_call",
                        call_id=call.id or "",
                        name=call.name or "",
                        args=call.args or {},
                    )
                )
        if message.go_away is not None:
            log.info("live session %s told to go away: %s", self._session_id, message.go_away)
        return out
