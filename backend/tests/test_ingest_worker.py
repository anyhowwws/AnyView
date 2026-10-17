"""The ingestion worker (ADR 0034): retries, at-least-once delivery, and the
status codes Cloud Tasks acts on. A real Postgres, the fake model, no Google."""

import base64
import datetime as dt
import json

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from anyview import worker
from anyview.brain import ingest
from anyview.brain.ingest import run_job
from anyview.db.repository import JobWork, Repository
from anyview.llm.fake import FakeModel
from anyview.tasks import CloudTasksQueue
from anyview.uploads.store import MemoryUploadStore
from tests.test_brain_api import DUMP

UID = "uid-jordan"


@pytest.fixture
def repo(db):
    r = Repository(db)
    r.ensure_user(UID, "jordan@example.com")
    return r


def _run(repo, job_id, model=None, *, final=False):
    return run_job(
        job_id, repo=repo, model=model or FakeModel(), store=MemoryUploadStore(), final=final
    )


def _dumps(db) -> int:
    with db.begin() as c:
        return c.execute(sa.text("SELECT count(*) FROM raw_dumps")).scalar_one()


def test_a_retryable_failure_asks_for_a_retry_and_the_retry_reuses_the_dump(repo, db):
    job = repo.create_job(UID, text=DUMP)
    assert _run(repo, job.id, FakeModel(fail="propose")) == "retry"
    assert repo.job(UID, job.id).status == "queued"  # waiting for the next delivery

    assert _run(repo, job.id) == "done"
    done = repo.job(UID, job.id)
    assert done.status == "done" and done.attempts == 2 and done.proposal is not None
    assert _dumps(db) == 1  # the second attempt did not store the text again


def test_the_last_attempt_fails_the_job_instead(repo):
    job = repo.create_job(UID, text=DUMP)
    assert _run(repo, job.id, FakeModel(fail="propose"), final=True) == "failed"
    failed = repo.job(UID, job.id)
    assert failed.status == "failed" and failed.error_status == 503
    assert failed.error == "fake failure"


def test_a_finished_or_unknown_job_is_not_run_again(repo):
    job = repo.create_job(UID, text=DUMP)
    assert _run(repo, job.id) == "done"
    assert _run(repo, job.id) == "gone"  # a duplicate delivery of a finished job
    assert _run(repo, "8d6f1e0a-0000-4000-8000-000000000000") == "gone"
    assert _run(repo, "not-a-uuid") == "gone"
    assert len(repo.pending_proposals(UID)) == 1


def test_two_deliveries_at_once_only_one_claims_the_job(repo):
    job = repo.create_job(UID, text=DUMP)
    assert isinstance(repo.claim_job(job.id, lease=ingest.LEASE), JobWork)
    assert repo.claim_job(job.id, lease=ingest.LEASE) == "busy"
    # Once the first delivery's heartbeat is older than the lease, it is
    # presumed dead and a later delivery takes the job over.
    taken = repo.claim_job(job.id, lease=dt.timedelta(0))
    assert isinstance(taken, JobWork) and repo.job(UID, job.id).attempts == 2


def test_a_job_nobody_is_working_on_reads_as_failed(repo, db):
    job = repo.create_job(UID, text=DUMP)
    with db.begin() as c:
        c.execute(
            sa.text("UPDATE ingest_jobs SET updated_at = now() - interval '1 hour' WHERE id = :id"),
            {"id": job.id},
        )
    stale = repo.job(UID, job.id)
    assert stale.status == "failed" and "stopped before she finished" in stale.error
    assert repo.active_jobs(UID) == []


def test_a_new_attempt_starts_its_progress_again(repo):
    job = repo.create_job(UID, text=DUMP)
    repo.claim_job(job.id, lease=ingest.LEASE)
    repo.report_job_progress(job.id, {"stage": "sections", "sections": []})
    assert len(repo.job(UID, job.id).progress) == 1
    repo.requeue_job(job.id)
    repo.claim_job(job.id, lease=ingest.LEASE)
    assert repo.job(UID, job.id).progress == []


# --- Cancelling a job ------------------------------------------------------------


class _CancelsOn(FakeModel):
    """A fake model that cancels the job the first time `call` is made, as a
    user clicking Cancel while Donna reads."""

    def __init__(self, repo, job_id, call):
        super().__init__()
        self._repo, self._job_id, self._call, self._done = repo, job_id, call, False

    def generate(self, **kwargs):
        if kwargs["call"] == self._call and not self._done:
            self._done = True
            self._repo.cancel_job(UID, self._job_id)
        return super().generate(**kwargs)


