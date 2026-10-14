"""Harvey's fixed lines, spoken in his Live voice.

The hearing test, the nudges and the cut-ins (`prompts.INTERJECTIONS`) used to
come from the TTS model, while the interviewer is Gemini Live (ADR 0031). Both
use the same prebuilt voice name, but they are different models and do not
sound alike, so Harvey changed voice every time a fixed line played. Now one
short Live session reads each line aloud, in the same voice and with the same
delivery direction as the interviewer.

- **Word for word, or not at all.** The line is in the session's instruction
  and the only message is "read it". A clip is kept only when Live's transcript
  of it has the line's words; anything else (a paraphrase, or Live asking for
  "the line to say", which 3.8 once did) is refused and the line comes from TTS.
  3.8 sometimes sends no transcript of its own speech at all; the clip is then
  transcribed by the model that transcribes answers, once per line per instance.
- **Fallback.** If Live fails, is slow or says nothing, the line comes from the
  TTS model as before. A clip is never missing because of this.
- **Cached per instance.** The lines are the same for every user, so a clip
  read once is kept in memory (a few hundred KB in all) and later interviews
  cost no Live call. Not user data and not session state: losing it on a new
  instance only means reading the lines again. TTS fallbacks are not cached, so
  the next request tries Live again.
"""

from __future__ import annotations

import asyncio
import logging
import re

from anyview.interview.prompts import HARVEY_DELIVERY, READ, live_reader
from anyview.llm.adapter import LIVE_OUTPUT_RATE, Model, ModelError, wav
from anyview.uploads.extract import ExtractionError, audio_to_text

log = logging.getLogger(__name__)

# Connecting takes a second or two and a line is a few seconds of audio.
# Plus, now and then, transcribing the clip to check it.
READ_TIMEOUT_S = 20.0
# Live's transcript of its own speech can trail the audio; wait this long for it.
TRANSCRIPT_GRACE_S = 1.5

_cache: dict[tuple[str, str], bytes] = {}


async def spoken(model: Model, *, text: str, session_id: str, voice: str) -> bytes:
    """`text` as a WAV clip in Harvey's Live voice, or his TTS voice if Live fails."""
    key = (voice, text)
    if key in _cache:
        return _cache[key]
    try:
        clip = await asyncio.wait_for(
            _read_on_live(model, text=text, session_id=session_id, voice=voice), READ_TIMEOUT_S
        )
    except (ModelError, TimeoutError) as exc:
        log.warning("live could not read a fixed line, using tts: %s", exc)
    else:
        _cache[key] = clip
        return clip
    # `speak` is a blocking call; a thread keeps it off the event loop.
    return await asyncio.to_thread(
        model.speak, text=text, session_id=session_id, voice=voice, style=HARVEY_DELIVERY
    )


def _letters(text: str) -> str:
    """The letters alone. A transcript's punctuation never matches the script's,
    and its spacing is not to be trusted either ("needit", "moveon")."""
    return re.sub(r"[\W_]+", "", text.lower().replace("’", "'"))


async def _read_on_live(model: Model, *, text: str, session_id: str, voice: str) -> bytes:
    pcm = bytearray()
    said: list[str] = []
    # Proactive audio off where the model allows it, so Live never decides a line
    # needs no reply. Gemini 3.8 Live has it always on.
    async with model.live(
        system=live_reader(text),
        tools=[],
        session_id=session_id,
        voice=voice,
        proactive_audio=False,
    ) as reader:
        await reader.send_text(READ)
        events = aiter(reader.events())
        # `anext` on a fresh iterator each time would restart the session's
        # stream, so the one iterator is shared by both loops below.
        async for event in events:
            if event.kind == "audio":
                pcm.extend(event.audio)
            elif event.kind == "harvey_text":
                said.append(event.text)
            elif event.kind == "turn_complete" and pcm:
                break
        # The last words of the transcript may still be on their way.
        try:
            async with asyncio.timeout(TRANSCRIPT_GRACE_S):
                while _letters("".join(said)) != _letters(text):
                    event = await anext(events)
                    if event.kind == "harvey_text":
                        said.append(event.text)
        except (TimeoutError, StopAsyncIteration):
            pass
    if not pcm:
        raise ModelError("Live returned no audio for a fixed line.")
    clip = wav(bytes(pcm), rate=LIVE_OUTPUT_RATE)
    heard = "".join(said)
    if not heard:
        heard = await _transcribe(model, clip, session_id=session_id)
    if _letters(heard) != _letters(text):
        log.warning("live misread a fixed line: %r as %r", text, heard)
        raise ModelError("Live did not read the line as written.")
    return clip


async def _transcribe(model: Model, clip: bytes, *, session_id: str) -> str:
    """What the clip says, when Live sent no transcript of it."""
    try:
        # A blocking call; a thread keeps it off the event loop.
        return await asyncio.to_thread(
            audio_to_text,
            clip,
            "audio/wav",
            model=model,
            session_id=session_id,
            what="one line spoken by an interviewer",
        )
    except ExtractionError:
        return ""
