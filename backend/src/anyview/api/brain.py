"""The second brain's routes (ADR 0002). Every route requires a signed-in,
allow-listed user; every repository call is scoped by that user's uid."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from anyview.api.auth import CurrentUser, current_user
from anyview.api.interview import ModelDep
from anyview.api.uploads import StoreDep, object_prefix
from anyview.brain.extract import ExtractionFailed, propose
from anyview.brain.models import Brain, Event, Patch, Proposal, RawDump
from anyview.db.repository import Conflict, NotFound, Repository
from anyview.uploads.extract import (
    ALLOWED_TYPES,
    ExtractionError,
    diagram_to_text,
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
    repo: Repository, model, user: CurrentUser, *, kind: str, text: str, object_name: str | None
) -> Proposal:
    repo.ensure_user(user.uid, user.email)
    dump = repo.create_dump(user.uid, kind=kind, text=text, object_name=object_name)
    index, _ = repo.brain_index(user.uid)
    try:
        patch = propose(text, brain_index=index, model=model, session_id=f"dump-{dump.id[:8]}")
    except ExtractionFailed as exc:
        raise HTTPException(502, exc.user_message) from exc
    if patch.is_empty():
        raise HTTPException(
            422,
            "Donna found nothing about your experience in that. "
            "Try describing a role, a project, or a story.",
        )
    return repo.create_proposal(
        user.uid, dump_id=dump.id, patch=patch, model=getattr(model, "model", "fake")
    )


@router.post("/dumps", response_model=Proposal)
def create_dump(body: DumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep) -> Proposal:
    return _propose(repo, model, user, kind="text", text=body.text, object_name=None)


@router.post("/dumps/from-upload", response_model=Proposal)
def create_dump_from_upload(
    body: UploadDumpRequest, user: CurrentUser, repo: RepoDep, model: ModelDep, store: StoreDep
) -> Proposal:
    if not body.resume_object.startswith(object_prefix(user.uid)):
        raise HTTPException(403, "That upload isn't yours.")
    data = store.read(body.resume_object)
    if data is None:
        raise HTTPException(404, "The uploaded file wasn't found. Please upload it again.")
    try:
        if body.resume_object.endswith(".pdf"):
            kind, text = (
                "resume_pdf",
                pdf_to_text(data, model=model, session_id=f"upload-{uuid.uuid4().hex[:8]}"),
            )
        elif body.resume_object.endswith(".docx"):
            kind, text = "resume_docx", docx_to_text(data)
        elif body.resume_object.endswith((".png", ".jpg", ".webp")):
            suffix = body.resume_object.rsplit(".", 1)[-1]
            mime = {value.lstrip("."): key for key, value in ALLOWED_TYPES.items()}[suffix]
            # The original image remains in Cloud Storage as `object_name`; its
            # extracted description uses the existing text dump category. This
            # keeps production migrations additive: the app identity is not
            # allowed to alter the original raw_dumps check constraint.
            kind = "text"
            text = diagram_to_text(
                data, mime, model=model, session_id=f"upload-{uuid.uuid4().hex[:8]}"
            )
        else:
            raise HTTPException(415, "Upload a PDF, Word (.docx), PNG, JPG, or WebP file.")
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc
    if len(text.strip()) < 20:
        raise HTTPException(422, "The file has almost no text in it.")
    return _propose(repo, model, user, kind=kind, text=text, object_name=body.resume_object)


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


Kind = Literal["role", "project", "story", "skill", "achievement", "education", "language"]


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


@router.get("/events", response_model=list[Event])
def list_events(user: CurrentUser, repo: RepoDep) -> list[Event]:
    return repo.events(user.uid)
