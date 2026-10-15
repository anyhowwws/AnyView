"""Garden embeddings (ADR 0038): one vector per confirmed project, story,
achievement and feedback, made before the write that changes it, and searched
filter-then-vector. Needs TEST_DATABASE_URL; skips without it."""

import pytest
import sqlalchemy as sa

from anyview.api import interview
from anyview.api.brain import embedder
from anyview.db.repository import EMBED_RENDER_VERSION, Conflict, Embedder
from anyview.interview import engine
from anyview.interview.prompts import ideal_user
from anyview.llm.adapter import ModelError
from anyview.llm.fake import FakeModel
from tests.test_repository import UID, first_patch, repo  # noqa: F401


def _rows(db, uid=UID):
    with db.begin() as c:
        return (
            c.execute(
                sa.text(
                    "SELECT entity_id::text, kind, render_version, model FROM entity_embeddings "
                    "WHERE user_id = :u ORDER BY kind"
                ),
                {"u": uid},
            )
            .mappings()
            .all()
        )


def _confirm(repo, patch, model):  # noqa: F811
    dump = repo.create_dump(UID, kind="text", text="dump text", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=patch, model="fake")
    return repo.confirm_proposal(UID, prop.id, patch, embed=embedder(model))


def _embeds(model):
    return [c for c in model.calls if c["call"] == "embed"]


def test_confirming_embeds_projects_stories_and_achievements_only(repo, db):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    rows = _rows(db)
    assert sorted(r["kind"] for r in rows) == ["achievement", "project", "story"]
    assert {r["render_version"] for r in rows} == {EMBED_RENDER_VERSION}
    assert {r["model"] for r in rows} == {"fake"}
    texts = sorted(c["user"] for c in _embeds(model))
    assert texts[1].startswith("Project: Billing service to Cloud Run")
    assert "At: Senior Cloud Architect, Acme Corp" in texts[1]
    assert not any("[P1]" in t for t in texts)  # labels move; the text must not


def test_a_failed_embedding_saves_nothing(repo, db):  # noqa: F811
    dump = repo.create_dump(UID, kind="text", text="dump text", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=first_patch(), model="fake")
    with pytest.raises(ModelError):
        repo.confirm_proposal(UID, prop.id, first_patch(), embed=embedder(FakeModel(fail="embed")))
    assert repo.brain(UID).projects == []
    assert [p.id for p in repo.pending_proposals(UID)] == [prop.id]
    assert _rows(db) == []


def test_an_edit_re_embeds_only_what_changed(repo):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    before = len(_embeds(model))
    project = repo.brain(UID).projects[0]
    repo.edit_entity(UID, "project", project.id, {"result": "-40% cost"}, embed=embedder(model))
    changed = _embeds(model)[before:]
    assert len(changed) == 1 and "-40% cost" in changed[0]["user"]


def test_editing_a_role_re_embeds_its_projects_and_stories(repo):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    before = len(_embeds(model))
    role = repo.brain(UID).roles[0]
    repo.edit_entity(UID, "role", role.id, {"title": "Principal Architect"}, embed=embedder(model))
    texts = [c["user"] for c in _embeds(model)[before:]]
    assert len(texts) == 2 and all("Principal Architect" in t for t in texts)


def test_retiring_drops_the_vector_and_search_ignores_it(repo, db):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    story = repo.brain(UID).stories[0]
    repo.retire_entity(UID, "story", story.id, embed=embedder(model))
    assert "story" not in {r["kind"] for r in _rows(db)}
    [query] = model.embed(["Cutting over billing without downtime"], session_id="sess-test")
    assert "story" not in {f.kind for f in repo.search_garden(UID, query)}


def test_search_is_nearest_first_filtered_by_kind_and_user(repo):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    [query] = model.embed(["rehearsed cutovers with zero downtime"], session_id="sess-test")
    found = repo.search_garden(UID, query)
    assert found[0].label == "S1" and found[0].text.startswith("[S1] Cutting over billing")
    assert [f.distance for f in found] == sorted(f.distance for f in found)
    assert {f.kind for f in repo.search_garden(UID, query, kinds=["achievement"])} == {
        "achievement"
    }
    assert repo.search_garden("uid-other", query) == []


