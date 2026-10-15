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
    assert kinds.count("token") >= 1
    assert kinds[-1] == "done"
    text = "".join(d["text"] for e, d in events if e == "token")
    # A fixed lead-in, then the planned question word for word.
    assert text.endswith(session["questions"][0]["text"])
    assert len(text) > len(session["questions"][0]["text"])


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
    assert report["items"][0]["ideal"]["has_material"] is True


def test_streamed_report_sends_the_header_then_each_item(client, setup):
    session = _start(client, setup)
    for i in range(5):
        r = client.post(
            "/interview/answer",
            json={"session": session, "answer": {"question_id": i + 1, "text": f"answer {i + 1}"}},
        )
        session = r.json()

    with client.stream("POST", "/interview/report/stream", json=session) as r:
        assert r.status_code == 200
        events = _sse_events(r)
    kinds = [e for e, _ in events]
    assert kinds == ["report"] + ["item"] * 5 + ["done"]
    assert events[0][1]["items"] == [] and "total" not in events[0][1]
    items = {d["index"]: d["item"] for e, d in events if e == "item"}
    assert sorted(items) == [0, 1, 2, 3, 4]
    assert all(items[i]["question"]["id"] == i + 1 for i in items)
    assert all(len(item["dimensions"]) == 4 for item in items.values())


def test_streamed_report_before_wrap_is_a_409_not_a_stream(client, setup):
    session = _start(client, setup)
    r = client.post("/interview/report/stream", json=session)
    assert r.status_code == 409


# --- Failure paths -------------------------------------------------------------


def test_no_resume_and_no_database_is_a_readable_422(client, setup):
    """Nothing sent and nothing on file. With a database this would fall back to
    the resume the user already gave us (ADR 0014); without one there is
    nowhere for that to have been kept, and the message says so."""
    body = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": ""}}
    r = client.post("/interview/start", json=body)
    assert r.status_code == 422
    assert "no resume on file" in r.json()["detail"]

    short = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": "too short"}}
    r = client.post("/interview/start", json=short)
    assert r.status_code == 422
    assert "at least 50 characters" in r.json()["detail"]


def test_oversize_resume_is_a_422(client, setup):
    body = {"session_id": "sess-0001", "setup": {**setup.model_dump(), "resume": "x" * 15_001}}
    r = client.post("/interview/start", json=body)
    assert r.status_code == 422
    assert "at most 15000 characters" in r.json()["detail"]


@pytest.mark.parametrize("session_id", ["s1", "x" * 65])
def test_a_malformed_session_id_is_a_422_on_every_route_that_takes_one(client, setup, session_id):
    """It used to pass the request model and fail inside Session, as a 500."""
    bodies = {
        "/interview/start": {"session_id": session_id, "setup": setup.model_dump()},
        "/interview/say": {"session_id": session_id, "line": "stalled"},
        "/interview/transcribe": {"session_id": session_id, "object_name": "audio/x/a.webm"},
    }
    for route, body in bodies.items():
        r = client.post(route, json=body)
        assert r.status_code == 422, (route, r.status_code, r.text)
        assert r.json()["errors"][0]["loc"] == ["body", "session_id"], route


def test_answer_to_wrong_question_is_a_409(client, setup):
    session = _start(client, setup)
    r = client.post(
        "/interview/answer",
        json={"session": session, "answer": {"question_id": 4, "text": "x"}},
    )
    assert r.status_code == 409
    assert "Expected an answer to question 1" in r.json()["detail"]


def test_the_answer_route_adapts_between_questions(client, setup, fake):
    # ADR 0036: between two questions the planner may reword the next one.
    fake.replies["adapt"] = {
        "notes": "Led the billing migration.",
        "rewrite": True,
        "text": "Tell me about a time you owned something nobody asked you to.",
        "rationale": "They already covered the migration.",
    }
    session = _start(client, setup)
    r = client.post(
        "/interview/answer",
        json={"session": session, "answer": {"question_id": 1, "text": "answer 1"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["questions"][1]["text"].startswith("Tell me about a time you owned")
    assert body["questions"][1]["planned"] == session["questions"][1]["text"]
    assert body["notes"] == "Led the billing migration."


def test_report_before_wrap_is_a_409(client, setup):
    session = _start(client, setup)
    r = client.post("/interview/report", json=session)
    assert r.status_code == 409


def test_ask_on_finished_session_is_a_409_not_a_stream(client, setup):
    session = _start(client, setup)
    session["state"] = "wrap"
    r = client.post("/interview/ask", json=session)
    assert r.status_code == 409


def test_asking_makes_no_model_call(client, fake, setup):
    session = _start(client, setup)
    before = len(fake.calls)
    with client.stream("POST", "/interview/ask", json=session) as r:
        _sse_events(r)
    assert len(fake.calls) == before


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
    for method in ("PATCH", "DELETE"):  # the Brain screen's edit and retire
        pre = client.options(
            "/brain/entities/story/x",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": method},
        )
        assert method in pre.headers.get("access-control-allow-methods", ""), method


# --- Cutting long text to fit (Setup's limits) ---------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "word " * 3_000,  # no line breaks at all: rfind's -1 used to keep it all
        "line of text\n" * 1_000,  # line breaks all the way through
        "x" * 9_000,  # no break of any kind
    ],
)
def test_truncated_text_fits_the_limit_note_included(text):
    from anyview.api.interview import MAX_JD_CHARS, _truncate

    cut = _truncate(text, MAX_JD_CHARS, "The job description")
    assert len(cut) <= MAX_JD_CHARS
    assert cut.endswith("was cut to fit.]")


def test_short_text_is_untouched():
    from anyview.api.interview import _truncate

    assert _truncate("short", 100, "x") == "short"
