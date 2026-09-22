"""Server-sent events, hand-rolled (ADR 0005).

Wire format, one frame per event:

    event: token          data: {"text": "..."}
    event: audio          data: {"seq": 0, "b64": "..."}   (voice mode, ADR 0013)
    event: voice_off      data: {"message": "..."}         (voice mode, ADR 0013)
    event: done           data: {}
    event: error          data: {"message": "...", "retryable": true}
    : ping                (comment frame, every 15 s while waiting)

A producer yields `(event, data)` pairs; `tokens()` adapts a plain text stream
into the token frames that shape covers.

The model stream is a blocking iterator (the SDK is sync), so it runs in a
worker thread and hands chunks to the async response through a queue. That
is what lets the ping fire while the model is still thinking.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

from fastapi.responses import StreamingResponse

from anyview.interview.engine import EngineError
from anyview.llm.adapter import ModelError

log = logging.getLogger(__name__)

PING_SECONDS = 15
_END = object()  # sentinel: the producer thread has finished


def frame(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


Frame = tuple[str, Any]


def tokens(chunks: Iterator[str]) -> Iterator[Frame]:
    """The silent path: one token frame per text delta."""
    for text in chunks:
        yield ("token", {"text": text})


async def _events(frames: Iterator[Frame]) -> AsyncIterator[str]:
    q: queue.Queue[Frame | object] = queue.Queue()

    def produce() -> None:
        try:
            for event, data in frames:
                q.put((event, data))
            q.put(("done", {}))
        except ModelError as exc:
            q.put(("error", {"message": exc.user_message, "retryable": exc.retryable}))
        except EngineError as exc:
            q.put(("error", {"message": exc.user_message, "retryable": False}))
        except Exception:
            log.exception("unexpected error while streaming")
            q.put(("error", {"message": "Something went wrong.", "retryable": True}))
        finally:
            q.put(_END)

    threading.Thread(target=produce, daemon=True).start()
    loop = asyncio.get_running_loop()
    while True:
        try:
            # q.get blocks, so it runs in the default executor rather than the event loop.
            item = await loop.run_in_executor(None, q.get, True, PING_SECONDS)
        except queue.Empty:
            yield ": ping\n\n"
            continue
        if item is _END:
            return
        event, data = item  # type: ignore[misc]
        yield frame(event, data)


def stream_response(frames: Iterator[Frame]) -> StreamingResponse:
    return StreamingResponse(
        _events(frames),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # tells buffering proxies to pass frames through
        },
    )
