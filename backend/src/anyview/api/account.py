"""The signed-in user's account as a whole. One route: erase it (ADR 0018).

Erasing removes the user's files from Cloud Storage and every row about them
from the database. It does not touch their Google sign-in record in Identity
Platform; the browser deletes that itself right after, because only a
freshly signed-in client may (and the API has no Identity Platform admin
rights, on purpose).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from anyview.api.auth import CurrentUser, current_user
from anyview.api.interview import get_repository_optional
from anyview.api.uploads import StoreDep, audio_prefix, object_prefix

log = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(current_user)])

RepoDep = Annotated[Any, Depends(get_repository_optional)]


class EraseRequest(BaseModel):
    # The phrase the user types to confirm. Checked here too, so a stray or
    # scripted call without it erases nothing.
    confirm: Literal["delete my data"]


class EraseOut(BaseModel):
    files: int
    rows: int


@router.post("/erase", response_model=EraseOut)
def erase(body: EraseRequest, user: CurrentUser, repo: RepoDep, store: StoreDep) -> EraseOut:
    # Files first. If the bucket fails, nothing in the database has gone yet
    # and the user can simply try again. The other order could leave files
    # behind with no account left to find them from.
    try:
        files = store.delete_prefix(object_prefix(user.uid)) + store.delete_prefix(
            audio_prefix(user.uid)
        )
    except Exception as exc:
        log.exception("erase: deleting files failed for %s", user.uid)
        raise HTTPException(
            502, "Couldn't delete your files. Nothing was erased; try again."
        ) from exc
    removed = repo.erase_user(user.uid) if repo is not None else {}
    # Counts only: no content, no email. This line is the record that it happened.
    log.info("erase: uid=%s files=%d rows=%s", user.uid, files, removed)
    return EraseOut(files=files, rows=sum(removed.values()))
