"""The second brain's routes (ADR 0002). Every route requires a signed-in,
allow-listed user; every repository call is scoped by that user's uid."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from anyview.activity import record
from anyview.api.auth import CurrentUser, current_user
from anyview.api.interview import ModelDep, SettingsDep, Transcript
from anyview.api.sse import stream_response
from anyview.api.uploads import StoreDep, transcribe_recording
from anyview.brain.discover import DiscoverRequest, ReadAloudRequest, answer, read_aloud
from anyview.brain.ingest import IngestFailed, check_upload, propose_for, read_upload
from anyview.brain.manual import BadEntry, patch_for, source_text
from anyview.brain.models import Brain, Event, IngestJob, Patch, Proposal, RawDump
from anyview.db.repository import Conflict, Embedder, NotFound, Repository
from anyview.llm.adapter import Model
from anyview.tasks import QueueError, TaskQueue

log = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["brain"], dependencies=[Depends(current_user)])


def get_repository() -> Repository:  # overridden in main.py and tests
    raise NotImplementedError


RepoDep = Annotated[Repository, Depends(get_repository)]


def embedder(model: Model) -> Embedder:
    """The model's `embed` for one garden write (ADR 0038). Every entry a write
    changes is embedded before it is saved; if that fails, nothing is saved and
    the app's ModelError handler answers 503."""
    session_id = f"garden-{uuid.uuid4().hex[:12]}"  # names this write's usage rows
    return Embedder(
        model=getattr(model, "embedding_model", model.model),
        embed=lambda texts: model.embed(texts, session_id=session_id),
    )


def get_queue() -> TaskQueue:  # overridden in main.py and tests
    raise NotImplementedError


QueueDep = Annotated[TaskQueue, Depends(get_queue)]


class DumpRequest(BaseModel):
    text: str = Field(min_length=20, max_length=20_000)


class UploadDumpRequest(BaseModel):
    resume_object: str = Field(max_length=200)


class ConfirmRequest(BaseModel):
    patch: Patch


class EditRequest(BaseModel):
    fields: dict[str, Any]


class EventOut(BaseModel):
    event: Event
    brain: Brain


def _propose(
    repo: Repository, model, user: CurrentUser, *, kind: str, text: str, object_name: str | None
) -> Proposal:
    repo.ensure_user(user.uid, user.email)
    dump = repo.create_dump(user.uid, kind=kind, text=text, object_name=object_name)
    try:
        return propose_for(repo, model, user.uid, dump)
    except IngestFailed as exc:
        raise HTTPException(exc.status, exc.message) from exc


def _silent(stage: str, data: dict) -> None:
    """The synchronous routes take no progress."""


# The synchronous routes read a dump inside the request. The browser no longer
# uses them (it queues a job, below); scripts and tests still do.


@router.post("/dumps", response_model=Proposal)
def create_dump(body: DumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep) -> Proposal:
    return _propose(repo, model, user, kind="text", text=body.text, object_name=None)


@router.post("/dumps/from-upload", response_model=Proposal)
def create_dump_from_upload(
    body: UploadDumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, store: StoreDep
) -> Proposal:
    try:
        kind, text = read_upload(
            body.resume_object, user.uid, model=model, store=store, tell=_silent
        )
    except IngestFailed as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return _propose(repo, model, user, kind=kind, text=text, object_name=body.resume_object)


# --- Queued ingestion (ADR 0034) ----------------------------------------------
# The browser hands in a dump and gets a job id back at once. Cloud Tasks runs
# the job on the worker service; the browser polls the job for its progress
# frames and, at the end, the proposal.


class JobRequest(BaseModel):
    """Typed text, or an uploaded file. Exactly one."""

    text: str | None = Field(default=None, min_length=20, max_length=20_000)
    resume_object: str | None = Field(default=None, max_length=200)


@router.post("/jobs", response_model=IngestJob, status_code=202)
def create_job(body: JobRequest, user: CurrentUser, repo: RepoDep, queue: QueueDep) -> IngestJob:
    if (body.text is None) == (body.resume_object is None):
        raise HTTPException(422, "Send either some text or an uploaded file.")
    if body.resume_object is not None:
        try:
            check_upload(body.resume_object, user.uid)  # answered now, not after the queue
        except IngestFailed as exc:
            raise HTTPException(exc.status, exc.message) from exc
    repo.ensure_user(user.uid, user.email)
    job = repo.create_job(user.uid, text=body.text, object_name=body.resume_object)
    try:
        queue.enqueue(job.id)
    except QueueError as exc:
        log.error("could not queue ingest job %s: %s", job.id, exc)
        repo.fail_job(job.id, "Donna couldn't start reading. Please try again.", 503)
        raise HTTPException(503, "Donna couldn't start reading. Please try again.") from exc
    record("garden_upload")
    # An inline queue may already have finished it; read it back either way.
    return repo.job(user.uid, job.id)


@router.get("/jobs", response_model=list[IngestJob])
def list_active_jobs(user: CurrentUser, repo: RepoDep) -> list[IngestJob]:
    """Jobs still running: a reloaded page picks its progress view back up."""
    return repo.active_jobs(user.uid)


@router.get("/jobs/{job_id}", response_model=IngestJob)
def read_job(job_id: str, user: CurrentUser, repo: RepoDep) -> IngestJob:
    try:
        return repo.job(user.uid, job_id)
    except NotFound as exc:
        raise HTTPException(404, "No such job.") from exc


