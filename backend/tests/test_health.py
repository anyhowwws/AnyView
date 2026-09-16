from fastapi.testclient import TestClient

from anyview.main import app

# TestClient runs the app in-process — no server, no network. Each call is a real
# HTTP request as far as FastAPI is concerned.
client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
