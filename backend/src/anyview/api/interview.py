"""Interview routes. The browser owns the session and posts it back each turn."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from anyview.api.auth import CurrentUser, current_user, get_settings
from anyview.api.sse import stream_response, tokens
from anyview.api.uploads import audio_prefix, get_store, object_prefix
from anyview.brain.extract import ExtractionFailed, propose
from anyview.config import Settings
from anyview.interview import engine
from anyview.interview.models import Answer, Report, Session, Setup, SetupInput, State
from anyview.interview.voice import voiced
from anyview.llm.adapter import Model
from anyview.uploads.extract import (
    EXTENSION_TYPES,
    ExtractionError,
    audio_to_text,
    docx_to_text,
    pdf_to_text,
)
from anyview.uploads.store import UploadStore

log = logging.getLogger(__name__)

# Every route here requires a signed-in, allow-listed user (api/auth.py).
router = APIRouter(prefix="/interview", tags=["interview"], dependencies=[Depends(current_user)])


def get_model() -> Model:  # overridden in main.py and in tests
    raise NotImplementedError


ModelDep = Annotated[Model, Depends(get_model)]
StoreDep = Annotated[UploadStore, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_repository_optional():  # overridden in main.py and tests; None = no database
    return None


RepoDep = Annotated[Any, Depends(get_repository_optional)]


class StartRequest(BaseModel):
    session_id: str
    setup: SetupInput


def resolve_setup(
    body: StartRequest, *, user_uid: str, store: UploadStore, model: Model, repo: Any = None
) -> Setup:
    """Turn the browser's SetupInput into a Setup with the candidate's record:
    pasted text, an uploaded file's extracted text (ADR 0010), or the brain
    rendered as text."""
    given = body.setup
    sources = sum(bool(x) for x in (given.resume, given.resume_object, given.use_brain))
    if sources != 1:
        raise HTTPException(
            422, "Upload a resume, paste its text, or use your Digital Garden — one of the three."
        )

    if given.use_brain:
        if repo is None:
            raise HTTPException(503, "The brain needs a database and none is configured.")
        text = repo.brain_context(user_uid)
        if len(text.strip()) < 50:
            raise HTTPException(
                422,
                "Your Digital Garden is still empty. Add something to it first, "
                "or upload a resume.",
            )
        try:
            return Setup(
                resume=text,
                company=given.company,
                role=given.role,
                seniority=given.seniority,
                job_description=given.job_description,
                resume_object=None,
                source="brain",
            )
        except ValidationError as exc:
            raise HTTPException(
                422, "Your Digital Garden is too large to fit in one interview prompt yet."
            ) from exc

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
def start(
    body: StartRequest, user: CurrentUser, model: ModelDep, store: StoreDep, repo: RepoDep
) -> Session:
    setup = resolve_setup(body, user_uid=user.uid, store=store, model=model, repo=repo)

    if not (body.setup.add_to_brain and setup.resume_object):
        return engine.start(setup, session_id=body.session_id, model=model)
    if repo is None:
        raise HTTPException(503, "The brain needs a database and none is configured.")

    # The same text feeds two independent model calls — plan the interview and
    # propose brain entries — so run them side by side rather than back to back.
    def add_to_brain() -> None:
        repo.ensure_user(user.uid, user.email)
        kind = "resume_pdf" if setup.resume_object.endswith(".pdf") else "resume_docx"
        dump = repo.create_dump(
            user.uid, kind=kind, text=setup.resume, object_name=setup.resume_object
        )
        index, _ = repo.brain_index(user.uid)
        patch = propose(setup.resume, brain_index=index, model=model, session_id=body.session_id)
        if not patch.is_empty():
            repo.create_proposal(
                user.uid, dump_id=dump.id, patch=patch, model=getattr(model, "model", "fake")
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        planned = pool.submit(engine.start, setup, session_id=body.session_id, model=model)
        proposed = pool.submit(add_to_brain)
        session = planned.result()
        try:
            proposed.result()
        except ExtractionFailed as exc:
            # The interview is what the user asked for; the brain entry is a bonus.
            log.warning("add_to_brain failed for %s: %s", body.session_id, exc.user_message)
    return session


@router.post("/ask")
def ask(session: Session, model: ModelDep, settings: SettingsDep, voice: bool = False):
    # Validate state before opening the stream so a bad session is a plain 409,
    # not an error frame inside a 200.
    engine.require_state(session, State.ASK)
    words = engine.ask(session, model=model)
    if not voice:
        return stream_response(tokens(words))
    # Voice mode: the same words, plus a spoken clip per sentence (ADR 0013).
    return stream_response(
        voiced(
            words,
            model=model,
            session_id=session.session_id,
            voice=settings.donna_voice,
        )
    )


class TranscribeRequest(BaseModel):
    session_id: str
    object_name: str


class Transcript(BaseModel):
    text: str


@router.post("/transcribe", response_model=Transcript)
def transcribe(
    body: TranscribeRequest, user: CurrentUser, model: ModelDep, store: StoreDep
) -> Transcript:
    """A recorded answer, turned into the text the engine already understands.

    The browser uploads the recording straight to the bucket and sends only its
    object name, the same shape as a resume upload (ADR 0010, 0013)."""
    # Only the caller's own recordings, by the prefix the ticket route set from
    # the verified uid. This is the whole authorisation check.
    if not body.object_name.startswith(audio_prefix(user.uid)):
        raise HTTPException(403, "That recording isn't yours.")
    suffix = body.object_name[body.object_name.rfind(".") :]
    mime = EXTENSION_TYPES.get(suffix)
    if mime is None:
        raise HTTPException(415, "That recording format isn't supported.")
    data = store.read(body.object_name)
    if data is None:
        raise HTTPException(404, "The recording wasn't found. Please record it again.")
    try:
        return Transcript(text=audio_to_text(data, mime, model=model, session_id=body.session_id))
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc


@router.post("/answer", response_model=Session)
def answer(body: AnswerRequest) -> Session:
    return engine.submit_answer(body.session, body.answer)


@router.post("/report", response_model=Report)
def report(session: Session, model: ModelDep) -> Report:
    return engine.finish(session, model=model)
