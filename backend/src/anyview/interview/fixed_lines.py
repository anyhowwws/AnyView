"""Harvey's fixed lines, spoken in his Live voice.

The hearing test, the nudges and the cut-ins (`prompts.INTERJECTIONS`) used to
come from the TTS model, while the interviewer is Gemini Live (ADR 0031). Both
use the same prebuilt voice name, but they are different models and do not
sound alike, so Harvey changed voice every time a fixed line played. Now one
short Live session reads each line aloud, in the same voice and with the same
delivery direction as the interviewer.

- **Word for word.** The session's only instruction is to say the text it is
  sent. Live can still paraphrase; what it actually said is logged when it
  differs, so drift is visible.
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

from anyview.interview.prompts import HARVEY_DELIVERY, LIVE_READER
from anyview.llm.adapter import LIVE_OUTPUT_RATE, Model, ModelError, wav

log = logging.getLogger(__name__)

# Connecting takes a second or two and a line is a few seconds of audio.
READ_TIMEOUT_S = 15.0

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


def _words(text: str) -> list[str]:
    """The words alone: a transcript's punctuation never matches the script's."""
    return re.findall(r"[\w']+", text.lower().replace("’", "'"))


async def _read_on_live(model: Model, *, text: str, session_id: str, voice: str) -> bytes:
    pcm = bytearray()
    said: list[str] = []
    # Proactive audio off where the model allows it, so Live never decides a line
    # needs no reply. Gemini 3.8 Live has it always on and still read every line
    # word for word when tried (2026-10-14).
    async with model.live(
        system=LIVE_READER, tools=[], session_id=session_id, voice=voice, proactive_audio=False
    ) as reader:
        await reader.send_text(text)
        async for event in reader.events():
            if event.kind == "audio":
                pcm.extend(event.audio)
            elif event.kind == "harvey_text":
                said.append(event.text)
            elif event.kind == "turn_complete" and pcm:
                break
    if not pcm:
        raise ModelError("Live returned no audio for a fixed line.")
    heard = "".join(said)
    if heard and _words(heard) != _words(text):
        log.info("live read a fixed line differently: %r as %r", text, heard)
    return wav(bytes(pcm), rate=LIVE_OUTPUT_RATE)
