# ruff: noqa: E501 — SQL statements read better on one line than folded to fit 100 columns.
"""All database access, with app-meaningful methods (brief). The only module
that contains SQL.

Write path (ADR 0011): every change to the brain is one row in `events`,
written and applied to the projection tables in the same transaction by
`_apply`. `rebuild()` replays a user's events from scratch with the same
function, so the projection is always reproducible from the log.

Every method takes the caller's uid and scopes every statement by it; a row
belonging to someone else is indistinguishable from a missing row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from anyview.activity import record
from anyview.brain.models import (
    EDITABLE,
    LABEL_PREFIX,
    Achievement,
    Brain,
    Competency,
    Coverage,
    Education,
    EntityKind,
    Event,
    Feedback,
    IngestJob,
    Language,
    Patch,
    Project,
    Proposal,
    Provenance,
    RawDump,
    Role,
    Skill,
    Story,
)
from anyview.interview.models import JobFields, SavedJob

TABLE: dict[EntityKind, str] = {
    "role": "roles",
    "project": "projects",
    "story": "stories",
    "skill": "skills",
    "achievement": "achievements",
    "education": "education",
    "language": "languages",
    "feedback": "feedback",
}


# Garden search (ADR 0038): which kinds get an embedding, and the version of
# how each renders to text. Bump the version when `_embedding_texts` changes:
# every entity is then re-embedded on its next write (or by the backfill).
EMBEDDED_KINDS = ("project", "story", "achievement", "feedback")
EMBED_RENDER_VERSION = 1


@dataclass(frozen=True)
class Embedder:
    """How a write gets its vectors (ADR 0038): the model's `embed`, bound to
    a session id by the caller, and the model's name for the row."""

    model: str
    embed: Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class Found:
    """One entity a garden search returned, nearest first."""

    label: str
    kind: str
    text: str  # the block `brain_context` shows for it
    distance: float  # cosine distance: 0 is the same direction, 2 the opposite


# Every table holding a user's rows, children before parents (ADR 0018).
# skill_evidence goes with skills and projects (ON DELETE CASCADE). A new
# table with a user_id belongs here too; a test fails if one is missed.
ERASE_ORDER = (
    "feedback",
    "stories",
    "skills",
    "achievements",
    "education",
    "languages",
    "projects",
    "roles",
    "events",
    "ingest_jobs",  # points at proposals and raw_dumps, so it goes first
    "proposals",
    "raw_dumps",
    "usage_events",
    "saved_jobs",
    "entity_embeddings",
    "daily_usage",
    "users",
)


# A queued or running job untouched for this long is reported as failed: its
# worker died and Cloud Tasks has given up (ADR 0034). Longer than every retry
# backoff added together, so a job waiting on its next attempt is never caught.
JOB_STALE = dt.timedelta(minutes=15)

# What a cancelled job records. 499 is nginx's "client closed request": nothing
# failed, the user changed their mind, and the browser shows it as such.
CANCELLED_MESSAGE = "Cancelled."
CANCELLED_STATUS = 499


@dataclass(frozen=True)
class JobWork:
    """What a worker needs to run a claimed job. Not scoped by a signed-in
    user: the worker is called by Cloud Tasks, and the uid comes from the row."""

    id: str
    uid: str
    source: str
    input_text: str | None
    object_name: str | None
    raw_dump_id: str | None


class NotFound(Exception):
    pass


class Conflict(Exception):
    """The request does not fit the current state (already resolved, bad reference…)."""


