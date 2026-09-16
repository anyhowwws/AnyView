from anyview.config import Settings


def test_defaults_when_env_is_empty(monkeypatch):
    for key in ("GOOGLE_CLOUD_PROJECT", "VERTEX_REGION", "CLAUDE_MODEL", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert s.project_id == ""
    assert s.vertex_region == "global"
    assert s.claude_model == "claude-opus-5"
    assert s.cors_origins == ["http://localhost:3000"]
    assert s.use_fake_model is False


def test_cors_origins_are_split_and_trimmed(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " https://a.web.app , http://localhost:3000 ")
    monkeypatch.setenv("ANYVIEW_FAKE_MODEL", "1")
    s = Settings.from_env()
    assert s.cors_origins == ["https://a.web.app", "http://localhost:3000"]
    assert s.use_fake_model is True
