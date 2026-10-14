"""A dump on its way to a proposal (ADR 0019), and the job that carries it (ADR 0034).

Two callers share this:

  - the synchronous `/brain/dumps` routes, which run it inside the request;
  - the worker Cloud Tasks calls (`anyview.worker`), which runs one queued job
    per delivery through `run_job`.

Failures are `IngestFailed`: a sentence for the browser and the HTTP status
the synchronous route answers with. A `ModelError` passes through untouched,
because whether to retry it is the caller's call.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Literal

from anyview.api.uploads import object_prefix
from anyview.brain.extract import ExtractionFailed, Progress, drop_unchanged, propose
from anyview.brain.models import Proposal, RawDump
from anyview.db.repository import JobWork, NotFound, Repository
from anyview.llm.adapter import ModelError
from anyview.uploads.extract import ExtractionError, docx_to_text, pdf_to_text

log = logging.getLogger(__name__)

UPLOAD_SUFFIXES = (".pdf", ".docx")

# How long a claimed job may go without a heartbeat (a progress frame) before
# another delivery may take it over. Longer than any single model call in the
# pipeline; shorter than the queue's total retry window (infra/tasks.tf), so a
# delivery that died is picked up by a later retry.
LEASE = dt.timedelta(seconds=120)


class IngestFailed(Exception):
    """A failure that retrying will not fix: the input is the problem."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def check_upload(object_name: str, uid: str) -> None:
    """The checks that need no file: whose it is, and what type. Run before a
    job is queued, so these answer at once."""
    if not object_name.startswith(object_prefix(uid)):
        raise IngestFailed("That upload isn't yours.", 403)
    if not object_name.endswith(UPLOAD_SUFFIXES):
        raise IngestFailed("Upload a PDF or Word (.docx) file.", 415)


def read_upload(object_name: str, uid: str, *, model, store, tell: Progress) -> tuple[str, str]:
    """The uploaded file as (dump kind, text)."""
    check_upload(object_name, uid)
    data = store.read(object_name)
    if data is None:
        raise IngestFailed("The uploaded file wasn't found. Please upload it again.", 404)
    tell("reading", {"file": object_name.rsplit(".", 1)[-1]})
    try:
        if object_name.endswith(".pdf"):
            kind = "resume_pdf"
            text = pdf_to_text(data, model=model, session_id=f"upload-{uuid.uuid4().hex[:8]}")
        else:
            kind, text = "resume_docx", docx_to_text(data)
    except ExtractionError as exc:
        raise IngestFailed(exc.user_message, 422) from exc
    if len(text.strip()) < 20:
        raise IngestFailed("The file has almost no text in it.", 422)
    tell("read", {"characters": len(text)})
    return kind, text


def propose_for(
    repo: Repository, model, uid: str, dump: RawDump, *, on_progress: Progress | None = None
) -> Proposal:
    """Read one dump into a pending proposal (ADR 0019, 0015)."""
    index, _ = repo.brain_index(uid)
    brain = repo.brain(uid)
    try:
        patch = propose(
            dump.text,
            brain_index=index,
            model=model,
            session_id=f"dump-{dump.id[:8]}",
            garden_skills={k.label: k.name for k in brain.skills},
            on_progress=on_progress,
        )
    except ExtractionFailed as exc:
        raise IngestFailed(exc.user_message, 502) from exc
    if patch.is_empty():
        raise IngestFailed(
            "Donna found nothing about your experience in that. "
            "Try describing a role, a project, or a story.",
            422,
        )
    # Drafts that only restate something already confirmed never reach the
    # queue: a queue of cards the user has already agreed to is a queue that
    # gets approved unread (ADR 0015).
    patch = drop_unchanged(patch, brain)
    if patch.is_empty():
        raise IngestFailed("Nothing new in there — your Digital Garden already has all of it.", 422)
    return repo.create_proposal(
        uid, dump_id=dump.id, patch=patch, model=getattr(model, "model", "fake")
    )


# What one delivery of a job came to. The worker turns it into an HTTP status
# for Cloud Tasks: "retry" is a 5xx (try again later), "busy" a 409 (another
# delivery holds it), everything else a 2xx (stop delivering).
Outcome = Literal["done", "failed", "retry", "busy", "gone"]


def run_job(job_id: str, *, repo: Repository, model, store, final: bool) -> Outcome:
    """Run one delivery of a queued job. `final` is True on the queue's last
    attempt: a retryable failure then fails the job instead of asking again."""
    claimed = repo.claim_job(job_id, lease=LEASE)
    if claimed == "busy":
        return "busy"
    if claimed in ("missing", "finished"):
        # Finished by an earlier delivery, or erased with its user (ADR 0018).
        return "gone"
    assert isinstance(claimed, JobWork)
    job = claimed

    def tell(stage: str, data: dict) -> None:
        repo.report_job_progress(job.id, {"stage": stage, **data})

    try:
        dump = _dump_for(job, repo=repo, model=model, store=store, tell=tell)
        proposal = propose_for(repo, model, job.uid, dump, on_progress=tell)
    except IngestFailed as exc:
        repo.fail_job(job.id, exc.message, exc.status)
        return "failed"
    except ModelError as exc:
        if exc.retryable and not final:
            log.warning("ingest job %s: retryable model error, asking for a retry", job.id)
            repo.requeue_job(job.id)
            return "retry"
        repo.fail_job(job.id, exc.user_message, 503 if exc.retryable else 502)
        return "failed"
    except Exception:
        log.exception("ingest job %s failed", job.id)
        if not final:
            repo.requeue_job(job.id)
            return "retry"
        repo.fail_job(
            job.id, "Something went wrong while Donna was reading. Please try again.", 500
        )
        return "failed"
    repo.finish_job(job.id, proposal.id)
    return "done"


def _dump_for(job: JobWork, *, repo: Repository, model, store, tell: Progress) -> RawDump:
    """The job's dump: the one an earlier attempt already read, or a new one.
    Reading a PDF is a model call, so a retry must not pay for it twice."""
    if job.raw_dump_id:
        try:
            return repo.dump(job.uid, job.raw_dump_id)
        except NotFound:
            pass  # cannot happen short of an erase mid-job; read it again
    if job.source == "upload":
        kind, text = read_upload(
            job.object_name or "", job.uid, model=model, store=store, tell=tell
        )
    else:
        kind, text = "text", job.input_text or ""
    dump = repo.create_dump(job.uid, kind=kind, text=text, object_name=job.object_name)
    repo.set_job_dump(job.id, dump.id)
    return dump
