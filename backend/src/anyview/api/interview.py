"""Interview routes. The browser owns the session and posts it back each turn."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from anyview.api.sse import stream_response
from anyview.interview import engine
from anyview.interview.models import Answer, Report, Session, Setup, State
from anyview.llm.adapter import Model

router = APIRouter(prefix="/interview", tags=["interview"])


def get_model() -> Model:  # overridden in main.py and in tests
    raise NotImplementedError


ModelDep = Annotated[Model, Depends(get_model)]


class StartRequest(BaseModel):
    session_id: str
    setup: Setup


class AnswerRequest(BaseModel):
    session: Session
    answer: Answer


@router.post("/start", response_model=Session)
def start(body: StartRequest, model: ModelDep) -> Session:
    return engine.start(body.setup, session_id=body.session_id, model=model)


@router.post("/ask")
def ask(session: Session, model: ModelDep):
    # Validate state before opening the stream so a bad session is a plain 409,
    # not an error frame inside a 200.
    engine.require_state(session, State.ASK)
    return stream_response(engine.ask(session, model=model))


@router.post("/answer", response_model=Session)
def answer(body: AnswerRequest) -> Session:
    return engine.submit_answer(body.session, body.answer)


@router.post("/report", response_model=Report)
def report(session: Session, model: ModelDep) -> Report:
    return engine.finish(session, model=model)
