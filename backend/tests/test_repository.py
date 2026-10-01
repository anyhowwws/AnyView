# ruff: noqa: E501 — fixture data reads better unwrapped.
"""The repository against a real Postgres: the write path, the read path, and
the property that makes the event log the source of truth — a rebuilt
projection is identical to the incrementally maintained one."""

import datetime as dt

import pytest
import sqlalchemy as sa

from anyview.brain.models import (
    AchievementDraft,
    FeedbackDraft,
    Patch,
    ProjectDraft,
    RoleDraft,
    SkillDraft,
    StoryDraft,
)
from anyview.db.repository import ERASE_ORDER, Conflict, NotFound, Repository, _apply_patch

UID = "uid-jordan"


@pytest.fixture
def repo(db):
    r = Repository(db)
    r.ensure_user(UID, "jordan@example.com")
    r.ensure_user("uid-other", "other@example.com")
    return r


def first_patch() -> Patch:
    return Patch(
        roles=[
            RoleDraft(
                key="r1",
                company="Acme Corp",
                title="Senior Cloud Architect",
                start_date=dt.date(2021, 3, 1),
                level="senior",
                evidence="Acme Corp (2021–present)",
            )  # fmt: skip
        ],
        projects=[
            ProjectDraft(
                key="p1",
                role="r1",
                name="Billing service to Cloud Run",
                problem="VM fleet was expensive",
                action="Led the migration",
                result="-38% monthly infra cost",
                tech=["Cloud Run", "Terraform"],
                metrics=["-38% cost"],
                evidence="Led migration of the billing service",
            )  # fmt: skip
        ],
        stories=[
            StoryDraft(
                key="s1",
                role="r1",
                project="p1",
                title="Cutting over billing without downtime",
                situation="Billing on VMs",
                task="Move it",
                action="Rehearsed cutovers",
                result="Zero downtime, cost -38%",
                competencies=["ownership", "delivery"],
                evidence="cutting monthly infra cost 38%",
            )  # fmt: skip
        ],
        skills=[
            SkillDraft(
                key="k1",
                name="Terraform",
                depth=4,
                projects=["p1"],
                evidence="Terraform module library",
            )
        ],
        achievements=[
            AchievementDraft(
                key="a1",
                kind="credential",
                title="GCP Professional Cloud Architect",
                issuer="Google",
                evidence="certified",
            )
        ],
    )


def _confirm(repo: Repository, patch: Patch, text="dump text"):
    dump = repo.create_dump(UID, kind="text", text=text, object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=patch, model="fake")
    return repo.confirm_proposal(UID, prop.id, patch)


def _snapshot(db, uid=UID) -> dict:
    """Every projection row for a user, as plain data, for equality checks."""
    out = {}
    with db.begin() as c:
        for t in ("roles", "projects", "stories", "skills", "achievements"):
            rows = (
                c.execute(sa.text(f"SELECT * FROM {t} WHERE user_id = :u ORDER BY id"), {"u": uid})
                .mappings()
                .all()
            )
            out[t] = [dict(r) for r in rows]
        out["skill_roles"] = sorted(
            tuple(map(str, r))
            for r in c.execute(
                sa.text(
                    "SELECT l.skill_id, l.role_id FROM skill_roles l JOIN skills s ON s.id = l.skill_id WHERE s.user_id = :u"
                ),
                {"u": uid},
            ).all()
        )
        out["skill_achievements"] = sorted(
            tuple(map(str, r))
            for r in c.execute(
                sa.text(
                    "SELECT l.skill_id, l.achievement_id FROM skill_achievements l JOIN skills s ON s.id = l.skill_id WHERE s.user_id = :u"
                ),
                {"u": uid},
            ).all()
        )
        out["skill_evidence"] = sorted(
            tuple(map(str, r))
            for r in c.execute(
                sa.text(
                    "SELECT e.skill_id, e.project_id FROM skill_evidence e JOIN skills s ON s.id = e.skill_id WHERE s.user_id = :u"
                ),
                {"u": uid},
            ).all()
        )
    return out


