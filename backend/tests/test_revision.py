"""Phase 8 verification: SM-2 easiness math, interval bands, due queries."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import SessionLocal
from app.models import LearnerConceptState, User
from app.services.onboarding import seed_concepts_for_user
from app.services.revision import (
    MIN_EASINESS,
    due_concepts,
    next_due_at,
    record_review,
    review_interval_days,
    updated_easiness,
)
from app.services.subject_templates import get_template, seed_builtin_templates


def test_easiness_update_matches_sm2():
    # perfect recall (q=5): +0.1
    assert updated_easiness(2.5, 1.0) == 2.6
    # q=3 ("correct with difficulty"): EF −0.14
    assert updated_easiness(2.5, 0.6) == pytest.approx(2.36)
    # total blackout (q=0) floors at 1.3 eventually
    e = 2.5
    for _ in range(10):
        e = updated_easiness(e, 0.0)
    assert e == MIN_EASINESS


def test_interval_bands():
    assert review_interval_days(0.1, 2.5) == 1     # shaky → tomorrow
    assert review_interval_days(0.5, 2.5) == 3     # developing → 3 days
    assert review_interval_days(0.9, 2.5) == 15    # solid → 6 × EF
    assert review_interval_days(0.9, 1.3) == 8


def test_never_reviewed_is_new_not_due():
    state = LearnerConceptState(user_id=1, concept_id=1, mastery=0.0, retention_score=2.5)
    state.last_reviewed = None
    assert next_due_at(state) is None


def test_record_review_moves_all_three_signals():
    state = LearnerConceptState(
        user_id=1, concept_id=1, mastery=0.5, retention_score=2.5, last_reviewed=None
    )
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    record_review(state, 1.0, now=now)
    assert state.retention_score == 2.6
    assert state.mastery == pytest.approx(0.65)
    assert state.last_reviewed == now
    # mastery 0.65 ≥ 0.6 → interval = max(6, round(6 × 2.6)) = 16 days
    assert next_due_at(state) == now + timedelta(days=16)


@pytest.mark.asyncio
async def test_due_query_returns_only_lapsed_sorted():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"rev-{uuid.uuid4().hex[:10]}@example.com", name="R")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Physics")
        concepts = await seed_concepts_for_user(db, user.id, template)

        now = datetime.now(timezone.utc)
        # concept A: reviewed 10 days ago, shaky (interval 1) → 9 days overdue
        a = await db.get(LearnerConceptState, (user.id, concepts[0].id))
        a.mastery, a.retention_score, a.last_reviewed = 0.1, 2.5, now - timedelta(days=10)
        # concept B: reviewed 5 days ago, developing (interval 3) → 2 days overdue
        b = await db.get(LearnerConceptState, (user.id, concepts[1].id))
        b.mastery, b.retention_score, b.last_reviewed = 0.5, 2.5, now - timedelta(days=5)
        # concept C: reviewed today, not due
        c = await db.get(LearnerConceptState, (user.id, concepts[2].id))
        c.mastery, c.retention_score, c.last_reviewed = 0.5, 2.5, now
        await db.commit()

        due = await due_concepts(db, user.id, now=now)

    assert [d["concept_id"] for d in due] == [concepts[0].id, concepts[1].id]
    assert due[0]["overdue_days"] == pytest.approx(9.0, abs=0.1)
