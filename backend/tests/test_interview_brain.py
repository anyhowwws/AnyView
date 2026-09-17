# ruff: noqa: E501
"""Step 6: the brain as an interview source, and resume uploads flowing into the queue."""

import pytest
from fastapi.testclient import TestClient

from anyview.api import brain, interview
from anyview.db.repository import Repository
from anyview.llm.fake import FakeModel
from anyview.main import app
from tests.conftest import RESUME
from tests.test_brain_api import DUMP
from tests.test_uploads import _docx_bytes

UID = "uid-jordan"


@pytest.fixture
def client(db, signed_in):
    repo = Repository(db)
    fake = FakeModel()
    app.dependency_overrides[brain.get_repository] = lambda: repo
    app.dependency_overrides[interview.get_repository_optional] = lambda: repo
    app.dependency_overrides[interview.get_model] = lambda: fake
    c = TestClient(app, headers={"Authorization": "Bearer good"})
    c.fake = fake  # type: ignore[attr-defined]
    yield c
    for dep in (brain.get_repository, interview.get_repository_optional, interview.get_model):
        app.dependency_overrides.pop(dep, None)


def _setup(**over):
    return {"company": "Initech", "role": "Cloud Architect", "seniority": "senior", **over}


def _fill_brain(client):
    p = client.post("/brain/dumps", json={"text": DUMP}).json()
    return client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]}).json()[
        "brain"
    ]


def test_use_brain_renders_the_confirmed_record_with_labels(client):
    _fill_brain(client)
    r = client.post("/interview/start", json={"session_id": "s1", "setup": _setup(use_brain=True)})
    assert r.status_code == 200, r.text
    setup = r.json()["setup"]
    assert setup["source"] == "brain" and setup["resume_object"] is None
    assert setup["resume"].startswith("## [R1] Senior Cloud Architect at Acme Corp")
    assert "[S1] On-call rota redesign after two Sev-1s" in setup["resume"]
    plan_call = next(c for c in client.fake.calls if c["call"] == "plan")
    assert 'confirmed "second brain"' in plan_call["system"]
    assert "cite these labels" in plan_call["system"]


def test_use_brain_with_an_empty_brain_is_a_422(client):
    r = client.post("/interview/start", json={"session_id": "s1", "setup": _setup(use_brain=True)})
    assert r.status_code == 422 and "still empty" in r.json()["detail"]


def test_exactly_one_source(client):
    both = _setup(use_brain=True, resume="x" * 60)
    assert (
        client.post("/interview/start", json={"session_id": "s1", "setup": both}).status_code == 422
    )


def test_report_carries_the_source(client):
    _fill_brain(client)
    session = client.post(
        "/interview/start", json={"session_id": "s1", "setup": _setup(use_brain=True)}
    ).json()
    for i in range(5):
        session = client.post(
            "/interview/answer",
            json={"session": session, "answer": {"question_id": i + 1, "text": "a"}},
        ).json()
    report = client.post("/interview/report", json=session).json()
    assert report["source"] == "brain"


def test_upload_with_add_to_brain_queues_a_proposal_alongside_the_interview(client, store):
    name = f"uploads/{UID}/cv.docx"
    store.put(name, _docx_bytes(RESUME.splitlines()))
    r = client.post(
        "/interview/start",
        json={"session_id": "s1", "setup": _setup(resume_object=name, add_to_brain=True)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "ask"
    calls = sorted(c["call"] for c in client.fake.calls)
    assert calls == ["plan", "propose"]  # both ran, once each
    b = client.get("/brain").json()
    assert b["pending_proposals"] == 1
    q = client.get("/brain/proposals").json()[0]
    assert q["dump_kind"] == "resume_docx"


def test_upload_without_add_to_brain_queues_nothing(client, store):
    name = f"uploads/{UID}/cv.docx"
    store.put(name, _docx_bytes(RESUME.splitlines()))
    r = client.post(
        "/interview/start", json={"session_id": "s1", "setup": _setup(resume_object=name)}
    )
    assert r.status_code == 200
    assert client.get("/brain").json()["pending_proposals"] == 0


def test_brain_source_without_a_database_is_a_503(signed_in):
    app.dependency_overrides[interview.get_model] = lambda: FakeModel()
    app.dependency_overrides[interview.get_repository_optional] = lambda: None
    try:
        c = TestClient(app, headers={"Authorization": "Bearer good"})
        r = c.post("/interview/start", json={"session_id": "s1", "setup": _setup(use_brain=True)})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.pop(interview.get_model, None)
        app.dependency_overrides.pop(interview.get_repository_optional, None)