# --- write path ------------------------------------------------------------------


def test_confirm_writes_one_event_and_the_projection(repo):
    event = _confirm(repo, first_patch())
    assert event.kind == "patch_confirmed" and event.seq == 1
    brain = repo.brain(UID)
    assert [r.company for r in brain.roles] == ["Acme Corp"]
    assert brain.projects[0].role_id == brain.roles[0].id
    assert brain.stories[0].project_id == brain.projects[0].id
    assert brain.skills[0].project_ids == [brain.projects[0].id]
    assert brain.achievements[0].kind == "credential"
    assert brain.pending_proposals == 0
    # provenance: every entity points at the dump and the event
    for e in (*brain.roles, *brain.projects, *brain.stories, *brain.skills, *brain.achievements):
        assert e.source.raw_dump_id == event.raw_dump_id and e.source.event_id == event.id


def test_labels_are_stable_handles(repo):
    _confirm(repo, first_patch())
    index, labels = repo.brain_index(UID)
    assert set(labels) == {"R1", "P1", "S1", "K1", "A1"}
    assert "[R1] Acme Corp — Senior Cloud Architect (2021-03 → now)" in index
    assert (
        "[S1] (ownership, delivery) Cutting over billing without downtime → Zero downtime" in index
    )


def test_second_dump_can_update_an_existing_entity_by_label(repo):
    _confirm(repo, first_patch())
    update = Patch(
        roles=[
            RoleDraft(
                key="r1",
                existing="R1",
                company="Acme Corp",
                title="Principal Cloud Architect",
                evidence="promoted",
            )
        ],
        stories=[
            StoryDraft(
                key="s1",
                role="R1",
                title="Rota redesign",
                result="MTTR 4h → 50m",
                competencies=["failure"],
                evidence="MTTR",
            )
        ],
    )
    event = _confirm(repo, update, text="second dump")
    brain = repo.brain(UID)
    assert len(brain.roles) == 1 and brain.roles[0].title == "Principal Cloud Architect"
    assert brain.roles[0].source.raw_dump_id == event.raw_dump_id  # the latest dump that touched it
    assert [s.title for s in brain.stories] == [
        "Cutting over billing without downtime",
        "Rota redesign",
    ]
    assert brain.stories[1].role_id == brain.roles[0].id


def test_bad_references_are_conflicts_not_partial_writes(repo):
    _confirm(repo, first_patch())
    bad = Patch(stories=[StoryDraft(key="s9", role="R7", title="x", evidence="e")])
    dump = repo.create_dump(UID, kind="text", text="t", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=bad, model="fake")
    with pytest.raises(Conflict):
        repo.confirm_proposal(UID, prop.id, bad)
    assert repo.proposal(UID, prop.id).status == "pending"  # untouched
    assert len(repo.events(UID)) == 1


def test_proposal_cannot_be_confirmed_twice(repo):
    patch = first_patch()
    dump = repo.create_dump(UID, kind="text", text="t", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=patch, model="fake")
    repo.confirm_proposal(UID, prop.id, patch)
    with pytest.raises(Conflict):
        repo.confirm_proposal(UID, prop.id, patch)
    with pytest.raises(NotFound):
        repo.discard_proposal(UID, prop.id)


def test_discard_leaves_no_event(repo):
    dump = repo.create_dump(UID, kind="text", text="t", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=first_patch(), model="fake")
    assert repo.brain(UID).pending_proposals == 1
    repo.discard_proposal(UID, prop.id)
    assert repo.brain(UID).pending_proposals == 0
    assert repo.events(UID) == []


def test_edit_and_retire_append_events(repo):
    _confirm(repo, first_patch())
    story = repo.brain(UID).stories[0]
    repo.edit_entity(UID, "story", story.id, {"result": "Zero downtime; cost down 38%; 2 quarters"})
    with pytest.raises(Conflict):
        repo.edit_entity(UID, "story", story.id, {"user_id": "uid-other"})  # not editable
    repo.retire_entity(UID, "achievement", repo.brain(UID).achievements[0].id)
    brain = repo.brain(UID)
    assert brain.stories[0].result.startswith("Zero downtime; cost down 38%")
    assert brain.achievements == []
    assert [e.kind for e in repo.events(UID)] == [
        "patch_confirmed",
        "entity_edited",
        "entity_retired",
    ]
    with pytest.raises(NotFound):  # retired is gone for edits too
        repo.edit_entity(UID, "achievement", repo.events(UID)[-1].payload["id"], {"title": "x"})


