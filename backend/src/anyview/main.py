"""FastAPI application entry point.

Cloud Run starts this with `uvicorn anyview.main:app`. Wiring only: settings,
CORS, error translation, the model singleton, and the routers.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anyview.api import interview
from anyview.config import Settings
from anyview.interview.engine import EngineError
from anyview.llm.adapter import Model, ModelError

logging.basicConfig(level=logging.INFO, format="%(message)s")

settings = Settings.from_env()
app = FastAPI(title="AnyView API", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list from config, never "*"
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@lru_cache(maxsize=1)
def build_model() -> Model:
    """One model client per process. Built on first use so importing the app
    (tests, `--help`) never touches GCP."""
    if settings.use_fake_model:
        from anyview.llm.fake import FakeModel

        return FakeModel()
    from anyview.llm.adapter import VertexClaude

    return VertexClaude(
        project_id=settings.project_id,
        region=settings.vertex_region,
        model=settings.claude_model,
    )


app.dependency_overrides[interview.get_model] = build_model
app.include_router(interview.router)


# --- Error translation: every failure is {"detail": <sentence>} -------------


@app.exception_handler(EngineError)
def engine_error(_: Request, exc: EngineError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.user_message})


@app.exception_handler(ModelError)
def model_error(_: Request, exc: ModelError) -> JSONResponse:
    status = 503 if exc.retryable else 502
    return JSONResponse(
        status_code=status, content={"detail": exc.user_message, "retryable": exc.retryable}
    )


@app.exception_handler(RequestValidationError)
def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's error list is precise but not friendly. Turn the first one
    # into a sentence the UI can show, keep the full list for debugging.
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p != "body")
    return JSONResponse(
        status_code=422,
        content={"detail": f"{field}: {first['msg']}", "errors": exc.errors()},
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Cloud Run and CI both hit this to confirm the container is up."""
    return {"status": "ok"}
