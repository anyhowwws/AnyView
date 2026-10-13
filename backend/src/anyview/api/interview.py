"""Interview routes. The browser owns the session and posts it back each turn.

Setup describes a situation, not a set of sources (ADR 0014): the resume is a
property of the user, the job is a document or a filled-in form, and difficulty
decides what the interviewer is allowed to know.
"""

from __future__ import annotations

import base64
import datetime as dt
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from anyview.api.auth import CurrentUser, current_user, get_settings
from anyview.api.sse import stream_response, tokens
from anyview.api.uploads import audio_prefix, get_store, object_prefix
from anyview.brain.extract import ExtractionFailed, drop_unchanged, propose
from anyview.config import Settings
from anyview.interview import engine
from anyview.interview.models import (
    JOB_SCHEMA,
    Answer,
    JobDocument,
    JobParse,
    Report,
    Session,
    SessionId,
    Setup,
    SetupInput,
    State,
)
from anyview.interview.prompts import INTERJECTIONS, JOB_PARSE_SYSTEM, job_parse_user
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

# A garden can outgrow a prompt. `Setup.garden` caps it; this is where the cut
# is made, with a line saying so rather than a sentence stopping mid-word.
MAX_GARDEN_CHARS = 20_000
MAX_JD_CHARS = 8_000

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
    session_id: SessionId
    setup: SetupInput


def _truncate(text: str, limit: int, what: str) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit) or limit
    return f"{text[:cut].rstrip()}\n\n[{what} continues past this point and was cut to fit.]"


def _extract(
    object_name: str, *, user_uid: str, store: UploadStore, model: Model, session_id: str
) -> str:
    """One uploaded PDF or Word file, as text (ADR 0010).

    The prefix was set by /uploads from the verified uid, so checking it is the
    whole authorisation check: an object outside the caller's own prefix is not
    theirs to read."""
    if not object_name.startswith(object_prefix(user_uid)):
        raise HTTPException(403, "That upload isn't yours.")
    data = store.read(object_name)
    if data is None:
        raise HTTPException(404, "The uploaded file wasn't found. Please upload it again.")
    try:
        if object_name.endswith(".pdf"):
            return pdf_to_text(data, model=model, session_id=session_id)
        if object_name.endswith(".docx"):
            return docx_to_text(data)
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc
    raise HTTPException(415, "Upload a PDF or a Word (.docx) file.")


def _resume_on_file(repo: Any, user_uid: str) -> str:
    if repo is None:
        raise HTTPException(
            422,
            "There's no resume on file and no database to keep one in. "
            "Upload the resume an interviewer would receive.",
        )
    dump = repo.active_resume(user_uid)
    if dump is None:
        raise HTTPException(
            422, "Donna needs your resume first — upload the one an interviewer would receive."
        )
    return dump.text


def _garden(repo: Any, user_uid: str) -> str | None:
    """The confirmed garden as text, or None when there is nothing in it."""
    if repo is None:
        return None
    text = repo.brain_context(user_uid)
    if len(text.strip()) < 50:
        return None
    return _truncate(text, MAX_GARDEN_CHARS, "Your Digital Garden")