def test_rebuild_reproduces_the_projection_exactly(repo, db):
    _confirm(repo, first_patch())
    _confirm(
        repo,
        Patch(
            stories=[
                StoryDraft(
                    key="s1",
                    role="R1",
                    title="Rota redesign",
                    competencies=["failure"],
                    evidence="e",
                )
            ]
        ),
        text="two",
    )
    brain = repo.brain(UID)
    repo.edit_entity(UID, "skill", brain.skills[0].id, {"depth": 5, "project_ids": []})
    repo.retire_entity(UID, "story", brain.stories[0].id)
    repo.edit_entity(UID, "role", brain.roles[0].id, {"end_date": dt.date(2026, 1, 31)})

    before = _snapshot(db)
    assert repo.rebuild(UID) == 5
    assert _snapshot(db) == before
    # rebuild of one user leaves another user's rows alone
    other = Repository(db)
    other_dump = other.create_dump("uid-other", kind="text", text="t", object_name=None)
    p = other.create_proposal("uid-other", dump_id=other_dump.id, patch=first_patch(), model="fake")
    other.confirm_proposal("uid-other", p.id, first_patch())
    other_before = _snapshot(db, "uid-other")
    repo.rebuild(UID)
    assert _snapshot(db, "uid-other") == other_before


def test_users_cannot_see_each_others_brains(repo):
    _confirm(repo, first_patch())
    other = repo.brain("uid-other")
    assert other.roles == [] and other.pending_proposals == 0
    with pytest.raises(NotFound):
        repo.dump("uid-other", repo.events(UID)[0].raw_dump_id)
    with pytest.raises(NotFound):
        repo.retire_entity("uid-other", "role", repo.brain(UID).roles[0].id)


# --- reads --------------------------------------------------------------------------


def test_coverage_marks_strong_weak_none(repo):
    _confirm(repo, first_patch())  # story with a result → strong for ownership, delivery at R1
    _confirm(
        repo,
        Patch(
            stories=[
                StoryDraft(
                    key="s1", role="R1", title="Vague", competencies=["conflict"], evidence="e"
                )
            ]
        ),
        text="two",
    )  # no result → weak
    cov = repo.brain(UID).coverage
    rid = cov.roles[0].id
    assert cov.cells["ownership"][rid] == "strong"
    assert cov.cells["conflict"][rid] == "weak"
    assert cov.cells["ambiguity"][rid] == "none"
    assert [c.key for c in cov.competencies][:3] == ["ownership", "ambiguity", "conflict"]


def test_stories_for_competency_and_brain_context(repo):
    _confirm(repo, first_patch())
    assert [s.title for s in repo.stories_for_competency(UID, "delivery")] == [
        "Cutting over billing without downtime"
    ]
    assert repo.stories_for_competency(UID, "failure") == []
    ctx = repo.brain_context(UID)
    assert ctx.startswith("## [R1] Senior Cloud Architect at Acme Corp (2021-03 → now)")
    assert "[P1] Billing service to Cloud Run" in ctx and "Result: -38% monthly infra cost" in ctx
    assert "[S1] Cutting over billing without downtime (competencies: ownership, delivery)" in ctx
    assert "[K1] Terraform — self-rated 4/5" in ctx


def test_usage_rows(repo):
    rec = {"session_id": "s1", "call": "plan", "model": "m", "input_tokens": 10, "output_tokens": 20,
           "thinking_tokens": 5, "cache_read": 0, "latency_ms": 100}  # fmt: skip
    repo.write_usage(rec, uid=UID)
    repo.write_usage({**rec, "call": "ask"}, uid=None)
    assert repo.usage_for_session("s1") == {
        "calls": 2,
        "input_tokens": 20,
        "output_tokens": 40,
        "thinking_tokens": 10,
    }


