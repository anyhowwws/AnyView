# ruff: noqa: E501
"""The Brain routes end to end: FakeModel for extraction, a real Postgres for
the repository, the fake verifier for sign-in. Two users, to prove isolation."""

import pytest
from fastapi.testclient import TestClient

from anyview.api import brain, interview
from anyview.db.repository import Repository
from anyview.llm.fake import FakeModel
from anyview.main import app
from tests.conftest import RESUME
from tests.test_uploads import _docx_bytes

DUMP = (
    "At Acme Corp (2021–present) — Senior Cloud Architect. Led migration of the billing "
    "service from VMs to Cloud Run, cutting monthly infra cost 38%. Ran the on-call rota "
    "redesign after two Sev-1 incidents; MTTR dropped from 4h to 50m. Designed the Terraform "
    "module library now used by 6 product teams."
)


@pytest.fixture
def client(db, signed_in):
    repo = Repository(db)
    app.dependency_overrides[brain.get_repository] = lambda: repo
    app.dependency_overrides[interview.get_model] = lambda: FakeModel()
    yield TestClient(app, headers={"Authorization": "Bearer good"})
    app.dependency_overrides.pop(brain.get_repository, None)
    app.dependency_overrides.pop(interview.get_model, None)


def _dump(client, text=DUMP):
    r = client.post("/brain/dumps", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_brain(client):
    r = client.get("/brain")
    assert r.status_code == 200
    b = r.json()
    assert b["roles"] == [] and b["pending_proposals"] == 0
    assert [c["key"] for c in b["coverage"]["competencies"]][:2] == ["ownership", "ambiguity"]
    assert b["coverage"]["cells"]["ownership"] == {"other": "none"}


def test_dump_creates_a_pending_proposal_with_evidence(client):
    p = _dump(client)
    assert p["status"] == "pending"
    assert p["patch"]["roles"][0]["company"] == "Acme Corp"
    assert p["patch"]["stories"][0]["evidence"].startswith("Ran the on-call rota redesign")
    assert p["dump_kind"] == "text" and "dump_excerpt" not in p
    assert client.get("/brain").json()["pending_proposals"] == 1
    assert [q["id"] for q in client.get("/brain/proposals").json()] == [p["id"]]


def test_confirm_applies_the_reviewed_patch(client):
    p = _dump(client)
    patch = p["patch"]
    patch["stories"][0]["title"] = "Rota redesign (edited in review)"  # the user edited a field
    patch["skills"] = []  # and rejected a draft
    r = client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": patch})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["event"]["kind"] == "patch_confirmed" and out["event"]["seq"] == 1
    b = out["brain"]
    assert b["pending_proposals"] == 0
    assert [s["title"] for s in b["stories"]] == ["Rota redesign (edited in review)"]
    assert b["skills"] == []
    assert b["projects"][0]["role_id"] == b["roles"][0]["id"]
    rid = b["roles"][0]["id"]
    assert b["coverage"]["cells"]["ownership"][rid] == "strong"
    assert b["coverage"]["cells"]["failure"][rid] == "strong"
    assert b["coverage"]["cells"]["conflict"][rid] == "none"


def test_confirm_twice_is_409_and_unknown_is_404(client):
    p = _dump(client)
    assert (
        client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]}).status_code
        == 200
    )
    assert (
        client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]}).status_code
        == 409
    )
    assert (
        client.post(
            "/brain/proposals/00000000-0000-0000-0000-000000000000/confirm",
            json={"patch": p["patch"]},
        ).status_code
        == 404
    )


def test_discard(client):
    p = _dump(client)
    r = client.post(f"/brain/proposals/{p['id']}/discard")
    assert r.status_code == 200 and r.json()["pending_proposals"] == 0
    assert client.post(f"/brain/proposals/{p['id']}/discard").status_code == 404
    assert client.get("/brain/events").json() == []