def test_rebuild_keeps_every_vector_current(repo, db):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    repo.rebuild(UID)
    assert len(_rows(db)) == 3
    assert repo.embed_garden(UID, embedder(model)) == 0


def test_the_backfill_embeds_what_has_no_vector_once(repo, db):  # noqa: F811
    dump = repo.create_dump(UID, kind="text", text="dump text", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=first_patch(), model="fake")
    repo.confirm_proposal(UID, prop.id, first_patch())  # no embedder: as before this change
    assert _rows(db) == []
    model = FakeModel()
    assert repo.embed_garden(UID, embedder(model)) == 3
    assert len(_rows(db)) == 3
    assert repo.embed_garden(UID, embedder(model)) == 0


def test_a_garden_changed_mid_write_is_refused(repo, db):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    project = repo.brain(UID).projects[0]

    def embed_while_someone_edits(texts):
        # Another tab renames the project while this write is embedding its
        # result, so the text this write would store no longer exists.
        repo.edit_entity(UID, "project", project.id, {"name": "Billing on Cloud Run"})
        return model.embed(texts, session_id="sess-test")

    with pytest.raises(Conflict):
        repo.edit_entity(
            UID,
            "project",
            project.id,
            {"result": "-40% cost"},
            embed=Embedder(model="fake", embed=embed_while_someone_edits),
        )
    after = repo.brain(UID).projects[0]
    assert (after.name, after.result) == ("Billing on Cloud Run", "-38% monthly infra cost")


# --- The report, for a garden too big to read whole --------------------------------


def test_the_report_searches_only_a_garden_too_big_to_read(repo, setup, monkeypatch):  # noqa: F811
    model = FakeModel()
    _confirm(repo, first_patch(), model)
    session = engine.start(setup, session_id="sess-0001", model=model)
    session = interview._for_report(session, repo, UID)
    assert interview._relevant(session, repo, UID, model) == {}  # it fits: read it whole

    monkeypatch.setattr(interview, "MAX_GARDEN_CHARS", 100)
    relevant = interview._relevant(session, repo, UID, model)
    assert set(relevant) == {q.id for q in session.questions}
    assert all(text.startswith("[") for text in relevant.values())
    assert {c["call"] for c in model.calls} >= {"embed_query"}


def test_ideal_answer_reads_the_index_and_nearest_entries_instead():
    from anyview.interview.models import Question, Setup

    setup = Setup(
        resume="x" * 60,
        company="Initech",
        role="Architect",
        seniority="senior",
        garden="[P1] cut-off garden",
        garden_index="[P1] Billing migration\n[S1] Cutover",
    )
    question = Question(id=2, text="Tell me about a failure.", competency="failure", rationale="r")
    text = ideal_user(question, setup, relevant="[S1] Cutover\n  Result: zero downtime")
    assert "<relevant_entries>\n[S1] Cutover" in text
    assert "<garden_index>\n[P1] Billing migration" in text
    assert "<digital_garden>" not in text  # never point at a block that is not there
    # Without search, the garden rides along whole, as before.
    assert "<digital_garden>\n[P1] cut-off garden" in ideal_user(question, setup)


def test_feedback_is_embedded_with_who_said_it(repo, db):  # noqa: F811
    from anyview.brain.models import FeedbackDraft

    patch = first_patch()
    patch.feedback = [
        FeedbackDraft(
            key="f1",
            project="p1",
            given_by="CTO",
            content="Pushed back on a one-weekend cutover, and was right.",
            evidence="Pushed back on a one-weekend cutover",
        )
    ]
    model = FakeModel()
    _confirm(repo, patch, model)
    assert "feedback" in {r["kind"] for r in _rows(db)}
    [text] = [c["user"] for c in _embeds(model) if c["user"].startswith("Feedback")]
    assert text == (
        "Feedback from CTO — on Billing service to Cloud Run: "
        "Pushed back on a one-weekend cutover, and was right."
    )