# --- The resume on file (ADR 0014) and the no-op check (ADR 0015) -----------


def test_the_resume_on_file_is_a_pointer_not_the_latest_dump(repo):
    """Adding a second resume to the garden as raw material must not silently
    change what interviewers see."""
    assert repo.active_resume(UID) is None
    first = repo.create_dump(UID, kind="resume_pdf", text="first resume" * 5, object_name="a.pdf")
    repo.set_active_resume(UID, first.id)
    repo.create_dump(UID, kind="resume_docx", text="an older CV" * 5, object_name="b.docx")
    assert repo.active_resume(UID).id == first.id


def test_a_dump_that_is_not_yours_cannot_become_your_resume(repo):
    theirs = repo.create_dump("uid-other", kind="resume_pdf", text="not mine" * 8, object_name=None)
    with pytest.raises(NotFound):
        repo.set_active_resume(UID, theirs.id)
    assert repo.active_resume(UID) is None


def test_identical_text_is_found_again_and_stays_scoped_to_its_owner(repo):
    text = "Jordan Lee — Cloud Solutions Architect. Acme Corp, 2021 to present."
    mine = repo.create_dump(UID, kind="resume_pdf", text=text, object_name="a.pdf")
    repo.create_dump("uid-other", kind="resume_pdf", text=text, object_name="b.pdf")

    assert repo.dump_with_text(UID, text).id == mine.id
    assert repo.dump_with_text(UID, text + " One more line.") is None
    assert repo.dump_with_text("uid-third", text) is None


# --- Feedback (ADR: a Digital Garden entity kind, complementing stories) ----


def test_feedback_confirms_edits_retires_and_rebuilds(repo, db):
    patch = Patch(
        roles=[
            RoleDraft(
                key="r1",
                company="Acme Corp",
                title="Senior Cloud Architect",
                evidence="Acme Corp",
            )
        ],
        feedback=[
            FeedbackDraft(
                key="f1",
                role="r1",
                given_by="Manager, 2024 review",
                content="Owned the migration end to end.",
                received_on=dt.date(2024, 11, 1),
                evidence="Owned the migration end to end.",
            )
        ],
    )
    event = _confirm(repo, patch)
    brain = repo.brain(UID)
    assert brain.feedback[0].given_by == "Manager, 2024 review"
    assert brain.feedback[0].role_id == brain.roles[0].id
    assert brain.feedback[0].source.event_id == event.id

    repo.edit_entity(UID, "feedback", brain.feedback[0].id, {"content": "Edited quote"})
    assert repo.brain(UID).feedback[0].content == "Edited quote"

    with pytest.raises(Conflict):  # not editable
        repo.edit_entity(UID, "feedback", brain.feedback[0].id, {"user_id": "uid-other"})

    before = _snapshot(db)
    before["feedback"] = _rows(db, "feedback")
    assert repo.rebuild(UID) == 2
    after = _snapshot(db)
    after["feedback"] = _rows(db, "feedback")
    assert after == before

    repo.retire_entity(UID, "feedback", brain.feedback[0].id)
    assert repo.brain(UID).feedback == []


def _rows(db, table: str) -> list[dict]:
    with db.begin() as c:
        return [
            dict(r)
            for r in c.execute(
                sa.text(f"SELECT * FROM {table} WHERE user_id = :u ORDER BY id"), {"u": UID}
            )
            .mappings()
            .all()
        ]


def test_feedback_appears_in_the_index_and_the_context(repo):
    _confirm(
        repo,
        Patch(
            roles=[
                RoleDraft(
                    key="r1", company="Acme Corp", title="Senior Cloud Architect", evidence="e"
                )
            ],
            projects=[ProjectDraft(key="p1", role="r1", name="Billing migration", evidence="e")],
            feedback=[
                FeedbackDraft(
                    key="f1",
                    project="p1",
                    given_by="Client",
                    content="Extremely responsive and clear throughout.",
                    evidence="e",
                )
            ],
        ),
    )
    index, labels = repo.brain_index(UID)
    assert "F1" in labels
    assert "[F1] feedback from Client: Extremely responsive" in index

    ctx = repo.brain_context(UID)
    assert "## Feedback" in ctx
    assert "[F1] Client — on Billing migration: Extremely responsive and clear throughout." in ctx


