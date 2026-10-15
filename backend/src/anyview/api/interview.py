"""Interview routes. The browser owns the session and posts it back each turn.

Setup describes a situation, not a set of sources (ADR 0014): the resume is a
property of the user, the job is a document, a link or a filled-in form, and difficulty
decides what the interviewer is allowed to know.
"""

from __future__ import annotations

import base64
import datetime as dt
import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from anyview.activity import record
from anyview.api.auth import CurrentUser, current_user, get_settings
from anyview.api.sse import stream_response, tokens
from anyview.api.uploads import get_store, object_prefix, transcribe_recording
from anyview.brain.extract import ExtractionFailed, drop_unchanged, propose
from anyview.config import Settings
from anyview.db.repository import NotFound
from anyview.interview import engine, fixed_lines
from anyview.interview.models import (
    JOB_SCHEMA,
    Answer,
    JobDocument,
    JobParse,
    Report,
    SavedJob,
    Session,
    SessionId,
    Setup,
    SetupInput,
    State,
)
from anyview.interview.prompts import (
    HARVEY_DELIVERY,
    INTERJECTIONS,
    JOB_PARSE_SYSTEM,
    job_parse_user,
)
from anyview.interview.voice import voiced
from anyview.llm.adapter import Model, ModelError
from anyview.uploads.extract import (
    PDF,
    ExtractionError,
    docx_to_text,
    pdf_to_text,
)
from anyview.uploads.link import Page, page_to_text
from anyview.uploads.link import fetch as fetch_page
from anyview.uploads.store import UploadStore

log = logging.getLogger(__name__)

# A garden can outgrow a prompt. `Setup.garden` caps it; this is where the cut
# is made, with a line saying so rather than a sentence stopping mid-word.
MAX_GARDEN_CHARS = 20_000
MAX_GARDEN_INDEX_CHARS = 12_000
# Garden entries an ideal answer reads in full when the garden is searched (ADR 0038).
RELEVANT_ENTRIES = 6
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
    """Cut `text` to at most `limit` characters, note included, at a line break
    if there is one, else a space. The result has to pass the same limit on
    `Setup`; it used to overshoot by the length of the note, and by nearly the
    whole text when there was no line break (rfind's -1 is truthy)."""
    if len(text) <= limit:
        return text
    note = f"\n\n[{what} continues past this point and was cut to fit.]"
    room = limit - len(note)
    cut = text.rfind("\n", 0, room)
    if cut <= 0:
        cut = text.rfind(" ", 0, room)
    if cut <= 0:
        cut = room
    return text[:cut].rstrip() + note


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
            422, "Harvey needs your resume first — upload the one an interviewer would receive."
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


def _garden_index(repo: Any, user_uid: str) -> str | None:
    """One line per garden entry, for Harvey on Live (ADR 0037)."""
    if repo is None:
        return None
    index, _ = repo.brain_index(user_uid)
    if not index.strip():
        return None
    return _truncate(index, MAX_GARDEN_INDEX_CHARS, "The garden index")


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
            garden_index=_garden_index(repo, user_uid) if given.difficulty == "panel" else None,
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
        session = engine.start(setup, session_id=body.session_id, model=model)
        record("interview_started")
        _save_job(repo, user, body.setup)
        return session

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
    record("interview_started")
    _save_job(repo, user, body.setup)
    return session


def _save_job(repo: Any, user: CurrentUser, given: SetupInput) -> None:
    """Remember the job this interview was planned for (ADR 0025).

    Only once planning has succeeded, so a failed start leaves nothing behind.
    Best effort: the interview is what the user asked for, and a job that fails
    to save is one they type again next time, not a reason to refuse it."""
    if repo is None or given.job is None:
        return
    try:
        repo.ensure_user(user.uid, user.email)
        repo.save_job(
            user.uid,
            job_id=given.job.id,
            company=given.company,
            role=given.role,
            seniority=given.seniority,
            source=given.job.source,
            job_description=given.job_description,
            fields=given.job.fields,
        )
    except Exception:  # noqa: BLE001 — logged, and never worth failing the interview over
        log.exception("saving the job failed for %s", user.uid)


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


class JobLinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


def get_page_fetcher() -> Callable[[str], Page]:  # overridden in tests; never touch the web there
    return fetch_page


FetcherDep = Annotated[Callable[[str], Page], Depends(get_page_fetcher)]


