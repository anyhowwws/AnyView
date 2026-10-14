"""The ingestion worker (ADR 0034): what Cloud Tasks calls.

Same image as the API, its own Cloud Run service (`anyview-worker`), started
with `APP_MODULE=anyview.worker:app`. The service is private: only the
`anyview-tasks` service account may invoke it, and Cloud Run checks that
before a request reaches this code. So there is no sign-in here; the job id
is the whole message, and the job's row says whose it is.

One route. Its status code is the only thing Cloud Tasks reads:

  2xx  stop: the job is done, failed for good, or already gone
  409  another delivery of this job is running it (at-least-once delivery)
  503  failed in a way worth retrying; Cloud Tasks backs off and calls again
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

# The API's wiring is reused as is: the same settings, model, upload store and
# database, and the same startup (migrations, usage rows for every model call).
from anyview.main import build_model, build_repository, build_store, lifespan, settings
from anyview.tasks import INGEST_PATH

log = logging.getLogger(__name__)

app = FastAPI(title="AnyView worker", version="0.0.1", lifespan=lifespan)

STATUS = {"retry": 503, "busy": 409}  # anything else: 204


class IngestTask(BaseModel):
    job_id: str


@app.post(INGEST_PATH)
def ingest(body: IngestTask, request: Request) -> Response:
    from anyview.brain.ingest import run_job

    # Cloud Tasks counts retries from 0, so the first delivery is attempt 1.
    attempt = int(request.headers.get("X-CloudTasks-TaskRetryCount", "0")) + 1
    final = attempt >= settings.ingest_max_attempts
    outcome = run_job(
        body.job_id,
        repo=build_repository(),
        model=build_model(),
        store=build_store(),
        final=final,
    )
    log.info("ingest job %s attempt %d: %s", body.job_id, attempt, outcome)
    return Response(status_code=STATUS.get(outcome, 204))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