# --- Erasing an account (ADR 0018) ----------------------------------------------


def _count(db, table: str, uid: str) -> int:
    column = "uid" if table == "users" else "user_id"
    with db.begin() as c:
        return c.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {column} = :u"), {"u": uid}
        ).scalar_one()


def _fill(repo: Repository, uid: str) -> None:
    """A garden with every kind of row: confirmed entities, an edit, a retire,
    a pending proposal, a resume on file, a usage row."""
    dump = repo.create_dump(uid, kind="resume_pdf", text="resume text " * 5, object_name="r.pdf")
    prop = repo.create_proposal(uid, dump_id=dump.id, patch=first_patch(), model="fake")
    repo.confirm_proposal(uid, prop.id, first_patch())
    repo.set_active_resume(uid, dump.id)
    brain = repo.brain(uid)
    repo.edit_entity(uid, "role", brain.roles[0].id, {"level": "principal"})
    repo.retire_entity(uid, "skill", brain.skills[0].id)
    pending = repo.create_dump(uid, kind="text", text="another dump " * 5, object_name=None)
    repo.create_proposal(uid, dump_id=pending.id, patch=first_patch(), model="fake")
    repo.write_usage(
        {"session_id": f"s-{uid}", "call": "plan", "model": "m", "input_tokens": 1,
         "output_tokens": 1, "thinking_tokens": 0, "cache_read": 0, "latency_ms": 1},
        uid=uid,
    )  # fmt: skip


def test_erase_user_removes_every_row_and_only_theirs(repo, db):
    _fill(repo, UID)
    _fill(repo, "uid-other")
    before = {t: _count(db, t, "uid-other") for t in ERASE_ORDER}

    removed = repo.erase_user(UID)

    assert all(_count(db, t, UID) == 0 for t in ERASE_ORDER)
    assert removed["events"] == 3 and removed["users"] == 1 and removed["raw_dumps"] == 2
    assert {t: _count(db, t, "uid-other") for t in ERASE_ORDER} == before
    assert repo.rebuild("uid-other") > 0  # the other user's log is intact and replays


def test_erase_is_safe_to_repeat_and_the_user_can_start_again(repo):
    _fill(repo, UID)
    repo.erase_user(UID)
    assert sum(repo.erase_user(UID).values()) == 0
    repo.ensure_user(UID, "jordan@example.com")
    assert repo.brain(UID).roles == [] and repo.active_resume(UID) is None
    _confirm(repo, first_patch())  # labels and seq start again from 1
    assert repo.events(UID)[0].seq == 1


def test_erase_order_covers_every_table_that_holds_a_user(db):
    """A table added later with a user_id column must be erased too."""
    with db.begin() as c:
        tables = {
            r[0]
            for r in c.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'user_id'"
                )
            )
        }
    assert tables | {"users"} == set(ERASE_ORDER)


# --- Responsibilities and skill → role links (ADR 0019) ---------------------------


def _with_responsibilities() -> Patch:
    patch = first_patch()
    patch.roles[0].responsibilities = ["EKS day-2 operations", "RFQ and pre-sales support"]
    patch.skills[0].roles = ["r1"]
    patch.skills[0].link_evidence = {"r1": "a quote shown in the queue, never stored"}
    return patch


def test_roles_carry_responsibilities_and_skills_link_to_roles(repo):
    _confirm(repo, _with_responsibilities())
    brain = repo.brain(UID)
    assert brain.roles[0].responsibilities == ["EKS day-2 operations", "RFQ and pre-sales support"]
    assert brain.skills[0].role_ids == [brain.roles[0].id]
    assert brain.skills[0].project_ids == [brain.projects[0].id]
    context = repo.brain_context(UID)
    assert "Responsibilities:\n  - EKS day-2 operations" in context
    assert "[K1] Terraform — self-rated 4/5 — used in P1, R1" in context


