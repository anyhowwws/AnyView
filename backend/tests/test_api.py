"""End-to-end through FastAPI with the FakeModel injected. No network."""

import json

import pytest
from fastapi.testclient import TestClient

from anyview.api import interview
from anyview.llm.fake import FakeModel
from anyview.main import app


@pytest.fixture
def fake():
    return FakeModel()


@pytest.fixture
def client(fake, signed_in):
    app.dependency_overrides[interview.get_model] = lambda: fake
    yield TestClient(app, headers={"Authorization": "Bearer good"})
    app.dependency_overrides.pop(interview.get_model, None)


def _start(client, setup, session_id="sess-0001"):
    r = client.post(
        "/interview/start", json={"session_id": session_id, "setup": setup.model_dump()}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _sse_events(response):
    """Parse the SSE body into (event, data) pairs; comment frames are dropped."""
    events, event = [], None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: ") and event:
            events.append((event, json.loads(line[len("data: ") :])))
            event = None
    return events


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_start_returns_a_session_in_ask_with_five_questions(client, setup):
    session = _start(client, setup)
    assert session["state"] == "ask"
    assert [q["id"] for q in session["questions"]] == [1, 2, 3, 4, 5]
    assert session["current"] == 0


def test_ask_streams_tokens_then_done(client, setup):
    session = _start(client, setup)
    with client.stream("POST", "/interview/ask", json=session) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r)
    kinds = [e for e, _ in events]
    assert kinds.count("token") > 1
    assert kinds[-1] == "done"
    text = "".join(d["text"] for e, d in events if e == "token")
    assert "tell me about a time" in text.lower()


def test_full_journey_to_report(client, setup):
    session = _start(client, setup)
    for i in range(5):
        with client.stream("POST", "/interview/ask", json=session) as r:
            assert r.status_code == 200
        r = client.post(
            "/interview/answer",
            json={"session": session, "answer": {"question_id": i + 1, "text": f"answer {i + 1}"}},
        )
        assert r.status_code == 200, r.text
        session = r.json()
    assert session["state"] == "wrap"

    r = client.post("/interview/report", json=session)
    assert r.status_code == 200, r.text
    report = r.json()
    assert len(report["items"]) == 5
    assert all(len(item["dimensions"]) == 4 for item in report["items"])
    assert "total" not in report
    assert report["items"][0]["ideal"]["resume_has_material"] is True


# --- Failure paths -------------------------------------------------------------


def test_empty_resume_is_a_readable_422(client, setup):
    body = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": ""}}
    r = client.post("/interview/start", json=body)
    assert r.status_code == 422
    assert "Upload a resume or paste its text" in r.json()["detail"]

    short = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": "too short"}}
    r = client.post("/interview/start", json=short)
    assert r.status_code == 422
    assert "at least 50 characters" in r.json()["detail"]


def test_oversize_resume_is_a_422(client, setup):
    body = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": "x" * 15_001}}
    r = client.post("/interview/start", json=body)
    assert r.status_code == 422
    assert "at most 15000 characters" in r.json()["detail"]


def test_answer_to_wrong_question_is_a_409(client, setup):
    session = _start(client, setup)
    r = client.post(
        "/interview/answer",
        json={"session": session, "answer": {"question_id": 4, "text": "x"}},
    )
    assert r.status_code == 409
    assert "Expected an answer to question 1" in r.json()["detail"]


def test_report_before_wrap_is_a_409(client, setup):
    session = _start(client, setup)
    r = client.post("/interview/report", json=session)
    assert r.status_code == 409


def test_ask_on_finished_session_is_a_409_not_a_stream(client, setup):
    session = _start(client, setup)
    session["state"] = "wrap"
    r = client.post("/interview/ask", json=session)
    assert r.status_code == 409


def test_model_failure_during_ask_is_an_error_event(setup, signed_in):
    fake = FakeModel(fail="ask")
    app.dependency_overrides[interview.get_model] = lambda: fake
    try:
        client = TestClient(app, headers={"Authorization": "Bearer good"})
        session = _start(client, setup)
        with client.stream("POST", "/interview/ask", json=session) as r:
            events = _sse_events(r)
        assert events == [("error", {"message": "fake failure", "retryable": True})]
    finally:
        app.dependency_overrides.pop(interview.get_model, None)


def test_model_failure_during_start_is_a_503(setup, signed_in):
    app.dependency_overrides[interview.get_model] = lambda: FakeModel(fail="plan")
    try:
        r = TestClient(app, headers={"Authorization": "Bearer good"}).post(
            "/interview/start", json={"session_id": "sess-0001", "setup": setup.model_dump()}
        )
        assert r.status_code == 503
        assert r.json()["retryable"] is True
    finally:
        app.dependency_overrides.pop(interview.get_model, None)


def test_cors_allows_configured_origin_only(client):
    ok = client.options(
        "/interview/start",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options(
        "/interview/start",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers
    assert "authorization" in ok.headers.get("access-control-allow-headers", "").lower()
