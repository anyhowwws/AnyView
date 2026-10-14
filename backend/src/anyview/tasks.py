"""Handing a job to the worker (ADR 0034).

`enqueue(job_id)` is all the API does with a queued job. Two ways to do it,
chosen in main.py by configuration:

  - `CloudTasksQueue` (Cloud Run): one Cloud Tasks task per job. Cloud Tasks
    calls the private worker service with an OIDC token minted for the
    `anyview-tasks` service account, and retries with backoff until the worker
    answers 2xx or the queue's attempts run out.
  - `InlineQueue` (a laptop, tests, `ANYVIEW_FAKE_MODEL=1`): runs the job in
    this process, once, with no retries.

Cloud Tasks is called over its REST API with `google-auth`'s authorised
session rather than the `google-cloud-tasks` client library: one POST does not
justify a gRPC stack in the image (ADR 0034).
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger(__name__)

# What the worker answers on. One route; the job id is the whole message.
INGEST_PATH = "/tasks/ingest"

# How long Cloud Tasks waits for the worker to answer one delivery. A resume
# takes about 90 s; the worker service's own timeout is the same (infra/worker.tf).
DISPATCH_DEADLINE = "600s"


class QueueError(Exception):
    """The job could not be handed over; nothing will run it."""


class TaskQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class CloudTasksQueue:
    def __init__(self, *, queue: str, worker_url: str, invoker: str) -> None:
        # queue: projects/<p>/locations/<r>/queues/<name>, from Terraform.
        self.queue = queue
        self.worker_url = worker_url.rstrip("/")
        self.invoker = invoker
        self._session = None  # built on first use, so importing never touches GCP

    def _authorised(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._session = AuthorizedSession(credentials)
        return self._session

    def task(self, job_id: str) -> dict:
        """The task resource for one job. Named after the job, so a second
        enqueue of the same job is refused by Cloud Tasks (ALREADY_EXISTS)
        instead of running it twice."""
        body = json.dumps({"job_id": job_id}).encode()
        return {
            "name": f"{self.queue}/tasks/{job_id}",
            "dispatchDeadline": DISPATCH_DEADLINE,
            "httpRequest": {
                "url": self.worker_url + INGEST_PATH,
                "httpMethod": "POST",
                "headers": {"Content-Type": "application/json"},
                "body": base64.b64encode(body).decode(),
                # Cloud Tasks signs a token as this service account; Cloud Run
                # checks it holds run.invoker on the worker before our code runs.
                "oidcToken": {"serviceAccountEmail": self.invoker, "audience": self.worker_url},
            },
        }

    def enqueue(self, job_id: str) -> None:
        url = f"https://cloudtasks.googleapis.com/v2/{self.queue}/tasks"
        try:
            res = self._authorised().post(url, json={"task": self.task(job_id)}, timeout=10)
        except Exception as exc:  # network, credentials
            raise QueueError(str(exc)) from exc
        if res.status_code == 409:  # ALREADY_EXISTS: this job is already queued
            return
        if not res.ok:
            raise QueueError(f"Cloud Tasks answered {res.status_code}: {res.text[:300]}")


class InlineQueue:
    """Runs the job here. `background=True` (local dev) returns at once, as
    Cloud Tasks would; tests pass False so the job is finished on return."""

    def __init__(self, run: Callable[[str], object], *, background: bool = True) -> None:
        self.run = run
        self.background = background

    def enqueue(self, job_id: str) -> None:
        if not self.background:
            self.run(job_id)
            return
        # A daemon thread dies with the process, like the old in-request
        # thread did. Fine on a laptop; on Cloud Run this class is not used.
        threading.Thread(target=self._run_logged, args=(job_id,), daemon=True).start()

    def _run_logged(self, job_id: str) -> None:
        try:
            self.run(job_id)
        except Exception:
            log.exception("inline ingest job %s failed", job_id)
