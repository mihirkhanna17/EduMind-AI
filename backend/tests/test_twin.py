"""Phase 11 verification: snapshot versioning, one batched call, diff logic,
resilience when the summarize call fails."""

import json
import uuid

import pytest

import app.services.twin as twin_svc
from app.db import SessionLocal
from app.models import LearnerConceptState, Session, TwinSnapshot, User
from app.services.onboarding import seed_concepts_for_user
from app.services.subject_templates import get_template, seed_builtin_templates
from app.services.twin import build_snapshot, diff_snapshots

SUMMARY_JSON = json.dumps(
    {
        "cognitive_profile": {
            "observed_style": "intuition-first, examples help",
            "pacing": "steady",
            "strengths": ["arrays"],
            "gaps": ["recursion depth"],
        },
        "behavioral_profile": {
            "engagement": "high",
            "question_asking": "asks branch questions often",
            "recommendations": ["review recursion tomorrow"],
        },
    }
)


async def setup_user():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"twin-{uuid.uuid4().hex[:10]}@example.com", name="T")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Computer Science")
        concepts = await seed_concepts_for_user(db, user.id, template)
        session = Session(user_id=user.id)
        db.add(session)
        await db.commit()
        return user.id, session.id, concepts


@pytest.mark.asyncio
async def test_snapshot_versions_and_single_batched_call(monkeypatch):
    calls = {"n": 0}

    async def fake_call_model(task, messages):
        calls["n"] += 1
        assert task == twin_svc.Task.twin_summarize
        return SUMMARY_JSON

    monkeypatch.setattr(twin_svc, "call_model", fake_call_model)
    user_id, session_id, concepts = await setup_user()

    async with SessionLocal() as db:
        s1 = await build_snapshot(db, user_id, session_id)
        s2 = await build_snapshot(db, user_id, session_id)

    assert (s1.version, s2.version) == (1, 2)
    assert calls["n"] == 2  # exactly one call per snapshot — batched, not per-turn
    assert s1.cognitive_profile["observed_style"].startswith("intuition")
    assert len(s1.knowledge_state) == 10
    assert s1.behavioral_profile["last_session_activity"]["session_id"] == session_id


@pytest.mark.asyncio
async def test_failed_summary_still_snapshots_knowledge(monkeypatch):
    async def broken_call_model(task, messages):
        raise RuntimeError("poe down")

    monkeypatch.setattr(twin_svc, "call_model", broken_call_model)
    user_id, session_id, _ = await setup_user()

    async with SessionLocal() as db:
        s = await build_snapshot(db, user_id, session_id)

    assert s.version == 1
    assert len(s.knowledge_state) == 10  # knowledge never lost
    assert "summary unavailable" in s.behavioral_profile["engagement"]


@pytest.mark.asyncio
async def test_diff_detects_improvement_and_misconception_changes(monkeypatch):
    async def fake_call_model(task, messages):
        return SUMMARY_JSON

    monkeypatch.setattr(twin_svc, "call_model", fake_call_model)
    user_id, session_id, concepts = await setup_user()

    async with SessionLocal() as db:
        s1 = await build_snapshot(db, user_id, session_id)

        # learner improves on Arrays, develops a misconception on Trees
        arrays = next(c for c in concepts if c.name == "Arrays")
        trees = next(c for c in concepts if c.name == "Trees")
        st_a = await db.get(LearnerConceptState, (user_id, arrays.id))
        st_a.mastery, st_a.confidence = 0.7, 0.8
        st_t = await db.get(LearnerConceptState, (user_id, trees.id))
        st_t.misconceptions = [{"text": "thinks BST insert is O(1)", "resolved": False}]
        await db.commit()

        s2 = await build_snapshot(db, user_id, session_id)

    d = diff_snapshots(s1, s2)
    assert d["from_version"] == 1 and d["to_version"] == 2
    improved = [c for c in d["concept_changes"] if c["kind"] == "improved"]
    assert any(c["concept"] == "Arrays" and c["mastery_delta"] == 0.7 for c in improved)
    assert d["new_misconceptions"] == [{"concept": "Trees", "text": "thinks BST insert is O(1)"}]
    assert d["resolved_misconceptions"] == []
