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
import json
import uuid
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from anyview.brain.models import (
    EDITABLE,
    LABEL_PREFIX,
    Achievement,
    Brain,
    Competency,
    Coverage,
    EntityKind,
    Event,
    Patch,
    Project,
    Proposal,
    Provenance,
    RawDump,
    Role,
    Skill,
    Story,
)

TABLE: dict[EntityKind, str] = {
    "role": "roles",
    "project": "projects",
    "story": "stories",
    "skill": "skills",
    "achievement": "achievements",
}


class NotFound(Exception):
    pass


class Conflict(Exception):
    """The request does not fit the current state (already resolved, bad reference…)."""


def _q(sql: str) -> sa.TextClause:
    return sa.text(sql)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # --- users ---------------------------------------------------------------

    def ensure_user(self, uid: str, email: str) -> None:
        with self.engine.begin() as c:
            c.execute(
                _q(
                    "INSERT INTO users (uid, email) VALUES (:uid, :email) "
                    "ON CONFLICT (uid) DO UPDATE SET email = EXCLUDED.email"
                ),
                {"uid": uid, "email": email},
            )

    # --- raw dumps -----------------------------------------------------------

    def create_dump(self, uid: str, *, kind: str, text: str, object_name: str | None) -> RawDump:
        dump_id = str(uuid.uuid4())
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "INSERT INTO raw_dumps (id, user_id, kind, text, object_name) "
                    "VALUES (:id, :uid, :kind, :text, :obj) RETURNING created_at"
                ),
                {"id": dump_id, "uid": uid, "kind": kind, "text": text, "obj": object_name},
            ).one()
        return RawDump(id=dump_id, kind=kind, text=text, object_name=object_name, created_at=row[0])

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

    # --- proposals (the review queue) ----------------------------------------

    def create_proposal(self, uid: str, *, dump_id: str, patch: Patch, model: str) -> Proposal:
        pid = str(uuid.uuid4())
        with self.engine.begin() as c:
            row = c.execute(
                _q(
                    "INSERT INTO proposals (id, user_id, raw_dump_id, patch, model) "
                    "SELECT :id, :uid, :dump, CAST(:patch AS jsonb), :model FROM raw_dumps d "
                    "WHERE d.id = :dump AND d.user_id = :uid "
                    "RETURNING created_at, (SELECT kind FROM raw_dumps WHERE id = :dump), "
                    "(SELECT left(text, 400) FROM raw_dumps WHERE id = :dump)"
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
            created_at=row[0], resolved_at=None, dump_kind=row[1], dump_excerpt=row[2],
        )  # fmt: skip

    def pending_proposals(self, uid: str) -> list[Proposal]:
        with self.engine.begin() as c:
            rows = c.execute(
                _q(
                    "SELECT p.id, p.raw_dump_id, p.status, p.patch, p.model, p.created_at, "
                    "p.resolved_at, d.kind, left(d.text, 400) "
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
                    "p.resolved_at, d.kind, left(d.text, 400) "
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
            model=r[4], created_at=r[5], resolved_at=r[6], dump_kind=r[7], dump_excerpt=r[8],
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

    def confirm_proposal(self, uid: str, proposal_id: str, patch: Patch) -> Event:
        """The user reviewed (and possibly edited) the patch. Resolve its keys and
        labels to real ids, append one event, apply it, and close the proposal —
        all in one transaction, so the log and the projection cannot disagree."""
        if patch.is_empty():
            raise Conflict("Nothing left to add. Discard the proposal instead.")
        with self.engine.begin() as c:
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
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
            c.execute(
                _q("UPDATE proposals SET status = 'confirmed', resolved_at = now() WHERE id = :id"),
                {"id": proposal_id},
            )
        return event

    # --- direct edits ----------------------------------------------------------

    def edit_entity(
        self, uid: str, kind: EntityKind, entity_id: str, fields: dict[str, Any]
    ) -> Event:
        unknown = set(fields) - EDITABLE[kind]
        if unknown:
            raise Conflict(f"Cannot edit {', '.join(sorted(unknown))} on a {kind}.")
        if not fields:
            raise Conflict("Nothing to change.")
        with self.engine.begin() as c:
            self._require_live(c, uid, kind, entity_id)
            payload = {"kind": kind, "id": entity_id, "fields": fields}
            event = self._append(c, uid, kind="entity_edited", payload=payload)
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
        return event

    def retire_entity(self, uid: str, kind: EntityKind, entity_id: str) -> Event:
        with self.engine.begin() as c:
            self._require_live(c, uid, kind, entity_id)
            payload = {"kind": kind, "id": entity_id}
            event = self._append(c, uid, kind="entity_retired", payload=payload)
            _apply(c, uid, event.id, event.kind, payload, event.created_at)
        return event

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
            for table in ("stories", "skills", "achievements", "projects", "roles"):
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
            roles, projects, stories, skills, achievements = self._entities(c, uid)
            pending = c.execute(
                _q("SELECT count(*) FROM proposals WHERE user_id = :uid AND status = 'pending'"),
                {"uid": uid},
            ).scalar_one()
            competencies = self._competencies(c)
        return Brain(
            roles=roles, projects=projects, stories=stories, skills=skills, achievements=achievements,
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
            roles, projects, stories, skills, achievements = self._entities(c, uid)
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
        labels = {
            e.label: e.id
            for group in (roles, projects, stories, skills, achievements)
            for e in group
        }
        return "\n".join(lines), labels

    def brain_context(self, uid: str) -> str:
        """The confirmed brain rendered as the candidate's record for interview
        prompts: fuller than the index, still one entity per block, labels kept
        so answers can cite them."""
        with self.engine.begin() as c:
            roles, projects, stories, skills, achievements = self._entities(c, uid)
        role_by_id = {r.id: r for r in roles}
        out: list[str] = []
        for r in roles:
            out.append(
                f"## [{r.label}] {r.title} at {r.company} ({_span(r.start_date, r.end_date)})"
            )
            for p in (p for p in projects if p.role_id == r.id):
                out.append(_project_block(p))
        loose = [p for p in projects if p.role_id not in role_by_id]
        if loose:
            out.append("## Other projects")
            out.extend(_project_block(p) for p in loose)
        if stories:
            out.append("## Stories")
            for s in stories:
                out.append(
                    f"[{s.label}] {s.title} (competencies: {', '.join(s.competencies) or 'none'})\n"
                    f"  Situation: {s.situation or '—'}\n  Task: {s.task or '—'}\n"
                    f"  Action: {s.action or '—'}\n  Result: {s.result or '—'}"
                )
        if skills:
            out.append("## Skills")
            out.extend(f"[{k.label}] {k.name} — self-rated {k.depth}/5" for k in skills)
        if achievements:
            out.append("## Achievements and credentials")
            out.extend(
                f"[{a.label}] {a.title}" + (f" ({a.issuer})" if a.issuer else "")
                for a in achievements
            )
        return "\n".join(out)

    # --- usage --------------------------------------------------------------------

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
        roles, projects, stories, skills, achievements = self._entities(c, uid)
        return {
            e.label: e.id
            for group in (roles, projects, stories, skills, achievements)
            for e in group
        }

    @staticmethod
    def _entities(
        c: Connection, uid: str
    ) -> tuple[list[Role], list[Project], list[Story], list[Skill], list[Achievement]]:
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
                source=Provenance(raw_dump_id=str(r[6]), event_id=r[7]),
            )  # fmt: skip
            for i, r in enumerate(
                rows(
                    "SELECT id, company, title, start_date, end_date, level, raw_dump_id, event_id "
                    "FROM roles WHERE user_id = :uid"
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
        skills = [
            Skill(
                id=str(r[0]),
                label=f"K{i}",
                name=r[1],
                depth=r[2],
                project_ids=evidence.get(str(r[0]), []),
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
        return roles, projects, stories, skills, achievements


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
                "INSERT INTO roles (id, user_id, company, title, start_date, end_date, level, raw_dump_id, event_id) "
                "VALUES (:id, :uid, :company, :title, :start_date, :end_date, :level, :d, :e) "
                "ON CONFLICT (id) DO UPDATE SET company = EXCLUDED.company, title = EXCLUDED.title, "
                "start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date, level = EXCLUDED.level, "
                "raw_dump_id = EXCLUDED.raw_dump_id, event_id = EXCLUDED.event_id, retired_at = NULL"
            ),
            {**base, **r},
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


def _apply_edit(c: Connection, uid: str, event_id: int, p: dict) -> None:
    kind, entity_id, fields = p["kind"], p["id"], dict(p["fields"])
    project_ids = fields.pop("project_ids", None)
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


def _set_evidence(c: Connection, skill_id: str, project_ids: list[str]) -> None:
    c.execute(_q("DELETE FROM skill_evidence WHERE skill_id = :s"), {"s": skill_id})
    for pid in project_ids:
        c.execute(
            _q(
                "INSERT INTO skill_evidence (skill_id, project_id) VALUES (:s, :p) ON CONFLICT DO NOTHING"
            ),
            {"s": skill_id, "p": pid},
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
