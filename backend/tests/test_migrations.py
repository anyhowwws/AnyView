"""The schema's own invariants, exercised directly in SQL."""

import uuid

import pytest
import sqlalchemy
from sqlalchemy.exc import IntegrityError

from anyview.db.migrate import MIGRATIONS_DIR, migrate


def test_migrations_are_idempotent(db_engine):
    assert migrate(db_engine) == []  # a second run applies nothing


def test_migrations_dir_actually_has_the_schema_files():
    # Caught a real production incident: MIGRATIONS_DIR's fallback path math
    # only holds for an editable local install. Installed non-editably (as
    # in the Docker image), the same traversal lands somewhere with no
    # migrations/ directory, glob("*.sql") silently returns nothing, and
    # migrate() "succeeds" having applied zero migrations — the app boots
    # against a database with only an empty schema_migrations table. This
    # guards that MIGRATIONS_DIR resolves to a real, non-empty directory
    # under whatever install produced this test run.
    assert MIGRATIONS_DIR.is_dir(), (
        f"MIGRATIONS_DIR ({MIGRATIONS_DIR}) does not exist — migrate() would "
        "silently apply nothing. Set the MIGRATIONS_DIR env var if this "
        "package was installed non-editably."
    )
    assert list(MIGRATIONS_DIR.glob("*.sql")), f"no .sql files found in {MIGRATIONS_DIR}"


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


def _erasing(conn, uid):
    conn.execute(sqlalchemy.text("SELECT set_config('anyview.erasing_user', :u, true)"), {"u": uid})


def test_erasing_a_user_may_delete_only_their_events(db):
    """ADR 0018: the one delete the log allows is a whole user's stream, in a
    transaction that names that user first."""
    with db.begin() as conn:
        _seed(conn)
    # Naming someone else does not open this user's events.
    with db.begin() as conn, pytest.raises(IntegrityError, match="append-only"):
        _erasing(conn, "someone-else")
        conn.execute(sqlalchemy.text("DELETE FROM events WHERE id = 1"))
    # Naming the right user still never allows rewriting history.
    with db.begin() as conn, pytest.raises(IntegrityError, match="append-only"):
        _erasing(conn, "u1")
        conn.execute(sqlalchemy.text("UPDATE events SET payload = '{\"x\": 1}' WHERE id = 1"))
    with db.begin() as conn:
        _erasing(conn, "u1")
        assert conn.execute(sqlalchemy.text("DELETE FROM events WHERE id = 1")).rowcount == 1


def test_the_erasing_mark_ends_with_its_transaction(db):
    """set_config(..., true) is transaction-local: a pooled connection's next
    transaction must not inherit it."""
    with db.begin() as conn:
        _seed(conn)
    with db.connect() as conn:
        with conn.begin():
            _erasing(conn, "u1")
        with conn.begin(), pytest.raises(IntegrityError, match="append-only"):
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


def test_the_resume_pointer_must_be_a_real_dump(db):
    """`users.resume_dump_id` is a foreign key, so the resume on file cannot
    point at a dump that does not exist (ADR 0014)."""
    with db.begin() as conn:
        dump, _ = _seed(conn)
    with db.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            sqlalchemy.text("UPDATE users SET resume_dump_id = :d WHERE uid = 'u1'"),
            {"d": uuid.uuid4()},
        )
    with db.begin() as conn:
        conn.execute(
            sqlalchemy.text("UPDATE users SET resume_dump_id = :d WHERE uid = 'u1'"), {"d": dump}
        )


def test_the_backfilled_hash_matches_the_one_python_writes(db):
    """Migration 003 backfills text_sha256 in SQL; the app computes it in
    Python. If the two ever disagree, the no-op check silently stops working."""
    from anyview.db.repository import text_sha256

    with db.begin() as conn:
        _seed(conn)
        conn.execute(
            sqlalchemy.text(
                "UPDATE raw_dumps SET text_sha256 = encode(sha256(convert_to(text, 'UTF8')), 'hex')"
            )
        )
        row = conn.execute(sqlalchemy.text("SELECT text, text_sha256 FROM raw_dumps")).one()
    assert row[1] == text_sha256(row[0])