@router.post("/job/parse", response_model=JobDocument)
def parse_job(
    body: JobUploadRequest, user: CurrentUser, model: ModelDep, store: StoreDep, repo: RepoDep
) -> JobDocument:
    """An uploaded job description, read and turned into the fields the setup
    form asks for. Everything it returns is a suggestion the user confirms
    before it reaches a prompt.

    A posting already saved comes back as that saved job instead, with the
    corrections the user made last time and no parse call (ADR 0025)."""
    session_id = f"job-{uuid.uuid4().hex[:8]}"
    text = _extract(
        body.object_name, user_uid=user.uid, store=store, model=model, session_id=session_id
    )
    return _read_posting(text, user=user, model=model, repo=repo, session_id=session_id)


@router.post("/job/parse-link", response_model=JobDocument)
def parse_job_link(
    body: JobLinkRequest, user: CurrentUser, model: ModelDep, repo: RepoDep, fetch: FetcherDep
) -> JobDocument:
    """A job posting from a link the user pasted (ADR 0027): fetched once,
    turned into text, then exactly what an uploaded posting goes through.
    `uploads/link.py` decides which links may be fetched at all."""
    session_id = f"job-{uuid.uuid4().hex[:8]}"
    try:
        page = fetch(body.url)
        if page.content_type == PDF:
            text = pdf_to_text(page.body, model=model, session_id=session_id)
        elif page.content_type == "text/plain":
            text = page.body.decode(page.charset or "utf-8", errors="replace")
        else:
            text = page_to_text(page.body.decode(page.charset or "utf-8", errors="replace"))
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc
    if len(text.strip()) < 50:
        raise HTTPException(
            422,
            "That page has almost no text until a browser runs it. "
            "Save the posting as a PDF and upload that instead.",
        )
    return _read_posting(text, user=user, model=model, repo=repo, session_id=session_id)


def _read_posting(
    text: str, *, user: CurrentUser, model: Model, repo: Any, session_id: str
) -> JobDocument:
    """A posting's text, matched against saved jobs, else parsed into fields."""
    text = _truncate(text, MAX_JD_CHARS, "The job description")
    if len(text.strip()) < 50:
        raise HTTPException(422, "There's almost no text in that file. Is it the right one?")

    saved = repo.saved_job_with_text(user.uid, text) if repo is not None else None
    if saved is not None:
        return JobDocument(text=text, parsed=_parse_from_saved(saved), saved_job=saved)

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
        raise HTTPException(502, "Harvey couldn't read that job description. Please try again.")
    try:
        parsed = JobParse.model_validate(reply.data)
    except ValidationError as exc:
        log.warning("job parse came back malformed: %s", exc)
        raise HTTPException(502, "That job description came back malformed. Please retry.") from exc
    return JobDocument(text=text, parsed=parsed)


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _parse_from_saved(job: SavedJob) -> JobParse:
    """A saved job, in the shape a fresh parse would have, so the form treats
    both the same way."""
    return JobParse(
        company=job.company,
        role=job.role,
        seniority=job.seniority,
        responsibilities=_lines(job.fields.responsibilities),
        must_haves=_lines(job.fields.must_haves),
        nice_to_haves=_lines(job.fields.nice_to_haves),
    )


@router.get("/jobs", response_model=list[SavedJob])
def saved_jobs(user: CurrentUser, repo: RepoDep) -> list[SavedJob]:
    """The jobs this user has practised for, most recent first. Empty with no
    database: then nothing is remembered and the form shows no list."""
    if repo is None:
        return []
    return repo.saved_jobs(user.uid)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_saved_job(job_id: str, user: CurrentUser, repo: RepoDep) -> None:
    if repo is None:
        raise HTTPException(404, "There are no saved jobs without a database.")
    try:
        repo.delete_saved_job(user.uid, job_id)
    except NotFound as exc:
        raise HTTPException(404, "That saved job wasn't found.") from exc


@router.post("/ask")
def ask(session: Session, model: ModelDep, settings: SettingsDep, voice: bool = False):
    # Validate state before opening the stream so a bad session is a plain 409,
    # not an error frame inside a 200.
    engine.require_state(session, State.ASK)
    words = engine.ask(session, spoken=voice)
    if not voice:
        return stream_response(tokens(words))
    # Voice mode: the same words, plus a spoken clip per sentence (ADR 0013).
    return stream_response(
        voiced(
            words,
            model=model,
            session_id=session.session_id,
            voice=settings.harvey_voice,
            style=HARVEY_DELIVERY,
        )
    )


class SayRequest(BaseModel):
    session_id: SessionId
    # A key, never free text: this route must not become a way to have the TTS
    # model read out anything a caller likes.
    line: Literal["time_up", "stalled", "move_on", "goodbye", "hello"]
    # Which wording of the line: an index, not text. Out of range wraps round,
    # so a browser that expects more wordings than there are still gets one.
    variant: int = Field(default=0, ge=0, le=99)