def test_edit_retire_and_events(client):
    p = _dump(client)
    b = client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]}).json()[
        "brain"
    ]
    story = b["stories"][0]
    r = client.patch(
        f"/brain/entities/story/{story['id']}",
        json={"fields": {"result": "MTTR 4h → 50m, sustained for a year"}},
    )
    assert r.status_code == 200 and r.json()["brain"]["stories"][0]["result"].endswith("a year")
    assert (
        client.patch(
            f"/brain/entities/story/{story['id']}", json={"fields": {"user_id": "x"}}
        ).status_code
        == 409
    )
    r = client.delete(f"/brain/entities/skill/{b['skills'][0]['id']}")
    assert r.status_code == 200 and r.json()["brain"]["skills"] == []
    assert [e["kind"] for e in client.get("/brain/events").json()] == [
        "patch_confirmed",
        "entity_edited",
        "entity_retired",
    ]
    assert client.delete(f"/brain/entities/skill/{b['skills'][0]['id']}").status_code == 404


def test_dump_source_is_readable_and_scoped(client, db):
    p = _dump(client)
    r = client.get(f"/brain/dumps/{p['raw_dump_id']}")
    assert r.status_code == 200 and r.json()["text"] == DUMP
    # another signed-in user cannot see it
    from tests.conftest import FAKE_TOKENS

    FAKE_TOKENS["stranger2"] = {
        "sub": "uid-stranger",
        "email": "jordan@example.com",
        "email_verified": True,
    }
    other = TestClient(app, headers={"Authorization": "Bearer stranger2"})
    assert other.get(f"/brain/dumps/{p['raw_dump_id']}").status_code == 404
    assert other.get("/brain").json()["roles"] == []
    assert (
        other.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]}).status_code
        == 404
    )


def test_dump_from_upload_goes_through_the_same_queue(client, store):
    name = "uploads/uid-jordan/x.docx"
    store.put(name, _docx_bytes(RESUME.splitlines()))
    r = client.post("/brain/dumps/from-upload", json={"resume_object": name})
    assert r.status_code == 200, r.text
    assert r.json()["dump_kind"] == "resume_docx"
    assert (
        client.post(
            "/brain/dumps/from-upload", json={"resume_object": "uploads/uid-other/x.docx"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/brain/dumps/from-upload", json={"resume_object": "uploads/uid-jordan/missing.pdf"}
        ).status_code
        == 404
    )


def test_useless_dump_is_a_422(client):
    fake = FakeModel(
        {"propose": {"roles": [], "projects": [], "stories": [], "skills": [], "achievements": []}}
    )
    app.dependency_overrides[interview.get_model] = lambda: fake
    r = client.post(
        "/brain/dumps", json={"text": "The weather was nice today and I had a sandwich."}
    )
    assert r.status_code == 422 and "nothing about your experience" in r.json()["detail"]


def test_brain_routes_require_sign_in(signed_in):
    c = TestClient(app)
    assert c.get("/brain").status_code == 401
    assert c.post("/brain/dumps", json={"text": DUMP}).status_code == 401


def test_feedback_flows_through_the_review_queue(client):
    fake = FakeModel(
        {
            "propose": {
                "roles": [],
                "projects": [],
                "stories": [],
                "skills": [],
                "achievements": [],
                "feedback": [
                    {
                        "key": "f1",
                        "existing": None,
                        "role": None,
                        "project": None,
                        "given_by": "Manager, 2024 review",
                        "content": "You owned the migration end to end.",
                        "received_on": "2024-11-01",
                        "evidence": "You owned the migration end to end.",
                    }
                ],
            }
        }
    )
    app.dependency_overrides[interview.get_model] = lambda: fake
    p = _dump(client, text="You owned the migration end to end.")
    assert p["patch"]["feedback"][0]["given_by"] == "Manager, 2024 review"

    r = client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]})
    assert r.status_code == 200, r.text
    feedback = r.json()["brain"]["feedback"]
    assert feedback[0]["content"] == "You owned the migration end to end."

    r = client.patch(
        f"/brain/entities/feedback/{feedback[0]['id']}",
        json={"fields": {"content": "Edited in review"}},
    )
    assert (
        r.status_code == 200 and r.json()["brain"]["feedback"][0]["content"] == "Edited in review"
    )

    r = client.delete(f"/brain/entities/feedback/{feedback[0]['id']}")
    assert r.status_code == 200 and r.json()["brain"]["feedback"] == []
