"""The sign-in gate on every interview route. No network: see conftest.fake_verifier."""

from fastapi.testclient import TestClient

from anyview.api import interview
from anyview.config import Settings
from anyview.llm.fake import FakeModel
from anyview.main import app


def _client(token: str | None):
    app.dependency_overrides[interview.get_model] = lambda: FakeModel()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(app, headers=headers)


def _start(client, setup):
    return client.post(
        "/interview/start", json={"session_id": "sess-0001", "setup": setup.model_dump()}
    )


def test_health_needs_no_sign_in(signed_in):
    assert _client(None).get("/health").status_code == 200


def test_missing_token_is_401(setup, signed_in):
    r = _start(_client(None), setup)
    assert r.status_code == 401
    assert r.json()["detail"] == "Sign in to continue."


def test_invalid_token_is_401(setup, signed_in):
    r = _start(_client("garbage"), setup)
    assert r.status_code == 401
    assert "sign in again" in r.json()["detail"]


def test_unverified_email_is_403(setup, signed_in):
    assert _start(_client("unverified"), setup).status_code == 403


def test_email_not_on_list_is_403(setup, signed_in):
    r = _start(_client("stranger"), setup)
    assert r.status_code == 403
    assert "access list" in r.json()["detail"]


def test_allow_list_is_case_insensitive(setup, signed_in):
    assert _start(_client("upper"), setup).status_code == 200


def test_every_interview_route_is_guarded(setup, signed_in):
    c = _client(None)
    assert c.post("/interview/ask", json={}).status_code == 401
    assert c.post("/interview/answer", json={}).status_code == 401
    assert c.post("/interview/report", json={}).status_code == 401


def test_fake_verifier_only_accepts_fake_tokens():
    from anyview.api.auth import fake_verifier

    assert fake_verifier("fake:dev@example.com") == {
        "sub": "fake-dev@example.com",
        "email": "dev@example.com",
        "email_verified": True,
    }
    import pytest as _pytest

    with _pytest.raises(ValueError):
        fake_verifier("eyJhbGciOi...")


def test_empty_allow_list_lets_nobody_in(monkeypatch):
    for key in ("ALLOWED_EMAILS",):
        monkeypatch.delenv(key, raising=False)
    assert Settings.from_env().allowed_emails == frozenset()


def test_allow_list_is_parsed_and_lowercased(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", " A@Example.com, b@example.com ,")
    assert Settings.from_env().allowed_emails == frozenset({"a@example.com", "b@example.com"})
