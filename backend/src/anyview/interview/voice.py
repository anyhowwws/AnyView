"""Donna's side of voice mode: spoken audio interleaved with the text she types.

The `ask` stream already yields text deltas. Waiting for the whole answer
before synthesising would put a two-second silence at the top of every
question, so this splits the text into sentences as it arrives and sends each
one to the TTS model while the next is still streaming:

    event: token   data: {"text": "Tell me about a time"}
    event: audio   data: {"seq": 0, "b64": "<a WAV file>"}
    event: voice_off data: {"message": "..."}        (synthesis failed; text is fine)

Synthesis is slower than the text stream, so it runs in a small thread pool.
Futures are kept in a queue and emitted strictly in submission order, which is
the order the sentences must be heard in. Text never waits for audio: token
frames keep flowing while sentences are still being spoken.
"""

from __future__ import annotations

import base64
import logging
import re
from collections import deque
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from anyview.llm.adapter import Model, ModelError

log = logging.getLogger(__name__)

# Two sentences in flight is enough to stay ahead of playback without queueing
# up paid calls for text the listener may never reach.
VOICE_WORKERS = 2
# Below this, a "sentence" is a fragment like "Right." or an abbreviation such
# as "e.g." — hold it and let it join the next one rather than paying for a
# clip that lasts half a second.
MIN_SENTENCE = 24
# A long clause with no punctuation still has to be spoken eventually; flush at
# a word boundary rather than letting the buffer grow to the end of the turn.
MAX_SENTENCE = 240

# A terminator, plus any closing quote or bracket that belongs with it, followed
# by whitespace or the end of the buffer. Requiring that trailing space is what
# keeps "3.5" and "anyapps.cloud" in one piece.
_END = re.compile(r"""[.!?…]["'”’)\]]*(?=\s|$)|\n""")

Frame = tuple[str, Any]


def take_sentence(buffer: str) -> tuple[str, str]:
    """Split the first complete sentence off the front of `buffer`.

    Returns `(sentence, rest)`, with `sentence` empty when the buffer does not
    hold a whole one yet. Kept pure so the splitting rules can be tested on
    their own, without a model.
    """
    for match in _END.finditer(buffer):
        end = match.end()
        if end >= MIN_SENTENCE:
            return buffer[:end].strip(), buffer[end:]

    if len(buffer) >= MAX_SENTENCE:
        cut = buffer.rfind(" ", 0, MAX_SENTENCE)
        if cut > 0:
            return buffer[:cut].strip(), buffer[cut:]
    return "", buffer


def _audio_frame(seq: int, audio: bytes) -> Frame:
    # SSE is a text protocol, so the WAV bytes travel base64-encoded. That costs
    # a third more bytes than the raw file and saves a second connection.
    return ("audio", {"seq": seq, "b64": base64.b64encode(audio).decode("ascii")})


def voiced(chunks: Iterator[str], *, model: Model, session_id: str, voice: str) -> Iterator[Frame]:
    """Wrap a text stream so it also carries Donna's voice.

    Yields the same token frames as the silent path, plus one audio frame per
    sentence. If synthesis fails, the text keeps streaming and a single
    `voice_off` frame tells the browser to stop waiting for audio.
    """
    pending: deque[tuple[int, Future[bytes]]] = deque()
    buffer = ""
    spoken = 0
    voice_failed = False

    # `with` shuts the pool down when the generator is closed — which is what
    # happens when the listener navigates away mid-question.
    with ThreadPoolExecutor(max_workers=VOICE_WORKERS, thread_name_prefix="tts") as pool:

        def say(sentence: str) -> None:
            nonlocal spoken
            pending.append(
                (
                    spoken,
                    pool.submit(model.speak, text=sentence, session_id=session_id, voice=voice),
                )
            )
            spoken += 1

        def ready(*, block: bool) -> Iterator[Frame]:
            """Emit finished clips in order. `block=False` between tokens so the
            text stream never stalls behind a slow synthesis call."""
            nonlocal voice_failed
            while pending and (block or pending[0][1].done()):
                seq, future = pending.popleft()
                try:
                    yield _audio_frame(seq, future.result())
                except ModelError as exc:
                    if not voice_failed:
                        voice_failed = True
                        log.warning("voice mode off for %s: %s", session_id, exc.user_message)
                        yield ("voice_off", {"message": exc.user_message})

        for text in chunks:
            yield ("token", {"text": text})
            buffer += text
            while not voice_failed:
                sentence, buffer = take_sentence(buffer)
                if not sentence:
                    break
                say(sentence)
            yield from ready(block=False)

        tail = buffer.strip()
        if tail and not voice_failed:
            say(tail)
        yield from ready(block=True)
