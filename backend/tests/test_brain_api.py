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


def _confirmed(client):
    p = _dump(client)
    r = client.post(f"/brain/proposals/{p['id']}/confirm", json={"patch": p["patch"]})
    assert r.status_code == 200, r.text
    return r.json()["brain"]


def _discover(client, question="What have I migrated?", history=()):
    return client.post(
        "/brain/discover",
        json={"conversation_id": "conv-12345678", "question": question, "history": list(history)},
    )


def test_discover_on_an_empty_garden_is_a_422(client):
    r = _discover(client)
    assert r.status_code == 422 and "empty" in r.json()["detail"]


def test_discover_streams_an_answer_with_resolved_citations(client):
    from tests.test_api import _sse_events

    b = _confirmed(client)
    fake = FakeModel()
    app.dependency_overrides[interview.get_model] = lambda: fake
    r = _discover(
        client, history=[{"role": "user", "text": "Hi"}, {"role": "donna", "text": "Hello"}]
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r)
    assert [e for e, _ in events][-2:] == ["citations", "done"]
    entities = events[-2][1]["entities"]
    assert entities == [
        {"label": "P1", "id": b["projects"][0]["id"], "kind": "project"},
        {"label": "S1", "id": b["stories"][0]["id"], "kind": "story"},
    ]
    call = fake.calls[0]
    assert "Billing service migration to Cloud Run" in call["system"]  # the confirmed garden
    assert "Candidate: Hi\n\nDonna: Hello" in call["user"]


def test_discover_reads_only_confirmed_entries(client):
    _confirmed(client)
    fake = FakeModel(
        {
            "propose": {
                "roles": [],
                "projects": [
                    {
                        "key": "p1", "existing": None, "role": None,
                        "name": "Bedrock claims triage", "problem": None, "action": None,
                        "result": None, "tech": ["Bedrock"], "metrics": [],
                        "evidence": "Built a Bedrock claims triage pipeline.",
                    }
                ],
                "stories": [], "skills": [], "achievements": [],
            }
        }
    )  # fmt: skip
    app.dependency_overrides[interview.get_model] = lambda: fake
    r = client.post("/brain/dumps", json={"text": "Built a Bedrock claims triage pipeline."})
    assert r.status_code == 200, r.text  # pending, not confirmed
    _discover(client, question="What have I built with Bedrock?")
    garden = fake.calls[-1]["system"].split("<digital_garden>")[-1]
    assert "Billing service" in garden and "Bedrock" not in garden


def test_discover_is_scoped_to_the_signed_in_user(client):
    from tests.conftest import FAKE_TOKENS

    _confirmed(client)
    FAKE_TOKENS["stranger3"] = {
        "sub": "uid-stranger3",
        "email": "jordan@example.com",
        "email_verified": True,
    }
    other = TestClient(app, headers={"Authorization": "Bearer stranger3"})
    assert _discover(other).status_code == 422  # their garden is empty; ours is not read


def test_discover_rejects_a_bad_conversation_id(client):
    _confirmed(client)
    r = client.post("/brain/discover", json={"conversation_id": "../x", "question": "Hi"})
    assert r.status_code == 422


# --- Streamed ingestion (ADR 0019) --------------------------------------------

from tests.test_api import _sse_events  # noqa: E402


def test_a_streamed_upload_reports_each_step_then_the_proposal(client, store):
    name = "uploads/uid-jordan/x.docx"
    store.put(name, _docx_bytes(RESUME.splitlines()))
    with client.stream(
        "POST", "/brain/dumps/from-upload/stream", json={"resume_object": name}
    ) as r:
        assert r.status_code == 200
        events = _sse_events(r)
    stages = [data["stage"] for event, data in events if event == "progress"]
    assert stages == ["reading", "read", "sections", "section_done", "tidying", "linking"]
    done = next(d for e, d in events if e == "progress" and d["stage"] == "section_done")
    assert done["names"][0] == "Senior Cloud Architect, Acme Corp"  # the role leads
    assert "Terraform" in done["names"] and len(done["names"]) == done["found"]
    sections = next(d for e, d in events if e == "progress" and d["stage"] == "sections")
    assert sections["sections"] == [{"id": 0, "kind": "document", "label": ""}]
    kinds = [event for event, _ in events]
    assert kinds[-2:] == ["proposal", "done"]
    assert events[-2][1]["dump_kind"] == "resume_docx"
    assert client.get("/brain").json()["pending_proposals"] == 1


def test_a_streamed_failure_is_an_error_frame_with_the_same_message(client, store):
    with client.stream(
        "POST",
        "/brain/dumps/from-upload/stream",
        json={"resume_object": "uploads/uid-other/x.docx"},
    ) as r:
        events = _sse_events(r)
    assert events[-2:] == [
        ("error", {"message": "That upload isn't yours.", "status": 403, "retryable": False}),
        ("done", {}),
    ]


def test_a_streamed_text_dump_ends_in_the_same_proposal_shape(client):
    with client.stream("POST", "/brain/dumps/stream", json={"text": DUMP}) as r:
        events = _sse_events(r)
    proposal = next(d for e, d in events if e == "proposal")
    assert proposal["patch"]["roles"][0]["company"] == "Acme Corp"
