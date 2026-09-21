"""Resume uploads (ADR 0010).

    POST /uploads  {filename, content_type, size_bytes}
                -> {object_name, upload_url, expires_in_seconds}

The browser then PUTs the file to `upload_url` with the same Content-Type and
passes `object_name` as `resume_object` when starting an interview. Objects
live under `uploads/<uid>/`, and `interview.start` refuses any object outside
the caller's own prefix.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from anyview.api.auth import CurrentUser, current_user
from anyview.uploads.extract import ALLOWED_TYPES, MAX_UPLOAD_BYTES, SIGNED_URL_TTL_SECONDS
from anyview.uploads.store import UploadStore

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


@router.post("", response_model=UploadTicket)
def create_upload(body: UploadRequest, user: CurrentUser, store: StoreDep) -> UploadTicket:
    if body.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Upload a PDF, Word (.docx), PNG, JPG, or WebP file.")
    if body.size_bytes > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "That file is over 10 MB. Please upload a smaller one.")

    # The object name is ours, not the browser's: a fresh UUID under the user's
    # prefix, with the extension implied by the declared type. The original
    # filename is not part of the name, so nothing in a filename can escape it.
    object_name = f"{object_prefix(user.uid)}{uuid.uuid4()}{ALLOWED_TYPES[body.content_type]}"
    return UploadTicket(
        object_name=object_name,
        upload_url=store.signed_put_url(object_name, body.content_type),
        expires_in_seconds=SIGNED_URL_TTL_SECONDS,
    )
