"""Erasing an account through the API (ADR 0018): files, then rows, only yours."""

import pytest
from fastapi.testclient import TestClient

from anyview.api import brain, interview
from anyview.db.repository import Repository
from anyview.llm.fake import FakeModel
from anyview.main import app
from tests.conftest import FAKE_TOKENS
from tests.test_brain_api import DUMP

ERASE = {"confirm": "delete my data"}


@pytest.fixture
def client(db, signed_in):
    repo = Repository(db)
    app.dependency_overrides[brain.get_repository] = lambda: repo
    app.dependency_overrides[interview.get_repository_optional] = lambda: repo
    app.dependency_overrides[interview.get_model] = lambda: FakeModel()
    FAKE_TOKENS["other-user"] = {
        "sub": "uid-other",
        "email": "jordan@example.com",
        "email_verified": True,
    }
    yield TestClient(app, headers={"Authorization": "Bearer good"})
    for dep in (brain.get_repository, interview.get_repository_optional, interview.get_model):
        app.dependency_overrides.pop(dep, None)


def _grow(client) -> None:
    p = client.post("/brain/dumps", json={"text": DUMP}).json()
    r = client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]})
    assert r.status_code == 200, r.text


def test_erase_removes_your_files_and_garden_and_nobody_elses(client, store):
    other = TestClient(app, headers={"Authorization": "Bearer other-user"})
    _grow(client)
    _grow(other)
    store.put("uploads/uid-jordan/resume.pdf", b"%PDF")
    store.put("audio/uid-jordan/answer.webm", b"audio")
    store.put("uploads/uid-other/resume.pdf", b"%PDF")

    r = client.post("/account/erase", json=ERASE)

    assert r.status_code == 200, r.text
    assert r.json()["files"] == 2 and r.json()["rows"] > 0
    assert sorted(store.objects) == ["uploads/uid-other/resume.pdf"]
    assert client.get("/brain").json()["roles"] == []  # signing back in starts empty
    assert len(other.get("/brain").json()["roles"]) == 1


def test_erase_needs_the_exact_phrase(client, store):
    store.put("uploads/uid-jordan/resume.pdf", b"%PDF")
    for body in ({}, {"confirm": "yes"}, {"confirm": "Delete My Data "}):
        assert client.post("/account/erase", json=body).status_code == 422
    assert "uploads/uid-jordan/resume.pdf" in store.objects


def test_erase_requires_sign_in(signed_in):
    assert TestClient(app).post("/account/erase", json=ERASE).status_code == 401


def test_a_failed_file_delete_erases_nothing(client, store, monkeypatch):
    _grow(client)

    def broken(prefix):
        raise RuntimeError("bucket unavailable")

    monkeypatch.setattr(store, "delete_prefix", broken)
    r = client.post("/account/erase", json=ERASE)
    assert r.status_code == 502 and "Nothing was erased" in r.json()["detail"]
    assert len(client.get("/brain").json()["roles"]) == 1
