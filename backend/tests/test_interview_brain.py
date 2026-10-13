# ruff: noqa: E501
"""The interview's situation, end to end (ADR 0014): the resume on file, the
difficulty that decides what the interviewer knows, and the review queue that a
replaced resume feeds without repeating itself (ADR 0015)."""

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
    c.repo = repo  # type: ignore[attr-defined]
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


def _upload(client, store, name=f"uploads/{UID}/cv.docx", lines=None):
    store.put(name, _docx_bytes(lines or RESUME.splitlines()))
    return name


def _call(client, name):
    return next((c for c in client.fake.calls if c["call"] == name), None)


def _finish(client, session):
    for i in range(5):
        session = client.post(
            "/interview/answer",
            json={"session": session, "answer": {"question_id": i + 1, "text": "a"}},
        ).json()
    return client.post("/interview/report", json=session)


# --- The resume on file ------------------------------------------------------


def test_nothing_on_file_says_so(client):
    assert client.get("/interview/resume").json()["dump_id"] is None
    r = client.post("/interview/start", json={"session_id": "sess-0001", "setup": _setup()})
    assert r.status_code == 422
    assert "Donna needs your resume first" in r.json()["detail"]


def test_an_upload_becomes_the_resume_on_file(client, store):
    name = _upload(client, store)
    r = client.post(
        "/interview/start", json={"session_id": "sess-0001", "setup": _setup(resume_object=name)}
    )
    assert r.status_code == 200, r.text

    on_file = client.get("/interview/resume").json()
    assert on_file["kind"] == "resume_docx" and on_file["characters"] > 50
    assert client.get(f"/brain/dumps/{on_file['dump_id']}").json()["object_name"] == name


def test_the_second_interview_needs_no_upload_and_re_reads_nothing(client, store):
    client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=_upload(client, store))},
    )
    client.fake.calls.clear()

    r = client.post("/interview/start", json={"session_id": "sess-0002", "setup": _setup()})
    assert r.status_code == 200, r.text
    assert "Acme Corp" in r.json()["setup"]["resume"]
    # Planning only: no second extraction, and nothing new to propose.
    assert [c["call"] for c in client.fake.calls] == ["plan"]


def test_a_resume_upload_queues_a_proposal(client, store):
    r = client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=_upload(client, store))},
    )
    assert r.status_code == 200 and r.json()["state"] == "ask"
    assert sorted(c["call"] for c in client.fake.calls) == ["link", "plan", "propose"]
    assert client.get("/brain").json()["pending_proposals"] == 1
    assert client.get("/brain/proposals").json()[0]["dump_kind"] == "resume_docx"


def test_re_uploading_the_same_resume_proposes_nothing_twice(client, store):
    """Identical extracted text is a no-op: the pointer moves, the queue does
    not grow, and no model call is spent reading it again (ADR 0015)."""
    first = _upload(client, store, name=f"uploads/{UID}/v1.docx")
    client.post(
        "/interview/start", json={"session_id": "sess-0001", "setup": _setup(resume_object=first)}
    )
    before = client.get("/interview/resume").json()
    client.fake.calls.clear()

    again = _upload(client, store, name=f"uploads/{UID}/v2.docx")
    r = client.post(
        "/interview/start", json={"session_id": "sess-0002", "setup": _setup(resume_object=again)}
    )
    assert r.status_code == 200, r.text
    assert [c["call"] for c in client.fake.calls] == ["plan"]  # no second `propose`
    assert client.get("/brain").json()["pending_proposals"] == 1
    # Same text, so it stays pointed at the dump that already holds it.
    assert client.get("/interview/resume").json()["dump_id"] == before["dump_id"]


def test_a_changed_resume_queues_only_what_changed(client, store):
    """The whole point of ADR 0015: the second upload's queue is what is new in
    it, not a restatement of everything the user already confirmed."""
    _fill_brain(client)
    brain_now = client.get("/brain").json()
    role, story = brain_now["roles"][0], brain_now["stories"][0]

    # The model recognises both, and one of them has genuinely changed.
    client.fake.replies["propose"] = {
        **{k: [] for k in ("roles", "projects", "stories", "skills", "achievements")},
        "roles": [
            {
                "key": "r1",
                "existing": role["label"],
                "company": role["company"],
                "title": role["title"],
                "start_date": role["start_date"],
                "end_date": role["end_date"],
                "level": "principal",  # the one real change
                "evidence": "Acme Corp (2021–present) — Senior Cloud Architect",
            }
        ],
        "stories": [
            {
                "key": "s1",
                "existing": story["label"],
                "role": "r1",
                "project": None,
                "title": story["title"],
                "situation": story["situation"],
                "task": story["task"],
                "action": story["action"],
                "result": story["result"],
                "competencies": list(reversed(story["competencies"])),  # same set, new order
                "evidence": "Ran the on-call rota redesign after two Sev-1 incidents; MTTR dropped from 4h to 50m.",
            }
        ],
    }
    client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=_upload(client, store))},
    )
    queued = client.get("/brain/proposals").json()[0]["patch"]
    assert [d["level"] for d in queued["roles"]] == ["principal"]
    assert queued["stories"] == []  # reordering a list is not a change
    # The story was dropped, but the role it referenced still resolves.
    assert queued["roles"][0]["existing"] == role["label"]


