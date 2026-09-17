"""Shared fixtures. A realistic Setup so prompt and engine tests read naturally."""

import pytest

from anyview.api import auth, uploads
from anyview.config import Settings
from anyview.interview.models import Setup
from anyview.main import app
from anyview.uploads.store import MemoryUploadStore

ALLOWED = "jordan@example.com"

# Claims a verifier returns for each fake token. Tests never touch Google.
FAKE_TOKENS = {
    "good": {"sub": "uid-jordan", "email": ALLOWED, "email_verified": True},
    "upper": {"sub": "uid-jordan", "email": ALLOWED.upper(), "email_verified": True},
    "unverified": {"sub": "uid-x", "email": ALLOWED, "email_verified": False},
    "stranger": {"sub": "uid-y", "email": "someone@example.com", "email_verified": True},
}


def fake_verifier(token: str) -> dict:
    try:
        return FAKE_TOKENS[token]
    except KeyError:
        raise ValueError("Token is not valid") from None


@pytest.fixture
def store():
    """An in-memory upload store, shared by the client and the test body."""
    memory = MemoryUploadStore()
    app.dependency_overrides[uploads.get_store] = lambda: memory
    yield memory
    app.dependency_overrides.pop(uploads.get_store, None)


@pytest.fixture
def signed_in(store):
    """Wire the auth dependencies to the fake verifier and a one-email allow-list."""
    app.dependency_overrides[auth.get_verifier] = lambda: fake_verifier
    app.dependency_overrides[auth.get_settings] = lambda: Settings(
        project_id="test",
        vertex_region="global",
        model_id="m",
        fast_model_id="m",
        allowed_emails=frozenset({ALLOWED}),
    )
    yield
    app.dependency_overrides.pop(auth.get_verifier, None)
    app.dependency_overrides.pop(auth.get_settings, None)


RESUME = """Jordan Lee — Cloud Solutions Architect

Acme Corp (2021–present) — Senior Cloud Architect
- Led migration of the billing service from VMs to Cloud Run, cutting monthly infra cost 38%.
- Designed the Terraform module library now used by 6 product teams.
- Ran the on-call rota redesign after two Sev-1 incidents; MTTR dropped from 4h to 50m.

Globex (2018–2021) — DevOps Engineer
- Built the CI/CD pipeline for 40 microservices on GitHub Actions.
- Introduced cost dashboards that surfaced $120k/yr of idle resources.
"""


@pytest.fixture
def setup() -> Setup:
    return Setup(
        resume=RESUME,
        company="Initech",
        role="Cloud Architect",
        seniority="senior",
        job_description="Own the platform roadmap. Strong communication with product teams.",
    )
