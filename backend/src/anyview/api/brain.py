"""The second brain's routes (ADR 0002). Every route requires a signed-in,
allow-listed user; every repository call is scoped by that user's uid."""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from anyview.api.auth import CurrentUser, current_user
from anyview.api.interview import ModelDep, SettingsDep, Transcript
from anyview.api.sse import Frame, stream_response
from anyview.api.uploads import StoreDep, object_prefix, transcribe_recording
from anyview.brain.discover import DiscoverRequest, ReadAloudRequest, answer, read_aloud
from anyview.brain.extract import ExtractionFailed, Progress, drop_unchanged, propose
from anyview.brain.manual import BadEntry, patch_for, source_text
from anyview.brain.models import Brain, Event, Patch, Proposal, RawDump
from anyview.db.repository import Conflict, NotFound, Repository
from anyview.uploads.extract import (
    ExtractionError,
    docx_to_text,
    pdf_to_text,
)

router = APIRouter(prefix="/brain", tags=["brain"], dependencies=[Depends(current_user)])


def get_repository() -> Repository:  # overridden in main.py and tests
    raise NotImplementedError


RepoDep = Annotated[Repository, Depends(get_repository)]


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
    repo: Repository,
    model,
    user: CurrentUser,
    *,
    kind: str,
    text: str,
    object_name: str | None,
    on_progress: Progress | None = None,
) -> Proposal:
    repo.ensure_user(user.uid, user.email)
    dump = repo.create_dump(user.uid, kind=kind, text=text, object_name=object_name)
    index, _ = repo.brain_index(user.uid)
    brain = repo.brain(user.uid)
    try:
        patch = propose(
            text,
            brain_index=index,
            model=model,
            session_id=f"dump-{dump.id[:8]}",
            garden_skills={k.label: k.name for k in brain.skills},
            on_progress=on_progress,
        )
    except ExtractionFailed as exc:
        raise HTTPException(502, exc.user_message) from exc
    if patch.is_empty():
        raise HTTPException(
            422,
            "Donna found nothing about your experience in that. "
            "Try describing a role, a project, or a story.",
        )
    # Drafts that only restate something already confirmed never reach the
    # queue: a queue of cards the user has already agreed to is a queue that
    # gets approved unread (ADR 0015).
    patch = drop_unchanged(patch, brain)
    if patch.is_empty():
        raise HTTPException(
            422, "Nothing new in there — your Digital Garden already has all of it."
        )
    return repo.create_proposal(
        user.uid, dump_id=dump.id, patch=patch, model=getattr(model, "model", "fake")
    )


def _read_upload(
    body: UploadDumpRequest, user: CurrentUser, model, store, tell: Progress
) -> tuple[str, str]:
    """The uploaded file as (dump kind, text)."""
    if not body.resume_object.startswith(object_prefix(user.uid)):
        raise HTTPException(403, "That upload isn't yours.")
    data = store.read(body.resume_object)
    if data is None:
        raise HTTPException(404, "The uploaded file wasn't found. Please upload it again.")
    tell("reading", {"file": body.resume_object.rsplit(".", 1)[-1]})
    try:
        if body.resume_object.endswith(".pdf"):
            kind, text = (
                "resume_pdf",
                pdf_to_text(data, model=model, session_id=f"upload-{uuid.uuid4().hex[:8]}"),
            )
        elif body.resume_object.endswith(".docx"):
            kind, text = "resume_docx", docx_to_text(data)
        else:
            raise HTTPException(415, "Upload a PDF or Word (.docx) file.")
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc
    if len(text.strip()) < 20:
        raise HTTPException(422, "The file has almost no text in it.")
    tell("read", {"characters": len(text)})
    return kind, text


def _silent(stage: str, data: dict) -> None:
    """The non-streaming routes take no progress."""


@router.post("/dumps", response_model=Proposal)
def create_dump(body: DumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep) -> Proposal:
    return _propose(repo, model, user, kind="text", text=body.text, object_name=None)


@router.post("/dumps/from-upload", response_model=Proposal)
def create_dump_from_upload(
    body: UploadDumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, store: StoreDep
) -> Proposal:
    kind, text = _read_upload(body, user, model, store, _silent)
    return _propose(repo, model, user, kind=kind, text=text, object_name=body.resume_object)


@router.post("/dumps/stream")
def stream_dump(body: DumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep):
    """`POST /dumps`, streamed: `progress` frames as each step starts and each
    section finishes, then one `proposal` frame (ADR 0005 wire format)."""
    return stream_response(
        _with_progress(
            lambda tell: _propose(
                repo, model, user, kind="text", text=body.text, object_name=None, on_progress=tell
            )
        )
    )