def test_absence_is_not_evidence(client, store):
    """A role missing from the new resume is not retired. Trimming a CV for one
    application is the normal reason a job vanishes from it (ADR 0015)."""
    _fill_brain(client)
    live = [r["id"] for r in client.get("/brain").json()["roles"]]
    client.fake.replies["propose"] = {
        k: [] for k in ("roles", "projects", "stories", "skills", "achievements")
    }
    client.fake.replies["propose"]["skills"] = [
        {
            "key": "k1",
            "existing": None,
            "name": "Kubernetes",
            "depth": 3,
            "projects": [],
            "evidence": "Built the CI/CD pipeline for 40 microservices on GitHub Actions.",
        }
    ]
    client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=_upload(client, store))},
    )
    assert [r["id"] for r in client.get("/brain").json()["roles"]] == live


# --- Difficulty decides what the interviewer knows ---------------------------


def test_below_panel_the_interviewer_never_sees_the_garden(client, store):
    _fill_brain(client)
    name = _upload(client, store)
    for level in ("recruiter_screen", "hiring_manager"):
        client.fake.calls.clear()
        r = client.post(
            "/interview/start",
            json={
                "session_id": f"sess-{level[:4]}01",
                "setup": _setup(resume_object=name, difficulty=level),
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["setup"]["garden"] is None
        assert "<digital_garden>" not in _call(client, "plan")["system"]


def test_at_panel_the_interviewer_has_done_their_homework(client, store):
    _fill_brain(client)
    r = client.post(
        "/interview/start",
        json={
            "session_id": "sess-0001",
            "setup": _setup(resume_object=_upload(client, store), difficulty="panel"),
        },
    )
    assert r.status_code == 200, r.text
    setup = r.json()["setup"]
    assert setup["garden"].startswith("## [R1] Senior Cloud Architect at Acme Corp")
    system = _call(client, "plan")["system"]
    assert "<digital_garden>" in system and "done your homework" in system
    assert "[S1] On-call rota redesign after two Sev-1s" in system


def test_a_panel_with_an_empty_garden_still_runs(client, store):
    r = client.post(
        "/interview/start",
        json={
            "session_id": "sess-0001",
            "setup": _setup(resume_object=_upload(client, store), difficulty="panel"),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["setup"]["garden"] is None
    assert "no record beyond their CV" in _call(client, "plan")["system"]


def test_the_report_reads_the_garden_below_panel(client, store):
    """The interviewer did not have it; the coaching does (ADR 0014)."""
    _fill_brain(client)
    session = client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=_upload(client, store))},
    ).json()
    r = _finish(client, session)
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["difficulty"] == "hiring_manager" and report["garden_used"] is True
    ideal = _call(client, "ideal")
    assert "<digital_garden>" in ideal["user"]  # the user turn, after the cache breakpoint
    assert "<digital_garden>" not in ideal["system"]


def test_the_report_carries_the_room_it_was_conducted_in(client, store):
    session = client.post(
        "/interview/start",
        json={
            "session_id": "sess-0001",
            "setup": _setup(resume_object=_upload(client, store), difficulty="recruiter_screen"),
        },
    ).json()
    report = _finish(client, session).json()
    assert report["difficulty"] == "recruiter_screen"
    assert report["garden_used"] is False  # nothing confirmed, nothing to read


# --- The target job ----------------------------------------------------------


def test_an_uploaded_jd_comes_back_as_text_and_prefilled_fields(client, store):
    name = _upload(
        client,
        store,
        name=f"uploads/{UID}/jd.docx",
        lines=[
            "Cloud Architect — Initech",
            "Own the platform roadmap and the guardrails other teams build on.",
            "Required: Terraform, strong communication with product teams.",
        ],
    )
    r = client.post("/interview/job/parse", json={"object_name": name})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Own the platform roadmap" in body["text"]
    assert body["parsed"]["company"] == "Initech" and body["parsed"]["seniority"] == "senior"
    assert "Terraform" in body["parsed"]["must_haves"]


def test_a_jd_belonging_to_someone_else_is_a_403(client):
    r = client.post("/interview/job/parse", json={"object_name": "uploads/uid-other/jd.pdf"})
    assert r.status_code == 403


def test_an_empty_jd_is_a_readable_422(client, store):
    name = _upload(client, store, name=f"uploads/{UID}/jd.docx", lines=["hi"])
    r = client.post("/interview/job/parse", json={"object_name": name})
    assert r.status_code == 422 and "almost no text" in r.json()["detail"]


# --- Without a database ------------------------------------------------------


def test_without_a_database_the_resume_must_come_with_the_interview(signed_in, store):
    app.dependency_overrides[interview.get_model] = lambda: FakeModel()
    app.dependency_overrides[interview.get_repository_optional] = lambda: None
    try:
        c = TestClient(app, headers={"Authorization": "Bearer good"})
        assert c.get("/interview/resume").json()["dump_id"] is None
        r = c.post("/interview/start", json={"session_id": "sess-0001", "setup": _setup()})
        assert r.status_code == 422 and "no resume on file" in r.json()["detail"]

        name = _upload(c, store)
        r = c.post(
            "/interview/start",
            json={"session_id": "sess-0001", "setup": _setup(resume_object=name)},
        )
        assert r.status_code == 200  # the upload path still works with no database
    finally:
        app.dependency_overrides.pop(interview.get_model, None)
        app.dependency_overrides.pop(interview.get_repository_optional, None)


# --- Saved jobs (ADR 0025) -----------------------------------------------------

JD_LINES = [
    "Cloud Architect — Initech",
    "Own the platform roadmap and the guardrails other teams build on.",
    "Required: Terraform, strong communication with product teams.",
]


def test_starting_saves_the_job_and_practising_it_again_reuses_it(client, store):
    name = _upload(client, store)
    job = {"source": "manual", "fields": {"must_haves": "Terraform"}}
    r = client.post(
        "/interview/start",
        json={"session_id": "sess-0001", "setup": _setup(resume_object=name, job=job)},
    )
    assert r.status_code == 200, r.text
    saved = client.get("/interview/jobs").json()
    assert [(j["company"], j["role"], j["fields"]["must_haves"]) for j in saved] == [
        ("Initech", "Cloud Architect", "Terraform")
    ]

    # Picked from the list and corrected: the same entry, updated in place.
    job = {"id": saved[0]["id"], "source": "manual", "fields": {"must_haves": "Terraform\nGo"}}
    r = client.post(
        "/interview/start",
        json={"session_id": "sess-0002", "setup": _setup(seniority="staff", job=job)},
    )
    assert r.status_code == 200, r.text
    again = client.get("/interview/jobs").json()
    assert len(again) == 1 and again[0]["seniority"] == "staff"
    assert again[0]["fields"]["must_haves"] == "Terraform\nGo"


def test_an_interview_without_a_job_block_saves_nothing(client, store):
    name = _upload(client, store)
    r = client.post(
        "/interview/start", json={"session_id": "sess-0001", "setup": _setup(resume_object=name)}
    )
    assert r.status_code == 200 and client.get("/interview/jobs").json() == []


def test_a_posting_already_saved_skips_the_parse_call(client, store):
    name = _upload(client, store, name=f"uploads/{UID}/jd.docx", lines=JD_LINES)
    first = client.post("/interview/job/parse", json={"object_name": name}).json()
    assert first["saved_job"] is None
    cv = _upload(client, store)
    job = {"source": "upload", "fields": {"must_haves": "Terraform"}}
    client.post(
        "/interview/start",
        json={
            "session_id": "sess-0001",
            "setup": _setup(
                resume_object=cv, job_description=first["text"], seniority="staff", job=job
            ),
        },
    )

    client.fake.calls.clear()
    second = client.post("/interview/job/parse", json={"object_name": name}).json()
    assert second["saved_job"]["seniority"] == "staff"  # last time's correction, not a re-read
    assert second["parsed"]["must_haves"] == ["Terraform"]
    assert _call(client, "parse_job") is None


def test_deleting_a_saved_job(client, store):
    name = _upload(client, store)
    client.post(
        "/interview/start",
        json={
            "session_id": "sess-0001",
            "setup": _setup(resume_object=name, job={"source": "manual"}),
        },
    )
    job_id = client.get("/interview/jobs").json()[0]["id"]
    assert client.delete(f"/interview/jobs/{job_id}").status_code == 204
    assert client.delete(f"/interview/jobs/{job_id}").status_code == 404
    assert client.get("/interview/jobs").json() == []
