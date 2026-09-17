"""Who is calling. Every interview route depends on `current_user`.

The browser signs in with Google through Firebase Authentication (Identity
Platform) and sends the resulting ID token as `Authorization: Bearer …`. This
module verifies that token against Google's public keys and checks the email
against the allow-list. Nothing here talks to a database; the user is just
`(uid, email)` for now — Phase 1's repository will key rows on `uid`.

Verification uses `google-auth`, which is already installed as part of the
Vertex SDK stack, so no new dependency. Google's signing certificates are
fetched over HTTPS and cached by the transport between calls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from anyview.config import Settings

log = logging.getLogger(__name__)

# One transport for the process: it caches Google's certificates.
_transport = google_requests.Request()


@dataclass(frozen=True)
class User:
    uid: str
    email: str


Verifier = Callable[[str], dict[str, Any]]
"""Takes a raw ID token, returns its claims or raises ValueError. Tests swap
this for a fake so no network is involved."""


def verify_firebase_token(settings: Settings) -> Verifier:
    def verify(token: str) -> dict[str, Any]:
        # `audience` pins the token to this Firebase project; a token minted for
        # any other project fails here even if Google signed it.
        return id_token.verify_firebase_token(token, _transport, audience=settings.project_id)

    return verify


def fake_verifier(token: str) -> dict[str, Any]:
    """Dev only, wired in main.py when ANYVIEW_FAKE_MODEL=1: a token of the form
    `fake:<email>` signs that email in. The allow-list still applies."""
    if not token.startswith("fake:"):
        raise ValueError("not a fake token")
    email = token.removeprefix("fake:")
    return {"sub": f"fake-{email}", "email": email, "email_verified": True}


def get_verifier(request: Request) -> Verifier:  # overridden in main.py and tests
    raise NotImplementedError


def get_settings(request: Request) -> Settings:  # overridden in main.py
    raise NotImplementedError


def current_user(
    request: Request,
    verifier: Annotated[Verifier, Depends(get_verifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue.")
    token = header.removeprefix("Bearer ").strip()

    try:
        claims = verifier(token)
    except ValueError as exc:  # expired, wrong project, bad signature, malformed
        log.info("rejected id token: %s", exc)
        raise HTTPException(401, "Your sign-in has expired. Please sign in again.") from exc

    email = str(claims.get("email", "")).lower()
    if not email or not claims.get("email_verified", False):
        raise HTTPException(403, "This account has no verified email address.")
    if email not in settings.allowed_emails:
        log.warning("sign-in from an email not on the allow-list: %s", email)
        raise HTTPException(403, "This account isn't on the access list for AnyView.")

    return User(uid=str(claims["sub"]), email=email)


CurrentUser = Annotated[User, Depends(current_user)]
