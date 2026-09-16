"""FastAPI application entry point.

Cloud Run starts this with `uvicorn anyview.main:app`. Everything the API does
hangs off the `app` object defined here; routers for interviews, brain, etc.
get included as each phase adds them.
"""

from fastapi import FastAPI

app = FastAPI(title="AnyView API", version="0.0.1")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Cloud Run and CI both hit this to confirm the container is up."""
    return {"status": "ok"}