def _q(sql: str) -> sa.TextClause:
    return sa.text(sql)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _is_uuid(value: str) -> bool:
    """True for a well-formed id. Checked before a query so a mangled id from the
    browser is "not found" rather than a Postgres cast error."""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def text_sha256(text: str) -> str:
    """Hex digest of a dump's text (ADR 0015). The *extracted text*, never the
    file bytes: the same CV exported twice from Word differs byte for byte and
    extracts identically, and that is the case worth catching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Edit fields that point at other entities, and the kind they point at.
LINK_TARGET: dict[str, EntityKind] = {
    "role_id": "role",
    "project_id": "project",
    "role_ids": "role",
    "project_ids": "project",
    "achievement_ids": "achievement",
}


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # --- users ---------------------------------------------------------------

    def user_ids(self) -> list[str]:
        """Every user's uid. For one-off maintenance (`scripts/embed_garden.py`)."""
        with self.engine.begin() as c:
            return [r[0] for r in c.execute(_q("SELECT uid FROM users ORDER BY created_at"))]

    def ensure_user(self, uid: str, email: str) -> bool:
        """Create the user's row on their first request. True when it was new,
        which is what counts as a sign-up (ADR 0042)."""
        with self.engine.begin() as c:
            # RETURNING gives a row only when the INSERT happened; on a conflict
            # nothing is returned and the email is refreshed instead.
            created = c.execute(
                _q(
                    "INSERT INTO users (uid, email) VALUES (:uid, :email) "
                    "ON CONFLICT (uid) DO NOTHING RETURNING uid"
                ),
                {"uid": uid, "email": email},
            ).first()
            if created is None:
                c.execute(
                    _q("UPDATE users SET email = :email WHERE uid = :uid AND email <> :email"),
                    {"uid": uid, "email": email},
                )
        if created is not None:
            record("signup")
        return created is not None

    def erase_user(self, uid: str) -> dict[str, int]:
        """Delete everything stored about one user, in one transaction (ADR 0018).

        The only code that deletes events. The trigger lets these deletes
        through because this transaction first names the user it is erasing
        (migration 005); any other delete, and every update, is still refused.

        Order follows the foreign keys: the projection points at events and
        dumps, events at proposals and dumps, everything at the user. Returns
        rows removed per table, for the log line. Erasing a user who is not
        there removes nothing and is not an error, so a retry is safe.
        """
        removed: dict[str, int] = {}
        with self.engine.begin() as c:
            c.execute(_q("SELECT set_config('anyview.erasing_user', :uid, true)"), {"uid": uid})
            # The resume pointer references a dump; clear it before the dumps go.
            c.execute(_q("UPDATE users SET resume_dump_id = NULL WHERE uid = :uid"), {"uid": uid})
            for table in ERASE_ORDER:
                column = "uid" if table == "users" else "user_id"
                removed[table] = c.execute(
                    _q(f"DELETE FROM {table} WHERE {column} = :uid"), {"uid": uid}
                ).rowcount
        return removed

    # --- raw dumps -----------------------------------------------------------

    def create_dump(self, uid: str, *, kind: str, text: str, object_name: str | None) -> RawDump:
        dump_id = str(uuid.uuid4())
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "INSERT INTO raw_dumps (id, user_id, kind, text, object_name, text_sha256) "
                    "VALUES (:id, :uid, :kind, :text, :obj, :sha) RETURNING created_at"
                ),
                {
                    "id": dump_id,
                    "uid": uid,
                    "kind": kind,
                    "text": text,
                    "obj": object_name,
                    "sha": text_sha256(text),
                },
            ).one()
        return RawDump(id=dump_id, kind=kind, text=text, object_name=object_name, created_at=row[0])

    def dump_with_text(self, uid: str, text: str) -> RawDump | None:
        """This user's existing dump holding exactly this text, if there is one.

        Matched on the hash column so the comparison is an index lookup rather
        than a table scan of everything they have ever written (ADR 0015)."""
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "SELECT id, kind, text, object_name, created_at FROM raw_dumps "
                    "WHERE user_id = :uid AND text_sha256 = :sha AND text = :text "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"uid": uid, "sha": text_sha256(text), "text": text},
            ).one_or_none()
        if row is None:
            return None
        return RawDump(
            id=str(row[0]), kind=row[1], text=row[2], object_name=row[3], created_at=row[4]
        )

    # --- the resume on file (ADR 0014) ---------------------------------------

    def active_resume(self, uid: str) -> RawDump | None:
        """The resume an interviewer would have received, or None if they have
        not given us one yet."""
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "SELECT d.id, d.kind, d.text, d.object_name, d.created_at "
                    "FROM users u JOIN raw_dumps d ON d.id = u.resume_dump_id "
                    "WHERE u.uid = :uid AND d.user_id = :uid"
                ),
                {"uid": uid},
            ).one_or_none()
        if row is None:
            return None
        return RawDump(
            id=str(row[0]), kind=row[1], text=row[2], object_name=row[3], created_at=row[4]
        )

    def set_active_resume(self, uid: str, dump_id: str) -> None:
        """Point the user at the dump that now holds their resume. Scoped to
        their own dumps: the join is the whole authorisation check."""
        with self.engine.begin() as c:
            updated = c.execute(
                _q(
                    "UPDATE users SET resume_dump_id = d.id FROM raw_dumps d "
                    "WHERE users.uid = :uid AND d.id = :dump AND d.user_id = :uid"
                ),
                {"uid": uid, "dump": dump_id},
            ).rowcount
        if not updated:
            raise NotFound("dump")

    # --- saved jobs (ADR 0025) ------------------------------------------------

    _JOB_COLUMNS = (
        "id, company, role, seniority, source, job_description, fields, created_at, last_used_at"
    )

    @staticmethod
    def _saved_job(row: Any) -> SavedJob:
        return SavedJob(
            id=str(row[0]),
            company=row[1],
            role=row[2],
            seniority=row[3],
            source=row[4],
            job_description=row[5],
            fields=JobFields.model_validate(row[6] or {}),
            created_at=row[7],
            last_used_at=row[8],
        )

    def saved_jobs(self, uid: str) -> list[SavedJob]:
        """This user's saved jobs, the one practised most recently first."""
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    f"SELECT {self._JOB_COLUMNS} FROM saved_jobs "
                    "WHERE user_id = :uid ORDER BY last_used_at DESC"
                ),
                {"uid": uid},
            ).all()
        return [self._saved_job(r) for r in rows]

    def saved_job_with_text(self, uid: str, text: str) -> SavedJob | None:
        """The saved job holding exactly this job description, if there is one."""
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    f"SELECT {self._JOB_COLUMNS} FROM saved_jobs "
                    "WHERE user_id = :uid AND text_sha256 = :sha AND job_description = :text "
                    "ORDER BY last_used_at DESC LIMIT 1"
                ),
                {"uid": uid, "sha": text_sha256(text), "text": text},
            ).one_or_none()
        return None if row is None else self._saved_job(row)

    def save_job(
        self,
        uid: str,
        *,
        job_id: str | None,
        company: str,
        role: str,
        seniority: str,
        source: str,
        job_description: str | None,
        fields: JobFields,
    ) -> SavedJob:
        """Remember the job an interview was started for, and mark it used now.

        Which row it lands in, in order: the saved job the user picked
        (`job_id`, scoped to their own rows); else one already holding this
        exact job description; else one with the same company, role and
        seniority and no description; else a new row. So practising the same
        posting twice never makes two entries, and corrections write back."""
        values = {
            "uid": uid,
            "company": company,
            "role": role,
            "seniority": seniority,
            "source": source,
            "jd": job_description,
            "fields": fields.model_dump_json(),
            "sha": text_sha256(job_description) if job_description else None,
        }
        with self.engine.begin() as c:
            target = None
            if job_id and _is_uuid(job_id):
                target = c.execute(
                    _q("SELECT id FROM saved_jobs WHERE id = CAST(:id AS uuid) AND user_id = :uid"),
                    {"id": job_id, "uid": uid},
                ).scalar_one_or_none()
            if target is None and job_description:
                target = c.execute(
                    _q(
                        "SELECT id FROM saved_jobs WHERE user_id = :uid "
                        "AND text_sha256 = :sha AND job_description = :jd LIMIT 1"
                    ),
                    values,
                ).scalar_one_or_none()
            if target is None and not job_description:
                target = c.execute(
                    _q(
                        "SELECT id FROM saved_jobs WHERE user_id = :uid "
                        "AND job_description IS NULL AND lower(company) = lower(:company) "
                        "AND lower(role) = lower(:role) AND seniority = :seniority LIMIT 1"
                    ),
                    values,
                ).scalar_one_or_none()

            if target is None:
                row = c.execute(
                    _q(
                        "INSERT INTO saved_jobs (id, user_id, company, role, seniority, source, "
                        "job_description, fields, text_sha256) VALUES (:id, :uid, :company, "
                        ":role, :seniority, :source, :jd, CAST(:fields AS jsonb), :sha) "
                        f"RETURNING {self._JOB_COLUMNS}"
                    ),
                    {**values, "id": str(uuid.uuid4())},
                ).one()
            else:
                row = c.execute(
                    _q(
                        "UPDATE saved_jobs SET company = :company, role = :role, "
                        "seniority = :seniority, source = :source, job_description = :jd, "
                        "fields = CAST(:fields AS jsonb), text_sha256 = :sha, last_used_at = now() "
                        f"WHERE id = :id RETURNING {self._JOB_COLUMNS}"
                    ),
                    {**values, "id": target},
                ).one()
        return self._saved_job(row)

    def delete_saved_job(self, uid: str, job_id: str) -> None:
        if not _is_uuid(job_id):
            raise NotFound("saved job")
        with self.engine.begin() as c:
            deleted = c.execute(
                _q("DELETE FROM saved_jobs WHERE id = CAST(:id AS uuid) AND user_id = :uid"),
                {"id": job_id, "uid": uid},
            ).rowcount
        if not deleted:
            raise NotFound("saved job")

    def dump(self, uid: str, dump_id: str) -> RawDump:
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "SELECT id, kind, text, object_name, created_at FROM raw_dumps "
                    "WHERE user_id = :uid AND id = :id"
                ),
                {"uid": uid, "id": dump_id},
            ).one_or_none()
        if row is None:
            raise NotFound("dump")
        return RawDump(
            id=str(row[0]), kind=row[1], text=row[2], object_name=row[3], created_at=row[4]
        )

    # --- ingestion jobs (ADR 0034) ---------------------------------------------
    # A plain table like saved_jobs, not event-sourced. The browser reads a job
    # by its uid-scoped methods; the worker writes it by id alone.

    _INGEST_COLUMNS = (
        "j.id, j.source, j.status, j.progress, j.attempts, j.error, j.error_status, "
        "j.proposal_id, j.created_at, j.updated_at, now() - j.updated_at > :stale AS stale"
    )

    def create_job(
        self, uid: str, *, text: str | None = None, object_name: str | None = None
    ) -> IngestJob:
        """A queued job for typed text or for an uploaded file (exactly one)."""
        source = "upload" if object_name is not None else "text"
        job_id = str(uuid.uuid4())
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "INSERT INTO ingest_jobs (id, user_id, source, input_text, object_name) "
                    "VALUES (:id, :uid, :source, :text, :obj)"
                ),
                {"id": job_id, "uid": uid, "source": source, "text": text, "obj": object_name},
            )
        return self.job(uid, job_id)

    def job(self, uid: str, job_id: str) -> IngestJob:
        if not _is_uuid(job_id):
            raise NotFound("job")
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    f"SELECT {self._INGEST_COLUMNS} FROM ingest_jobs j "
                    "WHERE j.user_id = :uid AND j.id = :id"
                ),
                {"uid": uid, "id": job_id, "stale": JOB_STALE},
            ).one_or_none()
        if row is None:
            raise NotFound("job")
        return self._job(uid, row)

    def active_jobs(self, uid: str) -> list[IngestJob]:
        """Jobs still on their way, newest first: what a reloaded page picks up."""
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    f"SELECT {self._INGEST_COLUMNS} FROM ingest_jobs j "
                    "WHERE j.user_id = :uid AND j.status IN ('queued', 'running') "
                    "AND now() - j.updated_at <= :stale ORDER BY j.created_at DESC"
                ),
                {"uid": uid, "stale": JOB_STALE},
            ).all()
        return [self._job(uid, r) for r in rows]

    def _job(self, uid: str, r: Any) -> IngestJob:
        status, error, error_status = r[2], r[5], r[6]
        if r[10] and status in ("queued", "running"):
            # Nothing is coming for this job any more; say so rather than let
            # the browser wait for ever. The row itself is left as it was.
            status, error, error_status = (
                "failed",
                "Donna stopped before she finished. Please try again.",
                503,
            )
        return IngestJob(
            id=str(r[0]), source=r[1], status=status, progress=r[3], attempts=r[4],
            error=error, error_status=error_status,
            proposal=self.proposal(uid, str(r[7])) if r[7] is not None else None,
            created_at=r[8], updated_at=r[9],
        )  # fmt: skip

    def claim_job(
        self, job_id: str, *, lease: dt.timedelta
    ) -> JobWork | Literal["missing", "finished", "busy"]:
        """Take a job for one delivery. A job is free when it is queued, or when
        it is running but its heartbeat is older than `lease` (that delivery
        died). Cloud Tasks delivers at least once, so two deliveries of the same
        task can arrive together; only one of them gets the row."""
        if not _is_uuid(job_id):
            return "missing"
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "UPDATE ingest_jobs SET status = 'running', attempts = attempts + 1, "
                    "progress = '[]'::jsonb, error = NULL, error_status = NULL, updated_at = now() "
                    "WHERE id = :id AND (status = 'queued' "
                    "OR (status = 'running' AND now() - updated_at > :lease)) "
                    "RETURNING user_id, source, input_text, object_name, raw_dump_id"
                ),
                {"id": job_id, "lease": lease},
            ).one_or_none()
            if row is not None:
                return JobWork(
                    id=job_id, uid=row[0], source=row[1], input_text=row[2],
                    object_name=row[3], raw_dump_id=str(row[4]) if row[4] else None,
                )  # fmt: skip
            status = c.execute(
                _q("SELECT status FROM ingest_jobs WHERE id = :id"), {"id": job_id}
            ).scalar_one_or_none()
        if status is None:
            return "missing"
        return "busy" if status == "running" else "finished"

    def report_job_progress(self, job_id: str, frame: dict) -> bool:
        """Append one progress frame. Doubles as the heartbeat. False means the
        job is no longer running (the user cancelled it), so the worker stops."""
        with self.engine.begin() as c:
            result = c.execute(
                _q(
                    "UPDATE ingest_jobs SET progress = progress || CAST(:frame AS jsonb), "
                    "updated_at = now() WHERE id = :id AND status = 'running'"
                ),
                {"id": job_id, "frame": _json([frame])},
            )
        return result.rowcount > 0

    def set_job_dump(self, job_id: str, dump_id: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                _q("UPDATE ingest_jobs SET raw_dump_id = :dump, updated_at = now() WHERE id = :id"),
                {"id": job_id, "dump": dump_id},
            )

    def finish_job(self, job_id: str, proposal_id: str) -> bool:
        """Mark a running job done. False when it was cancelled meanwhile: the
        caller then discards the proposal, so a cancelled upload leaves nothing."""
        with self.engine.begin() as c:
            result = c.execute(
                _q(
                    "UPDATE ingest_jobs SET status = 'done', proposal_id = :pid, "
                    "updated_at = now() WHERE id = :id AND status = 'running'"
                ),
                {"id": job_id, "pid": proposal_id},
            )
        return result.rowcount > 0

    def fail_job(self, job_id: str, message: str, status: int) -> None:
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "UPDATE ingest_jobs SET status = 'failed', error = :msg, "
                    "error_status = :status, updated_at = now() "
                    "WHERE id = :id AND status IN ('queued', 'running')"
                ),
                {"id": job_id, "msg": message, "status": status},
            )

    def cancel_job(self, uid: str, job_id: str) -> IngestJob:
        """The user's way out of a job that is queued or running. The job fails
        with status 499 ("Cancelled."), which a redelivered task then finds
        finished and skips, and the worker stops at its next progress frame.
        A job that already ended is returned as it is."""
        job = self.job(uid, job_id)  # NotFound unless it is this user's
        if job.status in ("queued", "running"):
            self.fail_job(job_id, CANCELLED_MESSAGE, CANCELLED_STATUS)
            job = self.job(uid, job_id)
        return job

    def requeue_job(self, job_id: str) -> None:
        """This delivery failed in a way worth retrying; Cloud Tasks will call
        again after its backoff, and the next claim takes the row at once."""
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "UPDATE ingest_jobs SET status = 'queued', updated_at = now() "
                    "WHERE id = :id AND status = 'running'"  # never revive a cancelled job
                ),
                {"id": job_id},
            )

    # --- proposals (the review queue) ----------------------------------------

    def create_proposal(self, uid: str, *, dump_id: str, patch: Patch, model: str) -> Proposal:
        pid = str(uuid.uuid4())
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "INSERT INTO proposals (id, user_id, raw_dump_id, patch, model) "
                    "SELECT :id, :uid, :dump, CAST(:patch AS jsonb), :model FROM raw_dumps d "
                    "WHERE d.id = :dump AND d.user_id = :uid "
                    "RETURNING created_at, (SELECT kind FROM raw_dumps WHERE id = :dump)"
                ),
                {
                    "id": pid,
                    "uid": uid,
                    "dump": dump_id,
                    "patch": patch.model_dump_json(),
                    "model": model,
                },
            ).one_or_none()
        if row is None:
            raise NotFound("dump")
        return Proposal(
            id=pid, raw_dump_id=dump_id, status="pending", patch=patch, model=model,
            created_at=row[0], resolved_at=None, dump_kind=row[1],
        )  # fmt: skip

    def pending_proposals(self, uid: str) -> list[Proposal]:
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    "SELECT p.id, p.raw_dump_id, p.status, p.patch, p.model, p.created_at, "
                    "p.resolved_at, d.kind "
                    "FROM proposals p JOIN raw_dumps d ON d.id = p.raw_dump_id "
                    "WHERE p.user_id = :uid AND p.status = 'pending' ORDER BY p.created_at"
                ),
                {"uid": uid},
            ).all()
        return [self._proposal(r) for r in rows]

    def proposal(self, uid: str, proposal_id: str) -> Proposal:
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "SELECT p.id, p.raw_dump_id, p.status, p.patch, p.model, p.created_at, "
                    "p.resolved_at, d.kind "
                    "FROM proposals p JOIN raw_dumps d ON d.id = p.raw_dump_id "
                    "WHERE p.user_id = :uid AND p.id = :id"
                ),
                {"uid": uid, "id": proposal_id},
            ).one_or_none()
        if row is None:
            raise NotFound("proposal")
        return self._proposal(row)

    @staticmethod
    def _proposal(r) -> Proposal:
        return Proposal(
            id=str(r[0]), raw_dump_id=str(r[1]), status=r[2], patch=Patch.model_validate(r[3]),
            model=r[4], created_at=r[5], resolved_at=r[6], dump_kind=r[7],
        )  # fmt: skip

    def discard_proposal(self, uid: str, proposal_id: str) -> None:
        with self.engine.begin() as c:
            n = c.execute(
                _q(
                    "UPDATE proposals SET status = 'discarded', resolved_at = now() "
                    "WHERE user_id = :uid AND id = :id AND status = 'pending'"
                ),
                {"uid": uid, "id": proposal_id},
            ).rowcount
        if n == 0:
            raise NotFound("pending proposal")

    def confirm_proposal(
        self, uid: str, proposal_id: str, patch: Patch, *, embed: Embedder | None = None
    ) -> Event:
        """The user reviewed (and possibly edited) the patch. Resolve its keys and
        labels to real ids, append one event, apply it, and close the proposal —
        all in one transaction, so the log and the projection cannot disagree.
        With `embed`, the entities it changes are embedded first (ADR 0038)."""
        if patch.is_empty():
            raise Conflict("Nothing left to add. Discard the proposal instead.")

        def work(c: Connection) -> Event:
            row = c.execute(
                _q(
                    "SELECT raw_dump_id, status FROM proposals "
                    "WHERE user_id = :uid AND id = :id FOR UPDATE"
                ),
                {"uid": uid, "id": proposal_id},
            ).one_or_none()
            if row is None:
                raise NotFound("proposal")
            if row[1] != "pending":
                raise Conflict("That proposal was already resolved.")
            dump_id = str(row[0])

            event = self._confirm(c, uid, patch, dump_id, proposal_id)
            c.execute(
                _q("UPDATE proposals SET status = 'confirmed', resolved_at = now() WHERE id = :id"),
                {"id": proposal_id},
            )
            return event

        return self._write(uid, work, embed)

    def add_entry(
        self, uid: str, patch: Patch, text: str, *, embed: Embedder | None = None
    ) -> Event:
        """An entry the user typed into a form (ADR 0022). The form's text is
        stored as a raw dump, which is the entry's provenance, and the patch
        is confirmed against it in the same transaction. No proposal: there
        was nothing for the user to review that they had not just written."""
        if patch.is_empty():
            raise Conflict("Nothing to add.")
        # Fixed outside `work`, so the dry run and the write make the same ids.
        dump_id = str(uuid.uuid4())

        def work(c: Connection) -> Event:
            c.execute(
                _q(
                    "INSERT INTO raw_dumps (id, user_id, kind, text, object_name, text_sha256) "
                    "VALUES (:id, :uid, 'text', :text, NULL, :sha)"
                ),
                {"id": dump_id, "uid": uid, "text": text, "sha": text_sha256(text)},
            )
            return self._confirm(c, uid, patch, dump_id, None)

        return self._write(uid, work, embed)

    def _confirm(
        self, c: Connection, uid: str, patch: Patch, dump_id: str, proposal_id: str | None
    ) -> Event:
        """Resolve a reviewed patch to ids, append its event, apply it."""
        labels = self._labels(c, uid)
        payload = _resolve(patch, labels, dump_id)
        event = self._append(
            c,
            uid,
            kind="patch_confirmed",
            payload=payload,
            dump_id=dump_id,
            proposal_id=proposal_id,
        )
        try:
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
        except sa.exc.IntegrityError as exc:
            # One live skill or language per name. A name edited in the
            # queue (or typed into a form) can still collide; the transaction
            # rolls back whole.
            if "_live_name_idx" in str(exc.orig):
                raise Conflict(
                    "Your garden already has an entry with one of these names. "
                    "Rename it, or untick it, and confirm again."
                ) from exc
            raise
        return event

    # --- direct edits ----------------------------------------------------------

    def edit_entity(
        self,
        uid: str,
        kind: EntityKind,
        entity_id: str,
        fields: dict[str, Any],
        *,
        embed: Embedder | None = None,
    ) -> Event:
        unknown = set(fields) - EDITABLE[kind]
        if unknown:
            raise Conflict(f"Cannot edit {', '.join(sorted(unknown))} on a {kind}.")
        if not fields:
            raise Conflict("Nothing to change.")

        def work(c: Connection) -> Event:
            self._require_live(c, uid, kind, entity_id)
            self._require_link_targets(c, uid, fields)
            payload = {"kind": kind, "id": entity_id, "fields": fields}
            event = self._append(c, uid, kind="entity_edited", payload=payload)
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
            return event

        return self._write(uid, work, embed)

    def retire_entity(
        self, uid: str, kind: EntityKind, entity_id: str, *, embed: Embedder | None = None
    ) -> Event:
        def work(c: Connection) -> Event:
            self._require_live(c, uid, kind, entity_id)
            payload = {"kind": kind, "id": entity_id}
            event = self._append(c, uid, kind="entity_retired", payload=payload)
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
            return event

        return self._write(uid, work, embed)

    # --- embeddings (ADR 0038) ------------------------------------------------------

    def _write(self, uid: str, work: Callable[[Connection], Any], embed: Embedder | None) -> Any:
        """Run `work` in one transaction. With `embed`, embed first (ADR 0038):

        1. a dry run applies `work` in a transaction that is rolled back, to see
           which entities' text it changes (`_stale`);
        2. those texts are embedded with no transaction open: a model call does
           not hold a lock. If it fails, nothing has been written;
        3. `work` runs for real, and the vectors are stored in the same
           transaction. If the garden changed in between, so that the texts no
           longer match, the write is refused rather than store a wrong vector.

        Every entity with a stale or missing vector is embedded, not only the
        ones this write touched, so the garden heals itself as it is used."""
        if embed is None:
            with self.engine.begin() as c:
                return work(c)

        with self.engine.connect() as c:
            dry = c.begin()
            try:
                work(c)
                planned = self._stale(c, uid)
            finally:
                dry.rollback()

        # Keyed by the text's hash, not the entity id: a new entity gets a fresh
        # id on each run (`_resolve`), but the same text has the same hash.
        texts = {sha: text for _, text, sha in planned.values()}
        shas = list(texts)
        vectors = dict(zip(shas, embed.embed([texts[h] for h in shas]), strict=True))

        with self.engine.begin() as c:
            result = work(c)
            stale = self._stale(c, uid)
            if any(sha not in vectors for _, _, sha in stale.values()):
                raise Conflict("Your garden changed while this was saving. Please try again.")
            self._store_embeddings(c, uid, stale, vectors, embed)
        return result

    def embed_garden(self, uid: str, embed: Embedder) -> int:
        """Embed every entity that has no current vector. For the backfill
        script and after a render-version bump. Returns how many were embedded."""
        with self.engine.begin() as c:
            count = len(self._stale(c, uid))
        if count:
            self._write(uid, lambda c: None, embed)
        return count

    def _stale(self, c: Connection, uid: str) -> dict[str, tuple[str, str, str]]:
        """Live embeddable entities whose stored vector is missing or was made
        from different text: id → (kind, text, sha256 of the text)."""
        texts = _embedding_texts(self._entities(c, uid))
        stored = {
            str(r[0]): r[1]
            for r in c.execute(
                _q(
                    "SELECT entity_id, text_sha256 FROM entity_embeddings "
                    "WHERE user_id = :uid AND render_version = :v"
                ),
                {"uid": uid, "v": EMBED_RENDER_VERSION},
            )
        }
        stale = {}
        for entity_id, (kind, text) in texts.items():
            sha = text_sha256(text)
            if stored.get(entity_id) != sha:
                stale[entity_id] = (kind, text, sha)
        return stale

    def _store_embeddings(
        self,
        c: Connection,
        uid: str,
        stale: dict[str, tuple[str, str, str]],
        vectors: dict[str, list[float]],
        embed: Embedder,
    ) -> None:
        """Store each stale entity's vector (`vectors` is keyed by text hash)."""
        for entity_id, (kind, _, sha) in stale.items():
            c.execute(
                _q(
                    "INSERT INTO entity_embeddings "
                    "(entity_id, user_id, kind, embedding, text_sha256, render_version, model) "
                    "VALUES (:id, :uid, :kind, CAST(:vec AS vector), :sha, :v, :model) "
                    "ON CONFLICT (entity_id) DO UPDATE SET embedding = EXCLUDED.embedding, "
                    "kind = EXCLUDED.kind, text_sha256 = EXCLUDED.text_sha256, "
                    "render_version = EXCLUDED.render_version, model = EXCLUDED.model, "
                    "embedded_at = now()"
                ),
                {
                    "id": entity_id,
                    "uid": uid,
                    "kind": kind,
                    "vec": _vector(vectors[sha]),
                    "sha": sha,
                    "v": EMBED_RENDER_VERSION,
                    "model": embed.model,
                },
            )
        # Retired entities keep no vector. Search ignores them anyway; this
        # keeps the table to what is live.
        c.execute(
            _q(
                "DELETE FROM entity_embeddings e WHERE e.user_id = :uid AND NOT EXISTS ("
                + _LIVE_EMBEDDED
                + " AND live.id = e.entity_id)"
            ),
            {"uid": uid},
        )

    def search_garden(
        self,
        uid: str,
        query: list[float],
        *,
        kinds: Iterable[str] = EMBEDDED_KINDS,
        limit: int = 8,
    ) -> list[Found]:
        """The live entities nearest `query`, nearest first (ADR 0003, 0038):
        filter first (this user, these kinds, live only), then order by cosine
        distance, in one statement."""
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    "SELECT e.entity_id, e.kind, e.embedding <=> CAST(:q AS vector) AS distance "
                    "FROM entity_embeddings e "
                    "WHERE e.user_id = :uid AND e.kind = ANY(:kinds) AND EXISTS ("
                    + _LIVE_EMBEDDED
                    + " AND live.id = e.entity_id) "
                    "ORDER BY distance LIMIT :limit"
                ),
                {"uid": uid, "q": _vector(query), "kinds": list(kinds), "limit": limit},
            ).all()
            entities = self._entities(c, uid)
        blocks = _entity_blocks(entities)
        label_of = {e.id: e.label for group in entities for e in group}
        found = []
        for entity_id, kind, distance in rows:
            label = label_of.get(str(entity_id))
            if label is not None:
                found.append(Found(label, kind, blocks[label], float(distance)))
        return found

    def _require_link_targets(self, c: Connection, uid: str, fields: dict[str, Any]) -> None:
        """Every id a link field names must be this user's, live, and of the
        right kind. A foreign key alone would accept another user's role."""
        for field, value in fields.items():
            target = LINK_TARGET.get(field)
            if target is None or value is None:
                continue
            ids = value if isinstance(value, list) else [value]
            for target_id in ids:
                try:
                    uuid.UUID(str(target_id))
                    self._require_live(c, uid, target, str(target_id))
                except (ValueError, NotFound) as exc:
                    raise Conflict(f"That {target} is not in your garden.") from exc

    def _require_live(self, c: Connection, uid: str, kind: EntityKind, entity_id: str) -> None:
        found = c.execute(
            _q(
                f"SELECT 1 FROM {TABLE[kind]} WHERE user_id = :uid AND id = :id AND retired_at IS NULL"
            ),
            {"uid": uid, "id": entity_id},
        ).one_or_none()
        if found is None:
            raise NotFound(kind)

    # --- the event log -----------------------------------------------------------

    def _append(
        self,
        c: Connection,
        uid: str,
        *,
        kind: str,
        payload: dict,
        dump_id: str | None = None,
        proposal_id: str | None = None,
    ) -> Event:
        # Lock the user row so two concurrent appends cannot pick the same seq.
        c.execute(_q("SELECT 1 FROM users WHERE uid = :uid FOR UPDATE"), {"uid": uid})
        row = c.execute(
            _q(
                "INSERT INTO events (user_id, seq, kind, payload, raw_dump_id, proposal_id) "
                "VALUES (:uid, (SELECT coalesce(max(seq), 0) + 1 FROM events WHERE user_id = :uid), "
                ":kind, CAST(:payload AS jsonb), :dump, :prop) RETURNING id, seq, created_at"
            ),
            {
                "uid": uid,
                "kind": kind,
                "payload": _json(payload),
                "dump": dump_id,
                "prop": proposal_id,
            },
        ).one()
        return Event(
            id=row[0], seq=row[1], kind=kind, payload=payload, raw_dump_id=dump_id,
            proposal_id=proposal_id, created_at=row[2],
        )  # fmt: skip

    def events(self, uid: str) -> list[Event]:
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    "SELECT id, seq, kind, payload, raw_dump_id, proposal_id, created_at "
                    "FROM events WHERE user_id = :uid ORDER BY seq"
                ),
                {"uid": uid},
            ).all()
        return [
            Event(
                id=r[0],
                seq=r[1],
                kind=r[2],
                payload=r[3],
                raw_dump_id=str(r[4]) if r[4] else None,
                proposal_id=str(r[5]) if r[5] else None,
                created_at=r[6],
            )  # fmt: skip
            for r in rows
        ]

    def rebuild(self, uid: str) -> int:
        """Drop the user's projection and replay their log. Returns events replayed."""
        with self.engine.begin() as c:
            c.execute(_q("SELECT 1 FROM users WHERE uid = :uid FOR UPDATE"), {"uid": uid})
            # Order matters for the foreign keys; skill_evidence cascades from skills.
            for table in (
                "stories",
                "feedback",
                "skills",
                "achievements",
                "education",
                "languages",
                "projects",
                "roles",
            ):
                c.execute(_q(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": uid})
            rows = c.execute(
                _q(
                    "SELECT id, kind, payload, created_at FROM events WHERE user_id = :uid ORDER BY seq"
                ),
                {"uid": uid},
            ).all()
            for event_id, kind, payload, created_at in rows:
                _apply(c, uid, event_id, kind, payload, created_at)
        return len(rows)

    # --- reads --------------------------------------------------------------------

    def brain(self, uid: str) -> Brain:
        with self.engine.begin() as c:
            roles, projects, stories, skills, achievements, education, languages, feedback = (
                self._entities(c, uid)
            )
            pending = c.execute(
                _q("SELECT count(*) FROM proposals WHERE user_id = :uid AND status = 'pending'"),
                {"uid": uid},
            ).scalar_one()
            competencies = self._competencies(c)
        return Brain(
            roles=roles, projects=projects, stories=stories, skills=skills, achievements=achievements, education=education, languages=languages, feedback=feedback,
            coverage=_coverage(competencies, roles, projects, stories), pending_proposals=pending,
        )  # fmt: skip

    def roles_for_user(self, uid: str) -> list[Role]:
        with self.engine.begin() as c:
            return self._entities(c, uid)[0]

    def stories_for_competency(self, uid: str, competency: str) -> list[Story]:
        with self.engine.begin() as c:
            stories = self._entities(c, uid)[2]
        return [s for s in stories if competency in s.competencies]

    def coverage_map(self, uid: str) -> Coverage:
        return self.brain(uid).coverage

    def brain_index(self, uid: str) -> tuple[str, dict[str, str]]:
        """One line per live entity for prompts, plus the label → id map so a
        model's reference ("R2") resolves to a real id."""
        with self.engine.begin() as c:
            roles, projects, stories, skills, achievements, education, languages, feedback = (
                self._entities(c, uid)
            )
        by_id = {r.id: r for r in roles}
        lines: list[str] = []
        for r in roles:
            lines.append(f"[{r.label}] {r.company} — {r.title} ({_span(r.start_date, r.end_date)})")
        for p in projects:
            where = f" ({by_id[p.role_id].label})" if p.role_id in by_id else ""
            result = f": {p.result}" if p.result else ""
            lines.append(f"[{p.label}] {p.name}{where}{result}")
        for s in stories:
            tags = ", ".join(s.competencies) or "untagged"
            result = f" → {s.result}" if s.result else ""
            lines.append(f"[{s.label}] ({tags}) {s.title}{result}")
        for k in skills:
            lines.append(f"[{k.label}] {k.name} (depth {k.depth}/5)")
        for a in achievements:
            lines.append(f"[{a.label}] {a.kind}: {a.title}" + (f", {a.issuer}" if a.issuer else ""))
        for e in education:
            lines.append(
                f"[{e.label}] education: {e.institution}"
                + (f", {e.qualification}" if e.qualification else "")
            )
        for language in languages:
            lines.append(
                f"[{language.label}] language: {language.name}"
                + (f", {language.proficiency}" if language.proficiency else "")
            )
        for f in feedback:
            lines.append(f"[{f.label}] feedback from {f.given_by}: {_excerpt(f.content)}")
        labels = {
            e.label: e.id
            for group in (
                roles,
                projects,
                stories,
                skills,
                achievements,
                education,
                languages,
                feedback,
            )  # fmt: skip
            for e in group
        }
        return "\n".join(lines), labels

    def brain_context(self, uid: str) -> str:
        """The confirmed brain rendered as the candidate's record for interview
        prompts: fuller than the index, still one entity per block, labels kept
        so answers can cite them."""
        with self.engine.begin() as c:
            entities = self._entities(c, uid)
        roles, projects, stories, skills, achievements, education, languages, feedback = entities
        blocks = _entity_blocks(entities)
        role_by_id = {r.id: r for r in roles}
        out: list[str] = []
        for r in roles:
            out.append(blocks[r.label])
            out.extend(blocks[p.label] for p in projects if p.role_id == r.id)
        loose = [p for p in projects if p.role_id not in role_by_id]
        if loose:
            out.append("## Other projects")
            out.extend(blocks[p.label] for p in loose)
        for heading, group in (
            ("## Stories", stories),
            ("## Feedback", feedback),
            ("## Skills", skills),
            ("## Achievements and certifications", achievements),
            ("## Education", education),
            ("## Languages", languages),
        ):
            if group:
                out.append(heading)
                out.extend(blocks[e.label] for e in group)
        return "\n".join(out)

    def garden_entries(self, uid: str, labels: list[str]) -> dict[str, str]:
        """The full blocks of the entries named by label, as `brain_context`
        renders them. For Harvey's lookup on Live (ADR 0037): unknown labels are
        simply absent, so a model's guess finds nothing rather than an error."""
        with self.engine.begin() as c:
            blocks = _entity_blocks(self._entities(c, uid))
        return {label: blocks[label] for label in labels if label in blocks}

    # --- usage --------------------------------------------------------------------

    # --- Daily limits (ADR 0047) ------------------------------------------------

    def take_daily(self, uid: str, action: str, limit: int) -> bool:
        """Count one `action` against today's limit. False, and nothing counted,
        when the user has already had `limit` today. Days are UTC."""
        with self.engine.begin() as c:
            # One statement: the first of the day inserts 1; later ones add 1
            # only while under the limit. At the limit the WHERE fails, no row
            # comes back, and the count stays where it was.
            row = c.execute(
                _q(
                    "INSERT INTO daily_usage (user_id, day, action, count) "
                    "VALUES (:uid, (now() AT TIME ZONE 'utc')::date, :action, 1) "
                    "ON CONFLICT (user_id, day, action) DO UPDATE "
                    "SET count = daily_usage.count + 1 WHERE daily_usage.count < :limit "
                    "RETURNING count"
                ),
                {"uid": uid, "action": action, "limit": limit},
            ).first()
        return row is not None

    def give_back_daily(self, uid: str, action: str) -> None:
        """Undo one `take_daily`, for work that failed before it cost anything."""
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "UPDATE daily_usage SET count = count - 1 WHERE user_id = :uid "
                    "AND day = (now() AT TIME ZONE 'utc')::date AND action = :action AND count > 0"
                ),
                {"uid": uid, "action": action},
            )

    def write_usage(self, record: dict[str, Any], *, uid: str | None) -> None:
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "INSERT INTO usage_events (user_id, session_id, call, model, input_tokens, "
                    "output_tokens, thinking_tokens, cache_read, latency_ms) VALUES "
                    "(:uid, :session_id, :call, :model, :input_tokens, :output_tokens, "
                    ":thinking_tokens, :cache_read, :latency_ms)"
                ),
                {"uid": uid, **record},
            )

    def usage_for_session(self, session_id: str) -> dict[str, int]:
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "SELECT count(*), coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0), "
                    "coalesce(sum(thinking_tokens), 0) FROM usage_events WHERE session_id = :s"
                ),
                {"s": session_id},
            ).one()
        return {
            "calls": row[0],
            "input_tokens": row[1],
            "output_tokens": row[2],
            "thinking_tokens": row[3],
        }

    # --- internals ------------------------------------------------------------------

    @staticmethod
    def _competencies(c: Connection) -> list[Competency]:
        rows = c.execute(_q("SELECT key, label FROM competencies ORDER BY ord")).all()
        return [Competency(key=r[0], label=r[1]) for r in rows]

    def _labels(self, c: Connection, uid: str) -> dict[str, str]:
        roles, projects, stories, skills, achievements, education, languages, feedback = (
            self._entities(c, uid)
        )
        return {
            e.label: e.id
            for group in (
                roles,
                projects,
                stories,
                skills,
                achievements,
                education,
                languages,
                feedback,
            )  # fmt: skip
            for e in group
        }

    @staticmethod
    def _entities(
        c: Connection, uid: str
    ) -> tuple[
        list[Role],
        list[Project],
        list[Story],
        list[Skill],
        list[Achievement],
        list[Education],
        list[Language],
        list[Feedback],
    ]:
        """Live entities in creation order (event id, then id) — the order labels
        are numbered in, so a label is stable until something before it retires."""

        def rows(sql: str):
            return c.execute(
                _q(sql + " AND retired_at IS NULL ORDER BY event_id, id"), {"uid": uid}
            ).all()

        roles = [
            Role(
                id=str(r[0]),
                label=f"R{i}",
                company=r[1],
                title=r[2],
                start_date=r[3],
                end_date=r[4],
                level=r[5],
                responsibilities=list(r[8]),
                source=Provenance(raw_dump_id=str(r[6]), event_id=r[7]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, company, title, start_date, end_date, level, raw_dump_id, event_id, "
                    "responsibilities FROM roles WHERE user_id = :uid"
                ),
                1,
            )
        ]
        projects = [
            Project(
                id=str(r[0]),
                label=f"P{i}",
                role_id=str(r[1]) if r[1] else None,
                name=r[2],
                problem=r[3],
                action=r[4],
                result=r[5],
                tech=list(r[6]),
                metrics=list(r[7]),
                source=Provenance(raw_dump_id=str(r[8]), event_id=r[9]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, role_id, name, problem, action, result, tech, metrics, raw_dump_id, "
                    "event_id FROM projects WHERE user_id = :uid"
                ),
                1,
            )
        ]
        stories = [
            Story(
                id=str(r[0]),
                label=f"S{i}",
                role_id=str(r[1]) if r[1] else None,
                project_id=str(r[2]) if r[2] else None,
                title=r[3],
                situation=r[4],
                task=r[5],
                action=r[6],
                result=r[7],
                competencies=list(r[8]),
                source=Provenance(raw_dump_id=str(r[9]), event_id=r[10]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, role_id, project_id, title, situation, task, action, result, "
                    "competencies, raw_dump_id, event_id FROM stories WHERE user_id = :uid"
                ),
                1,
            )
        ]
        evidence: dict[str, list[str]] = {}
        for skill_id, project_id in c.execute(
            _q(
                "SELECT e.skill_id, e.project_id FROM skill_evidence e "
                "JOIN skills s ON s.id = e.skill_id WHERE s.user_id = :uid"
            ),
            {"uid": uid},
        ).all():
            evidence.setdefault(str(skill_id), []).append(str(project_id))
        used_in: dict[str, list[str]] = {}
        for skill_id, role_id in c.execute(
            _q(
                "SELECT l.skill_id, l.role_id FROM skill_roles l "
                "JOIN skills s ON s.id = l.skill_id WHERE s.user_id = :uid"
            ),
            {"uid": uid},
        ).all():
            used_in.setdefault(str(skill_id), []).append(str(role_id))
        shown_by: dict[str, list[str]] = {}
        for skill_id, achievement_id in c.execute(
            _q(
                "SELECT l.skill_id, l.achievement_id FROM skill_achievements l "
                "JOIN skills s ON s.id = l.skill_id WHERE s.user_id = :uid"
            ),
            {"uid": uid},
        ).all():
            shown_by.setdefault(str(skill_id), []).append(str(achievement_id))
        skills = [
            Skill(
                id=str(r[0]),
                label=f"K{i}",
                name=r[1],
                depth=r[2],
                project_ids=evidence.get(str(r[0]), []),
                role_ids=used_in.get(str(r[0]), []),
                achievement_ids=shown_by.get(str(r[0]), []),
                source=Provenance(raw_dump_id=str(r[3]), event_id=r[4]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, name, depth, raw_dump_id, event_id FROM skills WHERE user_id = :uid"
                ),
                1,
            )
        ]
        achievements = [
            Achievement(
                id=str(r[0]),
                label=f"A{i}",
                kind=r[1],
                title=r[2],
                issuer=r[3],
                achieved_on=r[4],
                source=Provenance(raw_dump_id=str(r[5]), event_id=r[6]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, kind, title, issuer, achieved_on, raw_dump_id, event_id "
                    "FROM achievements WHERE user_id = :uid"
                ),
                1,
            )
        ]
        education = [
            Education(
                id=str(r[0]),
                label=f"E{i}",
                institution=r[1],
                qualification=r[2],
                field=r[3],
                start_date=r[4],
                end_date=r[5],
                source=Provenance(raw_dump_id=str(r[6]), event_id=r[7]),
            )
            for i, r in enumerate(
                rows(
                    "SELECT id, institution, qualification, field, start_date, end_date, raw_dump_id, event_id FROM education WHERE user_id = :uid"
                ),
                1,
            )
        ]
        languages = [
            Language(
                id=str(r[0]),
                label=f"L{i}",
                name=r[1],
                proficiency=r[2],
                source=Provenance(raw_dump_id=str(r[3]), event_id=r[4]),
            )
            for i, r in enumerate(
                rows(
                    "SELECT id, name, proficiency, raw_dump_id, event_id FROM languages WHERE user_id = :uid"
                ),
                1,
            )
        ]
        feedback = [
            Feedback(
                id=str(r[0]),
                label=f"F{i}",
                role_id=str(r[1]) if r[1] else None,
                project_id=str(r[2]) if r[2] else None,
                given_by=r[3],
                content=r[4],
                received_on=r[5],
                source=Provenance(raw_dump_id=str(r[6]), event_id=r[7]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, role_id, project_id, given_by, content, received_on, raw_dump_id, "
                    "event_id FROM feedback WHERE user_id = :uid"
                ),
                1,
            )
        ]
        return roles, projects, stories, skills, achievements, education, languages, feedback


