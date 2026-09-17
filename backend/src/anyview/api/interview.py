"""Interview routes. The browser owns the session and posts it back each turn."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from anyview.api.auth import CurrentUser, current_user
from anyview.api.sse import stream_response
from anyview.api.uploads import get_store, object_prefix
from anyview.interview import engine
from anyview.interview.models import Answer, Report, Session, Setup, SetupInput, State
from anyview.llm.adapter import Model
from anyview.uploads.extract import ExtractionError, docx_to_text, pdf_to_text
from anyview.uploads.store import UploadStore

# Every route here requires a signed-in, allow-listed user (api/auth.py).
router = APIRouter(prefix="/interview", tags=["interview"], dependencies=[Depends(current_user)])


def get_model() -> Model:  # overridden in main.py and in tests
    raise NotImplementedError


ModelDep = Annotated[Model, Depends(get_model)]
StoreDep = Annotated[UploadStore, Depends(get_store)]


class StartRequest(BaseModel):
    session_id: str
    setup: SetupInput


def resolve_setup(body: StartRequest, *, user_uid: str, store: UploadStore, model: Model) -> Setup:
    """Turn the browser's SetupInput into a Setup with resume text, reading and
    extracting the uploaded file when one was given (ADR 0010)."""
    given = body.setup
    if bool(given.resume) == bool(given.resume_object):
        raise HTTPException(422, "Upload a resume or paste its text — one or the other.")

    if given.resume_object:
        # Only the caller's own uploads. The prefix is set by /uploads from the
        # verified uid, so this is the whole authorisation check.
        if not given.resume_object.startswith(object_prefix(user_uid)):
            raise HTTPException(403, "That upload isn't yours.")
        data = store.read(given.resume_object)
        if data is None:
            raise HTTPException(404, "The uploaded file wasn't found. Please upload it again.")
        try:
            if given.resume_object.endswith(".pdf"):
                text = pdf_to_text(data, model=model, session_id=body.session_id)
            elif given.resume_object.endswith(".docx"):
                text = docx_to_text(data)
            else:
                raise HTTPException(415, "Upload a PDF or a Word (.docx) file.")
        except ExtractionError as exc:
            raise HTTPException(422, exc.user_message) from exc
    else:
        text = given.resume or ""

    try:
        return Setup(
            resume=text,
            company=given.company,
            role=given.role,
            seniority=given.seniority,
            job_description=given.job_description,
            resume_object=given.resume_object,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        if first["loc"] == ("resume",):
            raise HTTPException(
                422, "The resume needs at least 50 characters of text. Is the file empty?"
            ) from exc
        raise HTTPException(422, f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from exc


class AnswerRequest(BaseModel):
    session: Session
    answer: Answer


@router.post("/start", response_model=Session)
def start(body: StartRequest, user: CurrentUser, model: ModelDep, store: StoreDep) -> Session:
    setup = resolve_setup(body, user_uid=user.uid, store=store, model=model)
    return engine.start(setup, session_id=body.session_id, model=model)


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