def resolve_setup(
    body: StartRequest, *, user_uid: str, store: UploadStore, model: Model, repo: Any = None
) -> Setup:
    """Turn the browser's SetupInput into the interview's situation.

    The resume comes from a fresh upload, from already-extracted text, or — the
    normal case — from the one on file. The garden is attached only at `panel`,
    where the interviewer is allowed to have read it; the report picks it up
    separately at every other level (ADR 0014)."""
    given = body.setup
    if given.resume and given.resume_object:
        raise HTTPException(422, "Send an uploaded resume or its text, not both.")

    if given.resume_object:
        text = _extract(
            given.resume_object,
            user_uid=user_uid,
            store=store,
            model=model,
            session_id=body.session_id,
        )
    elif given.resume:
        text = given.resume
    else:
        text = _resume_on_file(repo, user_uid)

    try:
        return Setup(
            resume=text,
            company=given.company,
            role=given.role,
            seniority=given.seniority,
            difficulty=given.difficulty,
            time_bounded=given.time_bounded,
            job_description=given.job_description,
            resume_object=given.resume_object,
            garden=_garden(repo, user_uid) if given.difficulty == "panel" else None,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        if first["loc"] == ("resume",):
            raise HTTPException(
                422, "The resume needs at least 50 characters of text. Is the file empty?"
            ) from exc
        raise HTTPException(422, f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from exc


def _file_resume(
    repo: Any, user: CurrentUser, setup: Setup, *, model: Model, session_id: str
) -> None:
    """Remember this upload as the resume on file, and offer what is new in it
    to the review queue (ADR 0014, 0015).

    Identical text to something the user has already given us is a no-op: the
    pointer moves, nothing is proposed, and the queue stays worth reading."""
    repo.ensure_user(user.uid, user.email)
    seen = repo.dump_with_text(user.uid, setup.resume)
    if seen is not None:
        repo.set_active_resume(user.uid, seen.id)
        return

    kind = "resume_pdf" if setup.resume_object.endswith(".pdf") else "resume_docx"
    dump = repo.create_dump(user.uid, kind=kind, text=setup.resume, object_name=setup.resume_object)
    repo.set_active_resume(user.uid, dump.id)

    index, _ = repo.brain_index(user.uid)
    brain = repo.brain(user.uid)
    patch = propose(
        setup.resume,
        brain_index=index,
        model=model,
        session_id=session_id,
        garden_skills={k.label: k.name for k in brain.skills},
    )
    patch = drop_unchanged(patch, brain)
    if not patch.is_empty():
        repo.create_proposal(
            user.uid, dump_id=dump.id, patch=patch, model=getattr(model, "model", "fake")
        )


class AnswerRequest(BaseModel):
    session: Session
    answer: Answer


@router.post("/start", response_model=Session)
def start(
    body: StartRequest, user: CurrentUser, model: ModelDep, store: StoreDep, repo: RepoDep
) -> Session:
    setup = resolve_setup(body, user_uid=user.uid, store=store, model=model, repo=repo)

    if not (setup.resume_object and repo is not None):
        return engine.start(setup, session_id=body.session_id, model=model)

    # The same text feeds two independent model calls — plan the interview and
    # propose what the resume adds to the garden — so run them side by side
    # rather than back to back.
    with ThreadPoolExecutor(max_workers=2) as pool:
        planned = pool.submit(engine.start, setup, session_id=body.session_id, model=model)
        filed = pool.submit(
            _file_resume, repo, user, setup, model=model, session_id=body.session_id
        )
        session = planned.result()
        try:
            filed.result()
        except ExtractionFailed as exc:
            # The interview is what the user asked for; the garden entry is a bonus.
            log.warning("filing the resume failed for %s: %s", body.session_id, exc.user_message)
    return session


# --- The resume on file (ADR 0014) ------------------------------------------


class ResumeOnFile(BaseModel):
    """What the setup form shows in place of an upload zone. `dump_id` is None
    when there is nothing on file yet, which is the only thing the form needs
    in order to decide which of the two it draws."""

    dump_id: str | None = None
    kind: str | None = None
    uploaded_at: dt.datetime | None = None
    characters: int = 0


@router.get("/resume", response_model=ResumeOnFile)
def resume_on_file(user: CurrentUser, repo: RepoDep) -> ResumeOnFile:
    if repo is None:
        return ResumeOnFile()
    repo.ensure_user(user.uid, user.email)
    dump = repo.active_resume(user.uid)
    if dump is None:
        return ResumeOnFile()
    return ResumeOnFile(
        dump_id=dump.id,
        kind=dump.kind,
        uploaded_at=dump.created_at,
        characters=len(dump.text),
    )


# --- The target job (ADR 0014) ----------------------------------------------


class JobUploadRequest(BaseModel):
    object_name: str = Field(max_length=200)


@router.post("/job/parse", response_model=JobDocument)
def parse_job(
    body: JobUploadRequest, user: CurrentUser, model: ModelDep, store: StoreDep
) -> JobDocument:
    """An uploaded job description, read and turned into the fields the setup
    form asks for. Everything it returns is a suggestion the user confirms
    before it reaches a prompt."""
    session_id = f"job-{uuid.uuid4().hex[:8]}"
    text = _truncate(
        _extract(
            body.object_name, user_uid=user.uid, store=store, model=model, session_id=session_id
        ),
        MAX_JD_CHARS,
        "The job description",
    )
    if len(text.strip()) < 50:
        raise HTTPException(422, "There's almost no text in that file. Is it the right one?")

    # Extraction, not judgement: the fields are filled in from what the posting
    # says, and the user corrects anything the model read wrong.
    reply = model.generate(
        system=JOB_PARSE_SYSTEM,
        user=job_parse_user(text),
        session_id=session_id,
        call="parse_job",
        output_schema=JOB_SCHEMA,
        effort="low",
        max_tokens=2048,
    )
    if reply.refused or reply.truncated or reply.data is None:
        raise HTTPException(502, "Donna couldn't read that job description. Please try again.")
    try:
        parsed = JobParse.model_validate(reply.data)
    except ValidationError as exc:
        log.warning("job parse came back malformed: %s", exc)
        raise HTTPException(502, "That job description came back malformed. Please retry.") from exc
    return JobDocument(text=text, parsed=parsed)


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


class SayRequest(BaseModel):
    session_id: SessionId
    # A key, never free text: this route must not become a way to have the TTS
    # model read out anything a caller likes.
    line: Literal["time_up", "stalled"]


class Spoken(BaseModel):
    b64: str


@router.post("/say", response_model=Spoken)
def say(body: SayRequest, model: ModelDep, settings: SettingsDep) -> Spoken:
    """One of Donna's fixed interjections, spoken (ADR 0016).

    The browser fetches each line once and reuses the clip for the whole
    interview, so a five-question run synthesises two short clips at most."""
    audio = model.speak(
        text=INTERJECTIONS[body.line], session_id=body.session_id, voice=settings.donna_voice
    )
    return Spoken(b64=base64.b64encode(audio).decode("ascii"))


class TranscribeRequest(BaseModel):
    session_id: SessionId
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


def _for_report(session: Session, repo: Any, uid: str) -> Session:
    """The report is coaching, not simulation, so the ideal answers read the
    garden at every difficulty (ADR 0014). At `panel` the session already
    carries it; below that it is attached here, where it can reach the report
    without ever having reached the questions."""
    if session.setup.garden is None:
        garden = _garden(repo, uid)
        if garden:
            session = session.model_copy(
                update={"setup": session.setup.model_copy(update={"garden": garden})}
            )
    return session


@router.post("/report", response_model=Report)
def report(session: Session, user: CurrentUser, model: ModelDep, repo: RepoDep) -> Report:
    return engine.finish(_for_report(session, repo, user.uid), model=model)


@router.post("/report/stream")
def stream_report(session: Session, user: CurrentUser, model: ModelDep, repo: RepoDep):
    """`POST /report`, streamed, so the report fills in while it is written:

        event: report   data: <Report with items: []>     (at once: the header)
        event: item     data: {"index": 2, "item": <QuestionReport>}   (×5, as each finishes)
        event: done     data: {}

    Items arrive in finishing order; `index` is the question's position. The
    session is checked before the stream opens, so a bad one is a plain 409."""
    session = _for_report(session, repo, user.uid)
    header = engine.begin_scoring(session)

    def frames():
        yield ("report", header.model_dump(mode="json"))
        for index, item in engine.score_as_ready(session, model=model):
            yield ("item", {"index": index, "item": item.model_dump(mode="json")})

    return stream_response(frames())