# --- Resolving a reviewed patch into an event payload -----------------------


def _resolve(patch: Patch, labels: dict[str, str], dump_id: str) -> dict:
    """Give every draft a real id (reusing the existing entity's id when the
    draft updates one) and turn key/label references into ids. The result is
    the event payload: plain, id-only, replayable."""
    ids: dict[str, str] = {}  # draft key -> id

    def mint(drafts: Iterable, kind: EntityKind) -> None:
        prefix = LABEL_PREFIX[kind]
        for d in drafts:
            if d.existing:
                if not d.existing.startswith(prefix) or d.existing not in labels:
                    raise Conflict(f"'{d.existing}' is not an existing {kind}.")
                ids[d.key] = labels[d.existing]
            else:
                ids[d.key] = str(uuid.uuid4())

    for kind, drafts in (
        ("role", patch.roles),
        ("project", patch.projects),
        ("story", patch.stories),
        ("skill", patch.skills),
        ("achievement", patch.achievements),
        ("education", patch.education),
        ("language", patch.languages),
        ("feedback", patch.feedback),
    ):
        mint(drafts, kind)

    def ref(value: str | None, kind: EntityKind) -> str | None:
        if value is None:
            return None
        if value in ids:
            return ids[value]
        if value in labels and value.startswith(LABEL_PREFIX[kind]):
            return labels[value]
        raise Conflict(f"'{value}' does not refer to a {kind} in this patch or in the brain.")

    return {
        "raw_dump_id": dump_id,
        "roles": [
            {
                "id": ids[d.key],
                "company": d.company,
                "title": d.title,
                "start_date": d.start_date,
                "end_date": d.end_date,
                "level": d.level,
                "responsibilities": d.responsibilities,
            }  # fmt: skip
            for d in patch.roles
        ],
        "projects": [
            {
                "id": ids[d.key],
                "role_id": ref(d.role, "role"),
                "name": d.name,
                "problem": d.problem,
                "action": d.action,
                "result": d.result,
                "tech": d.tech,
                "metrics": d.metrics,
            }  # fmt: skip
            for d in patch.projects
        ],
        "stories": [
            {
                "id": ids[d.key],
                "role_id": ref(d.role, "role"),
                "project_id": ref(d.project, "project"),
                "title": d.title,
                "situation": d.situation,
                "task": d.task,
                "action": d.action,
                "result": d.result,
                "competencies": d.competencies,
            }  # fmt: skip
            for d in patch.stories
        ],
        "skills": [
            {
                "id": ids[d.key],
                "name": d.name,
                "depth": d.depth,
                "project_ids": [ref(p, "project") for p in d.projects],
                "role_ids": [ref(r, "role") for r in d.roles],
                "achievement_ids": [ref(a, "achievement") for a in d.achievements],
            }  # fmt: skip
            for d in patch.skills
        ],
        "achievements": [
            {
                "id": ids[d.key],
                "kind": d.kind,
                "title": d.title,
                "issuer": d.issuer,
                "achieved_on": d.achieved_on,
            }  # fmt: skip
            for d in patch.achievements
        ],
        "education": [
            {
                "id": ids[d.key],
                "institution": d.institution,
                "qualification": d.qualification,
                "field": d.field,
                "start_date": d.start_date,
                "end_date": d.end_date,
            }
            for d in patch.education
        ],
        "languages": [
            {"id": ids[d.key], "name": d.name, "proficiency": d.proficiency}
            for d in patch.languages
        ],
        "feedback": [
            {
                "id": ids[d.key],
                "role_id": ref(d.role, "role"),
                "project_id": ref(d.project, "project"),
                "given_by": d.given_by,
                "content": d.content,
                "received_on": d.received_on,
            }  # fmt: skip
            for d in patch.feedback
        ],
    }


