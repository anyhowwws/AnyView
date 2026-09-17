"""The schema's own invariants, exercised directly in SQL."""

import uuid

import pytest
import sqlalchemy
from sqlalchemy.exc import IntegrityError

from anyview.db.migrate import migrate


def test_migrations_are_idempotent(db_engine):
    assert migrate(db_engine) == []  # a second run applies nothing


def _seed(conn):
    conn.execute(sqlalchemy.text("INSERT INTO users (uid, email) VALUES ('u1', 'u1@example.com')"))
    dump = uuid.uuid4()
    conn.execute(
        sqlalchemy.text(
            "INSERT INTO raw_dumps (id, user_id, kind, text) VALUES (:id, 'u1', 'text', 'hello')"
        ),
        {"id": dump},
    )
    ev = conn.execute(
        sqlalchemy.text(
            "INSERT INTO events (user_id, seq, kind, payload) "
            "VALUES ('u1', 1, 'patch_confirmed', '{}') RETURNING id"
        )
    ).scalar_one()
    return dump, ev


def test_events_are_append_only(db):
    with db.begin() as conn:
        _seed(conn)
    with db.begin() as conn, pytest.raises(IntegrityError, match="append-only"):
        conn.execute(sqlalchemy.text("UPDATE events SET payload = '{\"x\": 1}' WHERE id = 1"))
    with db.begin() as conn, pytest.raises(IntegrityError, match="append-only"):
        conn.execute(sqlalchemy.text("DELETE FROM events WHERE id = 1"))


def test_projection_rows_need_a_dump_and_an_event(db):
    with db.begin() as conn:
        dump, ev = _seed(conn)
    role = (
        "INSERT INTO roles (id, user_id, company, title, raw_dump_id, event_id) "
        "VALUES (:id, 'u1', 'Acme', 'SRE', :d, :e)"
    )
    with db.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(sqlalchemy.text(role), {"id": uuid.uuid4(), "d": None, "e": ev})
    with db.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(sqlalchemy.text(role), {"id": uuid.uuid4(), "d": dump, "e": None})
    with db.begin() as conn, pytest.raises(IntegrityError):  # a dump that does not exist
        conn.execute(sqlalchemy.text(role), {"id": uuid.uuid4(), "d": uuid.uuid4(), "e": ev})
    with db.begin() as conn:
        conn.execute(sqlalchemy.text(role), {"id": uuid.uuid4(), "d": dump, "e": ev})


def test_stories_reject_unknown_competencies(db):
    with db.begin() as conn:
        dump, ev = _seed(conn)
    story = (
        "INSERT INTO stories (id, user_id, title, competencies, raw_dump_id, event_id) "
        "VALUES (:id, 'u1', 't', :c, :d, :e)"
    )
    with db.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            sqlalchemy.text(story),
            {"id": uuid.uuid4(), "c": ["ownership", "vibes"], "d": dump, "e": ev},
        )
    with db.begin() as conn:
        conn.execute(
            sqlalchemy.text(story),
            {"id": uuid.uuid4(), "c": ["ownership", "failure"], "d": dump, "e": ev},
        )


def test_one_live_skill_per_name(db):
    with db.begin() as conn:
        dump, ev = _seed(conn)
    skill = (
        "INSERT INTO skills (id, user_id, name, depth, raw_dump_id, event_id, retired_at) "
        "VALUES (:id, 'u1', :n, 3, :d, :e, :r)"
    )
    with db.begin() as conn:
        conn.execute(
            sqlalchemy.text(skill),
            {"id": uuid.uuid4(), "n": "Terraform", "d": dump, "e": ev, "r": None},
        )
    with db.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            sqlalchemy.text(skill),
            {"id": uuid.uuid4(), "n": "terraform", "d": dump, "e": ev, "r": None},
        )
    with db.begin() as conn:  # a retired duplicate is fine
        conn.execute(
            sqlalchemy.text(skill),
            {"id": uuid.uuid4(), "n": "terraform", "d": dump, "e": ev, "r": "2026-01-01"},
        )


def test_pgvector_is_available(db):
    with db.begin() as conn:
        assert (
            conn.execute(
                sqlalchemy.text("SELECT '[1,2,3]'::vector(3) <-> '[1,2,4]'::vector(3)")
            ).scalar_one()
            == 1.0
        )
