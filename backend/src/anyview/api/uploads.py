"""Resume uploads (ADR 0010).

    POST /uploads  {filename, content_type, size_bytes}
                -> {object_name, upload_url, expires_in_seconds}

The browser then PUTs the file to `upload_url` with the same Content-Type and
passes `object_name` as `resume_object` when starting an interview. Objects
live under `uploads/<uid>/`, and `interview.start` refuses any object outside
the caller's own prefix.

Recorded answers (ADR 0013) take the same route but live under `audio/<uid>/`
instead. A separate root, not a subfolder of `uploads/`, because a bucket
lifecycle rule matches on a literal prefix and cannot wildcard the uid in the
middle — and recordings expire after 30 days while resumes never do.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from anyview.api.auth import CurrentUser, current_user
from anyview.llm.adapter import Model
from anyview.uploads.extract import (
    ALLOWED_TYPES,
    AUDIO_TYPES,
    EXTENSION_TYPES,
    MAX_UPLOAD_BYTES,
    SIGNED_URL_TTL_SECONDS,
    ExtractionError,
    audio_to_text,
)
from anyview.uploads.store import MemoryUploadStore, UploadStore, UploadTooLarge

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(current_user)])


def get_store() -> UploadStore:  # overridden in main.py and tests
    raise NotImplementedError


StoreDep = Annotated[UploadStore, Depends(get_store)]


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(gt=0)


class UploadTicket(BaseModel):
    object_name: str
    upload_url: str
    expires_in_seconds: int
    # Sent with the PUT as-is: the size limit is signed into the URL (store.SIZE_HEADER).
    upload_headers: dict[str, str] = {}


def object_prefix(uid: str) -> str:
    return f"uploads/{uid}/"


def audio_prefix(uid: str) -> str:
    return f"audio/{uid}/"


def prefix_for(content_type: str, uid: str) -> str:
    return audio_prefix(uid) if content_type in AUDIO_TYPES else object_prefix(uid)


def transcribe_recording(
    object_name: str,
    *,
    uid: str,
    store: UploadStore,
    model: Model,
    session_id: str,
    what: str = "the candidate's answer",
) -> str:
    """A recording the browser uploaded, as the words that were said.

    Shared by an interview answer (ADR 0013) and a question asked out loud in
    Discover (ADR 0030). The browser uploads straight to the bucket and sends
    only the object name, the same shape as a resume upload (ADR 0010)."""
    # Only the caller's own recordings, by the prefix the ticket route set from
    # the verified uid. This is the whole authorisation check.
    if not object_name.startswith(audio_prefix(uid)):
        raise HTTPException(403, "That recording isn't yours.")
    suffix = object_name[object_name.rfind(".") :]
    mime = EXTENSION_TYPES.get(suffix)
    if mime is None:
        raise HTTPException(415, "That recording format isn't supported.")
    try:
        data = store.read(object_name)
    except UploadTooLarge as exc:
        raise HTTPException(413, "That recording is over 10 MB.") from exc
    if data is None:
        raise HTTPException(404, "The recording wasn't found. Please record it again.")
    try:
        return audio_to_text(data, mime, model=model, session_id=session_id, what=what)
    except ExtractionError as exc:
        raise HTTPException(422, exc.user_message) from exc


@router.post("", response_model=UploadTicket)
def create_upload(body: UploadRequest, user: CurrentUser, store: StoreDep) -> UploadTicket:
    types = {**ALLOWED_TYPES, **AUDIO_TYPES}
    if body.content_type not in types:
        raise HTTPException(415, "Upload a PDF or Word (.docx) file.")
    if body.size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That file is over 10 MB. Please upload a smaller one.")

    # The object name is ours, not the browser's: a fresh UUID under the user's
    # prefix, with the extension implied by the declared type. The original
    # filename is not part of the name, so nothing in a filename can escape it.
    prefix = prefix_for(body.content_type, user.uid)
    object_name = f"{prefix}{uuid.uuid4()}{types[body.content_type]}"
    return UploadTicket(
        object_name=object_name,
        upload_url=store.signed_put_url(object_name, body.content_type),
        expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        upload_headers=store.put_headers(),
    )


@router.put("/memory/{object_name:path}", status_code=204)
async def memory_put(
    object_name: str, request: Request, user: CurrentUser, store: StoreDep
) -> Response:
    """Local fake-mode only: somewhere for the browser to PUT to.

    `MemoryUploadStore` has no bucket behind it, so the "signed URL" it hands
    out points back here. Answers 404 against the real store, which keeps the
    rule from ADR 0010 intact: in production, file bytes never transit the API.
    """
    if not isinstance(store, MemoryUploadStore):
        raise HTTPException(404, "Not found.")
    if not object_name.startswith((object_prefix(user.uid), audio_prefix(user.uid))):
        raise HTTPException(403, "That upload isn't yours.")
    data = await request.body()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That file is over 10 MB. Please upload a smaller one.")
    store.put(object_name, data)
    return Response(status_code=204)