class Spoken(BaseModel):
    b64: str


@router.post("/say", response_model=Spoken)
async def say(body: SayRequest, model: ModelDep, settings: SettingsDep) -> Spoken:
    """One of Harvey's fixed interjections, spoken (ADR 0016) in his Live voice,
    so the hearing test and the cut-ins sound like the interviewer
    (`interview/fixed_lines.py`; TTS if Live fails).

    The browser fetches each wording once and reuses the clip for the whole
    interview, rotating through a line's wordings so Harvey does not say the
    same "take a moment" every time. `async` because a Live session is."""
    audio = await fixed_lines.spoken(
        model,
        text=_wording(body.line, body.variant),
        session_id=body.session_id,
        voice=settings.harvey_voice,
    )
    return Spoken(b64=base64.b64encode(audio).decode("ascii"))


def _wording(line: str, variant: int) -> str:
    wordings = INTERJECTIONS[line]
    return wordings[variant % len(wordings)]


class TranscribeRequest(BaseModel):
    session_id: SessionId
    object_name: str


class Transcript(BaseModel):
    text: str


@router.post("/transcribe", response_model=Transcript)
def transcribe(
    body: TranscribeRequest, user: CurrentUser, model: ModelDep, store: StoreDep
) -> Transcript:
    """A recorded answer, turned into the text the engine already understands
    (ADR 0013). The checks and the call live in `transcribe_recording`."""
    return Transcript(
        text=transcribe_recording(
            body.object_name, uid=user.uid, store=store, model=model, session_id=body.session_id
        )
    )


@router.post("/answer", response_model=Session)
def answer(body: AnswerRequest, model: ModelDep) -> Session:
    session = engine.submit_answer(body.session, body.answer)
    if session.state == State.ASK:
        # Another question follows: the planner may reword it (ADR 0036).
        # Best effort and bounded; the planned question is asked if it fails.
        session = engine.adapt(session, model=model)
    return session


def _for_report(session: Session, repo: Any, uid: str) -> Session:
    """The report is coaching, not simulation, so the ideal answers read the
    garden at every difficulty (ADR 0014). At `panel` the session already
    carries it; below that it is attached here, where it can reach the report
    without ever having reached the questions. The index rides along for a
    garden too big to read whole (ADR 0038)."""
    update: dict[str, Any] = {}
    if session.setup.garden is None:
        garden = _garden(repo, uid)
        if garden:
            update["garden"] = garden
    if session.setup.garden_index is None:
        index = _garden_index(repo, uid)
        if index:
            update["garden_index"] = index
    if update:
        session = session.model_copy(update={"setup": session.setup.model_copy(update=update)})
    return session


def _relevant(session: Session, repo: Any, uid: str, model: Model) -> dict[int, str]:
    """For each question, the garden entries nearest it (ADR 0038), but only
    when the garden is too big to read whole: until then the ideal answer reads
    all of it, which nothing nearest-first can beat (the rule of ADR 0017).
    Best effort: if search fails, the report reads the garden as before."""
    if repo is None or len(repo.brain_context(uid)) <= MAX_GARDEN_CHARS:
        return {}
    queries = [f"{q.text} (competency: {q.competency})" for q in session.questions]
    try:
        vectors = model.embed(queries, session_id=session.session_id, call="embed_query")
    except ModelError as exc:
        log.warning("garden search failed for %s: %s", session.session_id, exc.user_message)
        return {}
    return {
        question.id: "\n\n".join(
            found.text for found in repo.search_garden(uid, vector, limit=RELEVANT_ENTRIES)
        )
        for question, vector in zip(session.questions, vectors, strict=True)
    }


@router.post("/report", response_model=Report)
def report(session: Session, user: CurrentUser, model: ModelDep, repo: RepoDep) -> Report:
    session = _for_report(session, repo, user.uid)
    relevant = _relevant(session, repo, user.uid, model)
    finished = engine.finish(session, model=model, relevant=relevant)
    record("interview_completed")
    return finished


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
    relevant = _relevant(session, repo, user.uid, model)

    def frames():
        started = time.monotonic()
        yield ("report", header.model_dump(mode="json"))
        for index, item in engine.score_as_ready(session, model=model, relevant=relevant):
            # One line per item, so a slow report can be read off the logs: when
            # each question's score and ideal answer were both in and sent.
            log.info(
                "report %s: question %d sent after %.0f s",
                session.session_id,
                index + 1,
                time.monotonic() - started,
            )
            yield ("item", {"index": index, "item": item.model_dump(mode="json")})
        record("interview_completed")  # every item was sent

    return stream_response(frames())