def test_role_links_and_responsibilities_are_editable_and_replay(repo, db):
    _confirm(repo, _with_responsibilities())
    brain = repo.brain(UID)
    repo.edit_entity(UID, "role", brain.roles[0].id, {"responsibilities": ["Landing zones"]})
    repo.edit_entity(UID, "skill", brain.skills[0].id, {"role_ids": []})
    brain = repo.brain(UID)
    assert brain.roles[0].responsibilities == ["Landing zones"]
    assert brain.skills[0].role_ids == [] and brain.skills[0].project_ids != []
    before = _snapshot(db)
    repo.rebuild(UID)
    assert _snapshot(db) == before


def test_events_from_before_migration_006_still_replay(repo, db):
    """A patch_confirmed payload written before ADR 0019 has no
    `responsibilities` on roles and no `role_ids` on skills."""
    _confirm(repo, first_patch())
    with db.begin() as c:
        (payload,) = c.execute(
            sa.text("SELECT payload FROM events WHERE user_id = :u"), {"u": UID}
        ).one()
    del payload["roles"][0]["responsibilities"]
    del payload["skills"][0]["role_ids"]
    # Re-apply the old-shaped payload over the projection, as a replay would.
    with db.begin() as c:
        c.execute(sa.text("DELETE FROM skills WHERE user_id = :u"), {"u": UID})
        event_id = c.execute(
            sa.text("SELECT id FROM events WHERE user_id = :u"), {"u": UID}
        ).scalar()
        _apply_patch(c, UID, event_id, payload)
    brain = repo.brain(UID)
    assert brain.roles[0].responsibilities == [] and brain.skills[0].role_ids == []


def test_a_name_clash_is_a_conflict_and_writes_nothing(repo):
    _confirm(repo, first_patch())
    clash = Patch(skills=[SkillDraft(key="k1", name="TERRAFORM", depth=2, evidence="e")])
    dump = repo.create_dump(UID, kind="text", text="t", object_name=None)
    prop = repo.create_proposal(UID, dump_id=dump.id, patch=clash, model="fake")
    with pytest.raises(Conflict, match="already has an entry"):
        repo.confirm_proposal(UID, prop.id, clash)
    assert len(repo.events(UID)) == 1 and repo.proposal(UID, prop.id).status == "pending"


def test_a_certification_evidences_a_skill_and_replays(repo, db):
    patch = first_patch()
    patch.skills[0].achievements = ["a1"]
    _confirm(repo, patch)
    brain = repo.brain(UID)
    assert brain.skills[0].achievement_ids == [brain.achievements[0].id]
    assert "— certified by A1" in repo.brain_context(UID)
    repo.edit_entity(UID, "skill", brain.skills[0].id, {"achievement_ids": []})
    assert repo.brain(UID).skills[0].achievement_ids == []
    before = _snapshot(db)
    repo.rebuild(UID)
    assert _snapshot(db) == before


def test_origin_tells_a_resume_from_an_uploaded_file(repo):
    resume = repo.create_dump(UID, kind="resume_pdf", text="cv", object_name="uploads/x/cv.pdf")
    p = repo.create_proposal(UID, dump_id=resume.id, patch=first_patch(), model="fake")
    repo.confirm_proposal(UID, p.id, first_patch())
    diagram = repo.create_dump(UID, kind="text", text="diagram", object_name="uploads/x/d.png")
    patch = Patch(achievements=[AchievementDraft(key="a1", title="PCA", evidence="PCA 2024")])
    p = repo.create_proposal(UID, dump_id=diagram.id, patch=patch, model="fake")
    repo.confirm_proposal(UID, p.id, patch)
    b = repo.brain(UID)
    assert b.roles[0].source.origin == "resume"
    assert b.roles[0].source.evidence == "Acme Corp (2021–present)"
    assert b.achievements[-1].source.origin == "file"
    assert b.achievements[-1].source.evidence == "PCA 2024"
