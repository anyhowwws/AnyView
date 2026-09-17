"""FastAPI application entry point.

Cloud Run starts this with `uvicorn anyview.main:app`. Wiring only: settings,
CORS, error translation, the model singleton, and the routers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anyview.api import auth, brain, interview, uploads
from anyview.config import Settings
from anyview.interview.engine import EngineError
from anyview.llm.adapter import Model, ModelError

logging.basicConfig(level=logging.INFO, format="%(message)s")

settings = Settings.from_env()


@lru_cache(maxsize=1)
def build_engine():
    """The database engine, or None when none is configured (Phase 0 routes
    still work; /brain answers 503)."""
    from anyview.db.connection import make_engine

    return make_engine(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine = build_engine()
    if engine is not None:
        from anyview.db.migrate import migrate

        applied = migrate(engine)
        if applied:
            logging.getLogger(__name__).info("applied migrations: %s", applied)
    yield
    if engine is not None:
        engine.dispose()


app = FastAPI(title="AnyView API", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list from config, never "*"
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@lru_cache(maxsize=1)
def build_model() -> Model:
    """One model client per process. Built on first use so importing the app
    (tests, `--help`) never touches GCP."""
    if settings.use_fake_model:
        from anyview.llm.fake import FakeModel

        return FakeModel()
    from anyview.llm.adapter import VertexGemini

    return VertexGemini(
        project_id=settings.project_id,
        region=settings.vertex_region,
        model=settings.model_id,
        fast_model=settings.fast_model_id,
    )


@lru_cache(maxsize=1)
def build_store():
    """One upload store per process. In-memory when running on the fake model
    (no bucket needed for a token-free local walk-through)."""
    if settings.use_fake_model:
        from anyview.uploads.store import MemoryUploadStore

        return MemoryUploadStore()
    from anyview.uploads.store import GcsUploadStore

    return GcsUploadStore(
        bucket=settings.upload_bucket, signer_service_account=settings.signer_service_account
    )


def build_repository():
    from fastapi import HTTPException

    from anyview.db.repository import Repository

    engine = build_engine()
    if engine is None:
        raise HTTPException(503, "The brain needs a database and none is configured.")
    return Repository(engine)


app.dependency_overrides[interview.get_model] = build_model
app.dependency_overrides[uploads.get_store] = build_store
app.dependency_overrides[brain.get_repository] = build_repository
app.dependency_overrides[interview.get_repository_optional] = lambda: (
    build_repository() if build_engine() is not None else None
)
app.dependency_overrides[auth.get_settings] = lambda: settings
app.dependency_overrides[auth.get_verifier] = lambda: auth.verify_firebase_token(settings)
app.include_router(interview.router)
app.include_router(uploads.router)
app.include_router(brain.router)


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