def test_cancelling_a_queued_job_means_its_task_finds_nothing_to_do(repo):
    job = repo.create_job(UID, text=DUMP)
    cancelled = repo.cancel_job(UID, job.id)
    assert cancelled.status == "failed" and cancelled.error == "Cancelled."
    assert cancelled.error_status == 499
    assert _run(repo, job.id) == "gone"  # Cloud Tasks delivers it anyway; nothing runs
    assert repo.pending_proposals(UID) == []


def test_a_job_cancelled_while_reading_stops_and_keeps_nothing(repo):
    job = repo.create_job(UID, text=DUMP)
    assert _run(repo, job.id, _CancelsOn(repo, job.id, "propose")) == "gone"
    ended = repo.job(UID, job.id)
    assert ended.status == "failed" and ended.error == "Cancelled." and ended.proposal is None
    assert repo.pending_proposals(UID) == []


def test_a_job_cancelled_during_the_last_step_leaves_no_proposal(repo):
    # `link` is the last model call: the proposal is built after the final progress
    # frame, so only finish_job can notice the cancel.
    job = repo.create_job(UID, text=DUMP)
    model = _CancelsOn(repo, job.id, "link")
    assert _run(repo, job.id, model) == "gone"
    assert any(c["call"] == "link" for c in model.calls)  # the cancel really came late
    assert repo.job(UID, job.id).status == "failed"
    assert repo.pending_proposals(UID) == []


def test_nothing_revives_or_rewrites_a_cancelled_job(repo):
    job = repo.create_job(UID, text=DUMP)
    repo.claim_job(job.id, lease=ingest.LEASE)
    repo.cancel_job(UID, job.id)
    repo.requeue_job(job.id)  # a retry handler running late
    repo.fail_job(job.id, "Something else", 500)
    ended = repo.job(UID, job.id)
    assert ended.status == "failed" and ended.error == "Cancelled."
    assert repo.report_job_progress(job.id, {"stage": "read"}) is False


def test_cancelling_a_finished_job_changes_nothing(repo):
    job = repo.create_job(UID, text=DUMP)
    assert _run(repo, job.id) == "done"
    assert repo.cancel_job(UID, job.id).status == "done"
    assert len(repo.pending_proposals(UID)) == 1


# --- The worker's HTTP face: what Cloud Tasks sees -----------------------------


@pytest.mark.parametrize(
    ("outcome", "status"),
    [("done", 204), ("failed", 204), ("gone", 204), ("retry", 503), ("busy", 409)],
)
def test_each_outcome_is_the_status_cloud_tasks_acts_on(monkeypatch, outcome, status):
    seen = {}

    def fake_run_job(job_id, *, repo, model, store, final):
        seen.update(job_id=job_id, final=final)
        return outcome

    monkeypatch.setattr(ingest, "run_job", fake_run_job)
    for name in ("build_repository", "build_model", "build_store"):
        monkeypatch.setattr(worker, name, lambda: None)
    client = TestClient(worker.app)  # not a context manager: no startup, no database

    r = client.post("/tasks/ingest", json={"job_id": "j1"})
    assert r.status_code == status and seen == {"job_id": "j1", "final": False}


def test_the_queues_last_attempt_is_marked_final(monkeypatch):
    finals = []
    monkeypatch.setattr(ingest, "run_job", lambda *a, final, **k: finals.append(final) or "done")
    for name in ("build_repository", "build_model", "build_store"):
        monkeypatch.setattr(worker, name, lambda: None)
    client = TestClient(worker.app)
    last = str(worker.settings.ingest_max_attempts - 1)  # Cloud Tasks counts retries from 0
    client.post("/tasks/ingest", json={"job_id": "j"}, headers={"X-CloudTasks-TaskRetryCount": "0"})
    client.post(
        "/tasks/ingest", json={"job_id": "j"}, headers={"X-CloudTasks-TaskRetryCount": last}
    )
    assert finals == [False, True]


def test_a_cloud_task_is_named_after_its_job_and_carries_an_oidc_token():
    queue = CloudTasksQueue(
        queue="projects/p/locations/us-central1/queues/ingest",
        worker_url="https://anyview-worker-abc.a.run.app/",
        invoker="anyview-tasks@p.iam.gserviceaccount.com",
    )
    task = queue.task("job-1")
    assert task["name"] == "projects/p/locations/us-central1/queues/ingest/tasks/job-1"
    request = task["httpRequest"]
    assert request["url"] == "https://anyview-worker-abc.a.run.app/tasks/ingest"
    assert json.loads(base64.b64decode(request["body"])) == {"job_id": "job-1"}
    assert request["oidcToken"] == {
        "serviceAccountEmail": "anyview-tasks@p.iam.gserviceaccount.com",
        "audience": "https://anyview-worker-abc.a.run.app",
    }
