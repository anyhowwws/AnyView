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
from anyview.uploads.extract import (
    ALLOWED_TYPES,
    AUDIO_TYPES,
    MAX_UPLOAD_BYTES,
    SIGNED_URL_TTL_SECONDS,
)
from anyview.uploads.store import MemoryUploadStore, UploadStore

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


def object_prefix(uid: str) -> str:
    return f"uploads/{uid}/"


def audio_prefix(uid: str) -> str:
    return f"audio/{uid}/"


def prefix_for(content_type: str, uid: str) -> str:
    return audio_prefix(uid) if content_type in AUDIO_TYPES else object_prefix(uid)


@router.post("", response_model=UploadTicket)
def create_upload(body: UploadRequest, user: CurrentUser, store: StoreDep) -> UploadTicket:
    types = {**ALLOWED_TYPES, **AUDIO_TYPES}
    if body.content_type not in types:
        raise HTTPException(415, "Upload a PDF, Word (.docx), PNG, JPG, WebP, or audio file.")
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
    store.put(object_name, await request.body())
    return Response(status_code=204)
