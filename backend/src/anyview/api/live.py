"""`WS /interview/live`: one question of a spoken interview, relayed to Gemini Live (ADR 0030).

The browser cannot talk to Live itself: Vertex accepts only IAM credentials,
and this project has no API key to mint browser tokens from. So the API holds
the Live session with its own identity and relays both directions. One socket
per question: the context stays small (Live re-bills it every turn), and no
socket outlives Live's ten-minute connection limit.

Browser → API
    text    {"token": "<Firebase ID token>", "session": <Session>}   first frame, once
    binary  microphone audio, 16 kHz 16-bit mono PCM                continuously
    text    {"type": "cue", "name": "silent"|"move_on"|"time_up"}    the browser's clock
    text    {"type": "end"}                                         give up; close the question

API → browser
    text    {"type": "ready"}                                       Live is open
    binary  Harvey's voice, 24 kHz 16-bit mono PCM
    text    {"type": "harvey"|"candidate", "text": "..."}           transcripts, in fragments
    text    {"type": "turn_complete"}                               Harvey stopped talking
    text    {"type": "interrupted"}                                 the candidate cut in
    text    {"type": "follow_up", "question": "...", "allowed": bool}
    text    {"type": "done", "answer": <Answer>}                    then the socket closes
    text    {"type": "error", "message": "...", "fallback": bool}

`fallback` true means Live itself failed: the browser carries on with the
turn-based voice path (ADR 0013) for this question.

The browser posts the `Answer` to `/interview/answer` exactly as a typed one,
so the session stays in the browser and the engine is unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from anyview.api.auth import Verifier, get_settings, get_verifier, user_from_token
from anyview.api.interview import get_model
from anyview.config import Settings
from anyview.interview.engine import EngineError
from anyview.interview.live import TOOLS, LiveTurn
from anyview.interview.models import Session
from anyview.llm.adapter import LiveSession, Model, ModelError

log = logging.getLogger(__name__)

# No router-level `current_user`: that reads a header a WebSocket cannot send.
# The first frame carries the token and is checked the same way.
router = APIRouter(prefix="/interview", tags=["interview"])

# Cues the browser may send. `begin` is the API's own.
BROWSER_CUES = frozenset({"silent", "move_on", "time_up"})
# 100 ms of 16 kHz 16-bit audio is 3.2 KB; anything far bigger is not a microphone.
MAX_AUDIO_FRAME = 64 * 1024
FIRST_FRAME_TIMEOUT_S = 15
# After Harvey closes the question, how long to let his last words arrive.
FINISH_GRACE_S = 4.0
# Live drops a connection at about ten minutes. A question is over well before.
MAX_TURN_S = 9 * 60


@router.websocket("/live")
async def live(
    ws: WebSocket,
    verifier: Annotated[Verifier, Depends(get_verifier)],
    settings: Annotated[Settings, Depends(get_settings)],
    model: Annotated[Model, Depends(get_model)],
) -> None:
    # CORS does not apply to WebSockets, so any page could open one with the
    # user's cookies. There are no cookies here (the token is in the first
    # frame), but checking the origin keeps other sites off this route anyway.
    origin = ws.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        await ws.close(code=1008)
        return
    await ws.accept()

    try:
        turn, session = await _open(ws, verifier, settings)
    except _Refused as refused:
        await _send(ws, {"type": "error", "message": refused.message, "fallback": False})
        await ws.close(code=1008)
        return

    try:
        async with model.live(
            system=turn.system,
            tools=TOOLS,
            session_id=session.session_id,
            voice=settings.harvey_voice,
        ) as harvey:
            await _send(ws, {"type": "ready"})
            await harvey.send_text(turn.cue("begin"))
            limit = min(MAX_TURN_S, turn.question.seconds + 240)
            gone = await _relay(ws, harvey, turn, limit=limit)
    except ModelError as exc:
        log.warning("live session failed for %s: %s", session.session_id, exc.user_message)
        await _send(ws, {"type": "error", "message": exc.user_message, "fallback": True})
        await _close(ws)
        return

    if gone:
        return  # the browser left; there is no one to send the answer to
    await _send(ws, {"type": "done", "answer": turn.answer().model_dump(mode="json")})
    await _close(ws)


class _Refused(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def _open(ws: WebSocket, verifier: Verifier, settings: Settings) -> tuple[LiveTurn, Session]:
    """Read the first frame: who is calling, and which question this is."""
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), FIRST_FRAME_TIMEOUT_S))
        token = str(first["token"])
        session = Session.model_validate(first["session"])
    except (TimeoutError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise _Refused("The interview couldn't start. Please try again.") from exc
    except WebSocketDisconnect as exc:
        raise _Refused("The connection closed.") from exc
    try:
        user_from_token(token, verifier, settings)
        return LiveTurn(session), session
    except HTTPException as exc:
        raise _Refused(str(exc.detail)) from exc
    except EngineError as exc:
        raise _Refused(exc.user_message) from exc


async def _relay(ws: WebSocket, harvey: LiveSession, turn: LiveTurn, *, limit: float) -> bool:
    """Pump both directions until the question is over. True if the browser left."""
    upstream = asyncio.create_task(_from_browser(ws, harvey, turn))
    downstream = asyncio.create_task(_from_live(ws, harvey, turn))
    done, pending = await asyncio.wait(
        {upstream, downstream}, timeout=limit, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    if not done:
        turn.moved_on = True  # the hard cap ended it
        return False
    for task in done:
        exc = task.exception()
        if exc is None:
            continue
        if isinstance(exc, ModelError):
            raise exc
        if not isinstance(exc, WebSocketDisconnect):
            # Most often a send to a browser that has just gone; logged in
            # full in case it was something else.
            log.warning("live relay stopped", exc_info=exc)
        return True
    return False


async def _from_browser(ws: WebSocket, harvey: LiveSession, turn: LiveTurn) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message.get("bytes") is not None:
            if len(message["bytes"]) <= MAX_AUDIO_FRAME:
                await harvey.send_audio(message["bytes"])
            continue
        try:
            data = json.loads(message.get("text") or "")
        except ValueError:
            continue
        if data.get("type") == "end":
            turn.moved_on = True
            return
        if data.get("type") == "cue" and data.get("name") in BROWSER_CUES:
            await harvey.send_text(turn.cue(data["name"]))


async def _from_live(ws: WebSocket, harvey: LiveSession, turn: LiveTurn) -> None:
    loop = asyncio.get_running_loop()
    events = aiter(harvey.events())
    finish_by: float | None = None
    while True:
        wait = None if finish_by is None else max(0.0, finish_by - loop.time())
        try:
            event = await asyncio.wait_for(anext(events), wait)
        except (TimeoutError, StopAsyncIteration):
            return
        if event.kind == "audio":
            await ws.send_bytes(event.audio)
        elif event.kind == "harvey_text":
            turn.said(event.text)
            await _send(ws, {"type": "harvey", "text": event.text})
        elif event.kind == "candidate_text":
            turn.heard(event.text)
            await _send(ws, {"type": "candidate", "text": event.text})
        elif event.kind == "interrupted":
            await _send(ws, {"type": "interrupted"})
        elif event.kind == "turn_complete":
            if turn.finished:
                return
            # Harvey has stopped talking: the browser starts the clock here.
            await _send(ws, {"type": "turn_complete"})
        elif event.kind == "tool_call":
            result = turn.tool(event.name, event.args)
            await harvey.send_tool_result(event.call_id, event.name, result)
            if event.name == "ask_follow_up":
                await _send(
                    ws,
                    {
                        "type": "follow_up",
                        "question": str(event.args.get("question", "")),
                        "allowed": bool(result.get("allowed")),
                    },
                )
            if turn.finished and finish_by is None:
                finish_by = loop.time() + FINISH_GRACE_S


async def _send(ws: WebSocket, data: dict[str, Any]) -> None:
    with contextlib.suppress(Exception):  # the browser may already be gone
        await ws.send_text(json.dumps(data))


async def _close(ws: WebSocket) -> None:
    with contextlib.suppress(Exception):
        await ws.close()