@router.get("/dumps/{dump_id}", response_model=RawDump)
def read_dump(dump_id: str, user: CurrentUser, repo: RepoDep) -> RawDump:
    try:
        return repo.dump(user.uid, dump_id)
    except NotFound as exc:
        raise HTTPException(404, "No such dump.") from exc


@router.get("", response_model=Brain)
def read_brain(user: CurrentUser, repo: RepoDep) -> Brain:
    repo.ensure_user(user.uid, user.email)
    return repo.brain(user.uid)


@router.get("/proposals", response_model=list[Proposal])
def list_proposals(user: CurrentUser, repo: RepoDep) -> list[Proposal]:
    repo.ensure_user(user.uid, user.email)
    return repo.pending_proposals(user.uid)


@router.post("/proposals/{proposal_id}/confirm", response_model=EventOut)
def confirm_proposal(
    proposal_id: str, body: ConfirmRequest, user: CurrentUser, repo: RepoDep, model: ModelDep
) -> EventOut:
    try:
        event = repo.confirm_proposal(user.uid, proposal_id, body.patch, embed=embedder(model))
    except NotFound as exc:
        raise HTTPException(404, "No such proposal.") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.post("/proposals/{proposal_id}/discard", response_model=Brain)
def discard_proposal(proposal_id: str, user: CurrentUser, repo: RepoDep) -> Brain:
    try:
        repo.discard_proposal(user.uid, proposal_id)
    except NotFound as exc:
        raise HTTPException(404, "No such pending proposal.") from exc
    return repo.brain(user.uid)


Kind = Literal[
    "role", "project", "story", "skill", "achievement", "education", "language", "feedback"
]


@router.post("/entities/{kind}", response_model=EventOut)
def add_entity(
    kind: Kind, body: EditRequest, user: CurrentUser, repo: RepoDep, model: ModelDep
) -> EventOut:
    """Add one entry from a form, with no model call and no review (ADR 0022).
    The form's text becomes the dump the entry points back to."""
    repo.ensure_user(user.uid, user.email)
    text = source_text(kind, body.fields)
    try:
        patch = patch_for(kind, body.fields, evidence=text)
        event = repo.add_entry(user.uid, patch, text, embed=embedder(model))
    except BadEntry as exc:
        raise HTTPException(422, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.patch("/entities/{kind}/{entity_id}", response_model=EventOut)
def edit_entity(
    kind: Kind,
    entity_id: str,
    body: EditRequest,
    user: CurrentUser,
    repo: RepoDep,
    model: ModelDep,
) -> EventOut:
    try:
        event = repo.edit_entity(user.uid, kind, entity_id, body.fields, embed=embedder(model))
    except NotFound as exc:
        raise HTTPException(404, f"No such {kind}.") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.delete("/entities/{kind}/{entity_id}", response_model=EventOut)
def retire_entity(
    kind: Kind, entity_id: str, user: CurrentUser, repo: RepoDep, model: ModelDep
) -> EventOut:
    try:
        event = repo.retire_entity(user.uid, kind, entity_id, embed=embedder(model))
    except NotFound as exc:
        raise HTTPException(404, f"No such {kind}.") from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.post("/discover")
def discover(
    body: DiscoverRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, settings: SettingsDep
):
    """Ask Donna about the confirmed garden (ADR 0017). Streams token frames,
    then one `citations` frame naming the entries the answer relies on. With
    `voice: true` (a question asked out loud, ADR 0033) `audio` frames ride beside the tokens."""
    repo.ensure_user(user.uid, user.email)
    # Checked before the stream opens, so an empty garden is a plain 422 rather
    # than an error frame inside a 200.
    _, labels = repo.brain_index(user.uid)
    if not labels:
        raise HTTPException(
            422, "Your Digital Garden is empty. Capture something first, then ask Donna about it."
        )
    garden = repo.brain_context(user.uid)
    record("discover_question")
    return stream_response(
        answer(body, garden=garden, labels=labels, model=model, voice=settings.donna_voice)
    )


@router.post("/discover/read-aloud")
def discover_read_aloud(body: ReadAloudRequest, model: ModelDep, settings: SettingsDep):
    """Donna reads out an answer already on screen (ADR 0033): `audio` frames
    only, one per sentence. Each clip is a usage row like any other."""
    return stream_response(read_aloud(body, model=model, voice=settings.donna_voice))


class DiscoverTranscribeRequest(BaseModel):
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    object_name: str = Field(max_length=200)


@router.post("/discover/transcribe", response_model=Transcript)
def discover_transcribe(
    body: DiscoverTranscribeRequest, user: CurrentUser, model: ModelDep, store: StoreDep
) -> Transcript:
    """A question asked out loud (ADR 0030, 0033), as text. The browser
    shows it, then asks it through `/brain/discover` like a typed one."""
    text = transcribe_recording(
        body.object_name,
        uid=user.uid,
        store=store,
        model=model,
        session_id=f"discover-{body.conversation_id}",
        what="the candidate's question",
    )
    return Transcript(text=text)


@router.get("/events", response_model=list[Event])
def list_events(user: CurrentUser, repo: RepoDep) -> list[Event]:
    return repo.events(user.uid)
