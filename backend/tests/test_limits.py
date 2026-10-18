# ruff: noqa: E501
"""The daily cap per user (ADR 0047): ten interviews and ten garden uploads per
UTC day, counted in one statement, given back when the work fails early."""

import pytest

from anyview.api import interview
from anyview.api.limits import DAILY_LIMIT
from anyview.db.repository import Repository
from anyview.llm.fake import FakeModel
from anyview.main import app
from tests.test_brain_api import DUMP
from tests.test_brain_api import client as brain_client  # noqa: F401  (fixture)
from tests.test_interview_brain import _setup, _upload
from tests.test_interview_brain import client as interview_client  # noqa: F401  (fixture)

UID = "uid-jordan"


@pytest.fixture
def repo(db):
    r = Repository(db)
    r.ensure_user(UID, "jordan@example.com")
    return r


def test_take_daily_stops_at_the_limit_and_counts_nothing_more(repo, db):
    assert all(repo.take_daily(UID, "interview", 3) for _ in range(3))
    assert not repo.take_daily(UID, "interview", 3)
    assert repo.take_daily(UID, "upload", 3)  # each action has its own count
    with db.begin() as c:
        rows = dict(c.exec_driver_sql("SELECT action, count FROM daily_usage").all())
    assert rows == {"interview": 3, "upload": 1}


def test_give_back_frees_a_slot_and_never_goes_below_zero(repo):
    repo.give_back_daily(UID, "interview")  # nothing taken yet: a no-op
    assert repo.take_daily(UID, "interview", 1)
    assert not repo.take_daily(UID, "interview", 1)
    repo.give_back_daily(UID, "interview")
    assert repo.take_daily(UID, "interview", 1)


def test_the_eleventh_interview_of_the_day_is_refused(interview_client, store):  # noqa: F811
    name = _upload(interview_client, store)
    for i in range(DAILY_LIMIT):
        r = interview_client.post(
            "/interview/start",
            json={"session_id": f"sess-{i:04d}", "setup": _setup(resume_object=name)},
        )
        assert r.status_code == 200, r.text
    r = interview_client.post(
        "/interview/start", json={"session_id": "sess-0099", "setup": _setup(resume_object=name)}
    )
    assert r.status_code == 429
    assert r.json()["detail"].startswith(f"You've started {DAILY_LIMIT} interviews today")


def test_a_failed_start_does_not_use_up_the_day(interview_client):  # noqa: F811
    # Nothing on file and no resume given: 422, and the slot comes back.
    for i in range(DAILY_LIMIT + 2):
        r = interview_client.post(
            "/interview/start", json={"session_id": f"sess-{i:04d}", "setup": _setup()}
        )
        assert r.status_code == 422


def test_the_eleventh_upload_of_the_day_is_refused(brain_client):  # noqa: F811
    for _ in range(DAILY_LIMIT):
        assert brain_client.post("/brain/jobs", json={"text": DUMP}).status_code == 202
    r = brain_client.post("/brain/jobs", json={"text": DUMP})
    assert r.status_code == 429 and "daily limit" in r.json()["detail"]
    # The synchronous route shares the same count.
    assert brain_client.post("/brain/dumps", json={"text": DUMP}).status_code == 429


def test_entries_typed_in_a_form_are_not_counted(brain_client):  # noqa: F811
    for _ in range(DAILY_LIMIT):
        assert brain_client.post("/brain/jobs", json={"text": DUMP}).status_code == 202
    r = brain_client.post(
        "/brain/entities/skill", json={"fields": {"name": "Terraform", "depth": 3}}
    )
    assert r.status_code == 200, r.text


def test_without_a_database_there_is_no_limit(signed_in):
    from fastapi.testclient import TestClient

    from tests.conftest import RESUME

    fake = FakeModel()
    app.dependency_overrides[interview.get_model] = lambda: fake
    try:
        c = TestClient(app, headers={"Authorization": "Bearer good"})
        for i in range(DAILY_LIMIT + 1):
            r = c.post(
                "/interview/start",
                json={"session_id": f"sess-{i:04d}", "setup": _setup(resume=RESUME)},
            )
            assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(interview.get_model, None)