# --- Applying an event to the projection (used live and by rebuild) ----------


def _apply(
    c: Connection, uid: str, event_id: int, kind: str, payload: dict, at: dt.datetime
) -> None:
    if kind == "patch_confirmed":
        _apply_patch(c, uid, event_id, payload)
    elif kind == "entity_edited":
        _apply_edit(c, uid, event_id, payload)
    elif kind == "entity_retired":
        c.execute(
            _q(
                f"UPDATE {TABLE[payload['kind']]} SET retired_at = :at, event_id = :e WHERE user_id = :uid AND id = :id"
            ),
            {"at": at, "e": event_id, "uid": uid, "id": payload["id"]},
        )
    else:
        raise ValueError(f"unknown event kind {kind}")


def _apply_patch(c: Connection, uid: str, event_id: int, p: dict) -> None:
    dump = p["raw_dump_id"]
    base = {"uid": uid, "e": event_id, "d": dump}
    for r in p["roles"]:
        c.execute(
            _q(
                "INSERT INTO roles (id, user_id, company, title, start_date, end_date, level, responsibilities, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :company, :title, :start_date, :end_date, :level, :responsibilities, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET company = EXCLUDED.company, title = EXCLUDED.title, "
                "start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date, level = EXCLUDED.level, "
                "responsibilities = EXCLUDED.responsibilities, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            # Events from before migration 006 carry no responsibilities (ADR 0019).
            {**base, "responsibilities": [], **r},
        )
    for r in p["projects"]:
        c.execute(
            _q(
                "INSERT INTO projects (id, user_id, role_id, name, problem, action, result, tech, metrics, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :role_id, :name, :problem, :action, :result, :tech, :metrics, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET role_id = EXCLUDED.role_id, name = EXCLUDED.name, "
                "problem = EXCLUDED.problem, action = EXCLUDED.action, result = EXCLUDED.result, "
                "tech = EXCLUDED.tech, metrics = EXCLUDED.metrics, raw_dump_id = EXCLUDED.raw_dump_id, "
                "event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )
    for r in p["stories"]:
        c.execute(
            _q(
                "INSERT INTO stories (id, user_id, role_id, project_id, title, situation, task, action, result, competencies, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :role_id, :project_id, :title, :situation, :task, :action, :result, :competencies, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET role_id = EXCLUDED.role_id, project_id = EXCLUDED.project_id, "
                "title = EXCLUDED.title, situation = EXCLUDED.situation, task = EXCLUDED.task, "
                "action = EXCLUDED.action, result = EXCLUDED.result, competencies = EXCLUDED.competencies, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )
    for r in p["skills"]:
        c.execute(
            _q(
                "INSERT INTO skills (id, user_id, name, depth, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :name, :depth, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, depth = EXCLUDED.depth, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, "id": r["id"], "name": r["name"], "depth": r["depth"]},
        )
        _set_evidence(c, r["id"], r["project_ids"])
        _set_skill_roles(c, r["id"], r.get("role_ids", []))  # absent before migration 006
    for r in p["achievements"]:
        c.execute(
            _q(
                "INSERT INTO achievements (id, user_id, kind, title, issuer, achieved_on, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :kind, :title, :issuer, :achieved_on, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, title = EXCLUDED.title, "
                "issuer = EXCLUDED.issuer, achieved_on = EXCLUDED.achieved_on, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )
    # After the achievements themselves: a skill may point at a credential
    # this same patch creates (ADR 0020). Absent from events before 007.
    for r in p["skills"]:
        _set_skill_achievements(c, r["id"], r.get("achievement_ids", []))
    for r in p.get("education", []):
        c.execute(
            _q(
                "INSERT INTO education (id, user_id, institution, qualification, field, start_date, end_date, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :institution, :qualification, :field, :start_date, :end_date, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET institution = EXCLUDED.institution, qualification = EXCLUDED.qualification, field = EXCLUDED.field, start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date, raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )
    for r in p.get("languages", []):
        c.execute(
            _q(
                "INSERT INTO languages (id, user_id, name, proficiency, raw_dump_id, event_id) VALUES (:id, :uid, :name, :proficiency, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, proficiency = EXCLUDED.proficiency, raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )
    for r in p.get("feedback", []):
        c.execute(
            _q(
                "INSERT INTO feedback (id, user_id, role_id, project_id, given_by, content, received_on, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :role_id, :project_id, :given_by, :content, :received_on, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET role_id = EXCLUDED.role_id, project_id = EXCLUDED.project_id, "
                "given_by = EXCLUDED.given_by, content = EXCLUDED.content, received_on = EXCLUDED.received_on, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
        )


def _apply_edit(c: Connection, uid: str, event_id: int, p: dict) -> None:
    kind, entity_id, fields = p["kind"], p["id"], dict(p["fields"])
    project_ids = fields.pop("project_ids", None)
    role_ids = fields.pop("role_ids", None)
    achievement_ids = fields.pop("achievement_ids", None)
    if fields:
        # Column names come from EDITABLE (validated in edit_entity), never from the request.
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        c.execute(
            _q(
                f"UPDATE {TABLE[kind]} SET {assignments}, event_id = :e WHERE user_id = :uid AND id = :id"
            ),
            {**fields, "e": event_id, "uid": uid, "id": entity_id},
        )
    else:
        c.execute(
            _q(f"UPDATE {TABLE[kind]} SET event_id = :e WHERE user_id = :uid AND id = :id"),
            {"e": event_id, "uid": uid, "id": entity_id},
        )
    if kind == "skill" and project_ids is not None:
        _set_evidence(c, entity_id, project_ids)
    if kind == "skill" and role_ids is not None:
        _set_skill_roles(c, entity_id, role_ids)
    if kind == "skill" and achievement_ids is not None:
        _set_skill_achievements(c, entity_id, achievement_ids)


def _set_evidence(c: Connection, skill_id: str, project_ids: list[str]) -> None:
    c.execute(_q("DELETE FROM skill_evidence WHERE skill_id = :s"), {"s": skill_id})
    for pid in project_ids:
        c.execute(
            _q(
                "INSERT INTO skill_evidence (skill_id, project_id) VALUES (:s, :p) ON CONFLICT DO NOTHING"
            ),
            {"s": skill_id, "p": pid},
        )


def _set_skill_roles(c: Connection, skill_id: str, role_ids: list[str]) -> None:
    """The role-side twin of `_set_evidence` (ADR 0019): replace, not merge."""
    c.execute(_q("DELETE FROM skill_roles WHERE skill_id = :s"), {"s": skill_id})
    for rid in role_ids:
        c.execute(
            _q(
                "INSERT INTO skill_roles (skill_id, role_id) VALUES (:s, :r) ON CONFLICT DO NOTHING"
            ),
            {"s": skill_id, "r": rid},
        )


def _set_skill_achievements(c: Connection, skill_id: str, achievement_ids: list[str]) -> None:
    """Credentials that evidence a skill (ADR 0020): replace, not merge."""
    c.execute(_q("DELETE FROM skill_achievements WHERE skill_id = :s"), {"s": skill_id})
    for aid in achievement_ids:
        c.execute(
            _q(
                "INSERT INTO skill_achievements (skill_id, achievement_id) VALUES (:s, :a) "
                "ON CONFLICT DO NOTHING"
            ),
            {"s": skill_id, "a": aid},
        )


# --- Coverage and rendering helpers ------------------------------------------


def _coverage(
    competencies: list[Competency], roles: list[Role], projects: list[Project], stories: list[Story]
) -> Coverage:
    project_role = {p.id: p.role_id for p in projects}
    role_ids = [r.id for r in roles] + ["other"]
    cells: dict[str, dict[str, str]] = {
        c.key: {rid: "none" for rid in role_ids} for c in competencies
    }
    for s in stories:
        rid = s.role_id or project_role.get(s.project_id or "") or "other"
        if rid not in role_ids:
            rid = "other"
        strength = "strong" if (s.result or "").strip() else "weak"
        for key in s.competencies:
            if key in cells and (cells[key][rid] == "none" or strength == "strong"):
                cells[key][rid] = strength
    return Coverage(competencies=competencies, roles=roles, cells=cells)


def _span(start: dt.date | None, end: dt.date | None) -> str:
    fmt = lambda d: d.strftime("%Y-%m") if d else None  # noqa: E731
    return f"{fmt(start) or '?'} → {fmt(end) or 'now'}"


def _excerpt(text: str, limit: int = 80) -> str:
    """A feedback quote can run to a paragraph; the index stays scannable by
    showing only its opening. `brain_context` shows the full text."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# The live entities that carry embeddings, as one derived table `live` (id),
# for an EXISTS that keeps retired entities out of search and storage.
_LIVE_EMBEDDED = (
    "SELECT 1 FROM ("
    "SELECT id FROM projects WHERE user_id = :uid AND retired_at IS NULL UNION ALL "
    "SELECT id FROM stories WHERE user_id = :uid AND retired_at IS NULL UNION ALL "
    "SELECT id FROM achievements WHERE user_id = :uid AND retired_at IS NULL UNION ALL "
    "SELECT id FROM feedback WHERE user_id = :uid AND retired_at IS NULL"
    ") AS live WHERE true"
)


def _vector(values: list[float]) -> str:
    """A vector as pgvector's text form, "[0.1,0.2,…]". Sent as text and cast in
    SQL, so no pgvector client library is needed."""
    return "[" + ",".join(f"{x:.7g}" for x in values) + "]"


def _embedding_texts(entities: tuple) -> dict[str, tuple[str, str]]:
    """What is embedded for each live project, story, achievement and feedback
    (ADR 0038): id → (kind, text). The entity's own block without its label
    (labels move when an entity is retired), led by what it is, plus the role it
    belongs to. Version `EMBED_RENDER_VERSION`: change this, bump that."""
    roles, projects, stories, _, achievements, _, _, feedback = entities
    blocks = _entity_blocks(entities)
    role_by_id = {r.id: r for r in roles}

    def bare(label: str) -> str:
        return blocks[label].removeprefix(f"[{label}] ")

    def at(role_id: str | None) -> str:
        role = role_by_id.get(role_id) if role_id else None
        return f"\n  At: {role.title}, {role.company}" if role else ""

    texts: dict[str, tuple[str, str]] = {}
    for p in projects:
        texts[p.id] = ("project", f"Project: {bare(p.label)}{at(p.role_id)}")
    for s in stories:
        texts[s.id] = ("story", f"Story: {bare(s.label)}{at(s.role_id)}")
    for a in achievements:
        texts[a.id] = ("achievement", f"{a.kind.capitalize()}: {bare(a.label)}")
    for f in feedback:
        texts[f.id] = ("feedback", f"Feedback from {bare(f.label)}")
    return texts


def _entity_blocks(entities: tuple) -> dict[str, str]:
    """Every live entity's own block, by label: the unit `brain_context` is
    made of and the unit Harvey can look up. A role's block is its heading and
    responsibilities; its projects are blocks of their own."""
    roles, projects, stories, skills, achievements, education, languages, feedback = entities
    role_by_id = {r.id: r for r in roles}
    project_by_id = {p.id: p for p in projects}
    label_of = {e.id: e.label for e in (*roles, *projects, *achievements)}
    blocks: dict[str, str] = {}
    for r in roles:
        lines = [f"## [{r.label}] {r.title} at {r.company} ({_span(r.start_date, r.end_date)})"]
        if r.responsibilities:
            lines.append("Responsibilities:")
            lines.extend(f"  - {line}" for line in r.responsibilities)
        blocks[r.label] = "\n".join(lines)
    for p in projects:
        blocks[p.label] = _project_block(p)
    for s in stories:
        blocks[s.label] = (
            f"[{s.label}] {s.title} (competencies: {', '.join(s.competencies) or 'none'})\n"
            f"  Situation: {s.situation or '—'}\n  Task: {s.task or '—'}\n"
            f"  Action: {s.action or '—'}\n  Result: {s.result or '—'}"
        )
    for f in feedback:
        about = ""
        if f.project_id in project_by_id:
            about = f" — on {project_by_id[f.project_id].name}"
        elif f.role_id in role_by_id:
            about = f" — at {role_by_id[f.role_id].title}"
        when = f" ({f.received_on})" if f.received_on else ""
        blocks[f.label] = f"[{f.label}] {f.given_by}{when}{about}: {f.content}"
    for k in skills:
        where = [label_of[i] for i in (*k.project_ids, *k.role_ids) if i in label_of]
        shown = [label_of[i] for i in k.achievement_ids if i in label_of]
        used = f" — used in {', '.join(where)}" if where else ""
        certified = f" — certified by {', '.join(shown)}" if shown else ""
        blocks[k.label] = f"[{k.label}] {k.name} — self-rated {k.depth}/5{used}{certified}"
    for a in achievements:
        blocks[a.label] = f"[{a.label}] {a.title}" + (f" ({a.issuer})" if a.issuer else "")
    for e in education:
        blocks[e.label] = f"[{e.label}] {e.institution}" + (
            f" — {e.qualification}" if e.qualification else ""
        )
    for language in languages:
        blocks[language.label] = f"[{language.label}] {language.name}" + (
            f" — {language.proficiency}" if language.proficiency else ""
        )
    return blocks


def _project_block(p: Project) -> str:
    lines = [f"[{p.label}] {p.name}"]
    if p.problem:
        lines.append(f"  Problem: {p.problem}")
    if p.action:
        lines.append(f"  Action: {p.action}")
    if p.result:
        lines.append(f"  Result: {p.result}")
    if p.tech:
        lines.append(f"  Tech: {', '.join(p.tech)}")
    if p.metrics:
        lines.append(f"  Metrics: {', '.join(p.metrics)}")
    return "\n".join(lines)