@router.post("/dumps/from-upload/stream")
def stream_dump_from_upload(
    body: UploadDumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, store: StoreDep
):
    """`POST /dumps/from-upload`, streamed. An upload takes about a minute;
    this is what lets the screen show where it is instead of a spinner."""

    def work(tell: Progress) -> Proposal:
        kind, text = _read_upload(body, user, model, store, tell)
        return _propose(
            repo, model, user, kind=kind, text=text, object_name=body.resume_object,
            on_progress=tell,
        )  # fmt: skip

    return stream_response(_with_progress(work))


def _with_progress(work: Callable[[Progress], Proposal]) -> Iterator[Frame]:
    """Run `work` in its own thread and yield its progress as it happens.

    The pipeline reports from several threads at once (one per section), so
    reports go through a queue; this generator is the one reader. It ends
    with the proposal, or an `error` frame carrying the same message the
    non-streaming route would have returned.
    """
    reports: queue.Queue[tuple[str, dict] | None] = queue.Queue()
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["proposal"] = work(lambda stage, data: reports.put((stage, data)))
        except Exception as exc:  # re-raised or reported below, on this side
            outcome["error"] = exc
        finally:
            reports.put(None)

    threading.Thread(target=run, daemon=True).start()
    while (report := reports.get()) is not None:
        stage, data = report
        yield ("progress", {"stage": stage, **data})
    if "error" in outcome:
        exc = outcome["error"]
        if isinstance(exc, HTTPException):
            yield ("error", {"message": exc.detail, "status": exc.status_code, "retryable": False})
            return
        raise exc  # ModelError and the unexpected: sse._events reports them
    yield ("proposal", outcome["proposal"].model_dump(mode="json"))


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
    proposal_id: str, body: ConfirmRequest, user: CurrentUser, repo: RepoDep
) -> EventOut:
    try:
        event = repo.confirm_proposal(user.uid, proposal_id, body.patch)
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
def add_entity(kind: Kind, body: EditRequest, user: CurrentUser, repo: RepoDep) -> EventOut:
    """Add one entry from a form, with no model call and no review (ADR 0022).
    The form's text becomes the dump the entry points back to."""
    repo.ensure_user(user.uid, user.email)
    text = source_text(kind, body.fields)
    try:
        patch = patch_for(kind, body.fields, evidence=text)
        event = repo.add_entry(user.uid, patch, text)
    except BadEntry as exc:
        raise HTTPException(422, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.patch("/entities/{kind}/{entity_id}", response_model=EventOut)
def edit_entity(
    kind: Kind, entity_id: str, body: EditRequest, user: CurrentUser, repo: RepoDep
) -> EventOut:
    try:
        event = repo.edit_entity(user.uid, kind, entity_id, body.fields)
    except NotFound as exc:
        raise HTTPException(404, f"No such {kind}.") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.delete("/entities/{kind}/{entity_id}", response_model=EventOut)
def retire_entity(kind: Kind, entity_id: str, user: CurrentUser, repo: RepoDep) -> EventOut:
    try:
        event = repo.retire_entity(user.uid, kind, entity_id)
    except NotFound as exc:
        raise HTTPException(404, f"No such {kind}.") from exc
    return EventOut(event=event, brain=repo.brain(user.uid))


@router.post("/discover")
def discover(
    body: DiscoverRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, settings: SettingsDep
):
    """Ask Donna about the confirmed garden (ADR 0017). Streams token frames,
    then one `citations` frame naming the entries the answer relies on. With
    `voice: true` (a question asked out loud, ADR 0032) `audio` frames ride beside the tokens."""
    repo.ensure_user(user.uid, user.email)
    # Checked before the stream opens, so an empty garden is a plain 422 rather
    # than an error frame inside a 200.
    _, labels = repo.brain_index(user.uid)
    if not labels:
        raise HTTPException(
            422, "Your Digital Garden is empty. Capture something first, then ask Donna about it."
        )
    garden = repo.brain_context(user.uid)
    return stream_response(
        answer(body, garden=garden, labels=labels, model=model, voice=settings.donna_voice)
    )


@router.post("/discover/read-aloud")
def discover_read_aloud(body: ReadAloudRequest, model: ModelDep, settings: SettingsDep):
    """Donna reads out an answer already on screen (ADR 0032): `audio` frames
    only, one per sentence. Each clip is a usage row like any other."""
    return stream_response(read_aloud(body, model=model, voice=settings.donna_voice))


class DiscoverTranscribeRequest(BaseModel):
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    object_name: str = Field(max_length=200)


@router.post("/discover/transcribe", response_model=Transcript)
def discover_transcribe(
    body: DiscoverTranscribeRequest, user: CurrentUser, model: ModelDep, store: StoreDep
) -> Transcript:
    """A question asked out loud (ADR 0030, 0032), as text. The browser
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
