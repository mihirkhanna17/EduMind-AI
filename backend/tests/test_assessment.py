"""Phase 5 verification: quiz generation parsing, deterministic MCQ grading,
LLM short-answer grading (mocked), and confidence/misconception writes."""

import uuid

import pytest
from sqlalchemy import select

import app.services.assessment as svc
from app.db import SessionLocal
from app.models import Concept, LearnerConceptState, User
from app.services.onboarding import seed_concepts_for_user
from app.services.subject_templates import get_template, seed_builtin_templates

QUIZ_JSON = """[
  {"concept": "Arrays", "type": "mcq", "question": "Index of first element?",
   "options": ["0", "1", "-1", "depends"], "correct_index": 0},
  {"concept": "Recursion", "type": "mcq", "question": "What does every recursion need?",
   "options": ["A loop", "A base case", "A pointer", "A stack overflow"], "correct_index": 1},
  {"concept": "Time Complexity", "type": "short_answer",
   "question": "Explain what O(n log n) means.",
   "answer_guide": "growth rate proportional to n times log n; typical of efficient sorts"}
]"""

GRADE_JSON = """{"score": 0.5, "feedback": "Partially right.",
"misconception": "Thinks big-O measures exact runtime rather than growth rate"}"""


async def seeded_user():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"assess-{uuid.uuid4().hex[:10]}@example.com", name="A")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Computer Science")
        await seed_concepts_for_user(db, user.id, template)
        return user.id


@pytest.mark.asyncio
async def test_full_assessment_flow(monkeypatch):
    calls = {"generate": 0, "grade": 0}

    async def fake_call_model(task, messages):
        if task == svc.Task.generate_quiz:
            calls["generate"] += 1
            return QUIZ_JSON
        calls["grade"] += 1
        return GRADE_JSON

    monkeypatch.setattr(svc, "call_model", fake_call_model)
    user_id = await seeded_user()

    async with SessionLocal() as db:
        started = await svc.start_assessment(db, user_id, "Computer Science")
        assert len(started["questions"]) == 3
        # correct answers must never reach the client
        assert all("correct_index" not in q and "answer_guide" not in q for q in started["questions"])

        aid = started["assessment_id"]

        # MCQ correct — deterministic, no model call
        r1 = await svc.grade_answer(db, aid, 0, "0")
        assert r1["score"] == 1.0 and calls["grade"] == 0

        # MCQ wrong, answered by option text
        r2 = await svc.grade_answer(db, aid, 1, "A loop")
        assert r2["score"] == 0.0
        assert "base case" in r2["feedback"]

        # short answer — graded by mocked mid-tier model, detects misconception
        r3 = await svc.grade_answer(db, aid, 2, "it means it runs in n log n seconds")
        assert r3["score"] == 0.5 and calls["grade"] == 1
        assert r3["misconception"] is not None
        assert r3["answered"] == 3 and r3["total"] == 3

        # confidence written: Arrays got EWMA 0.4*1.0 = 0.4
        arrays = await db.scalar(
            select(Concept).where(Concept.user_id == user_id, Concept.name == "Arrays")
        )
        state = await db.get(LearnerConceptState, (user_id, arrays.id))
        assert state.confidence == pytest.approx(0.4)
        assert state.last_reviewed is not None

        # misconception ledger appended on Time Complexity
        tc = await db.scalar(
            select(Concept).where(Concept.user_id == user_id, Concept.name == "Time Complexity")
        )
        tc_state = await db.get(LearnerConceptState, (user_id, tc.id))
        assert len(tc_state.misconceptions) == 1
        assert tc_state.misconceptions[0]["resolved"] is False


@pytest.mark.asyncio
async def test_start_without_onboarding_fails():
    async with SessionLocal() as db:
        with pytest.raises(ValueError, match="onboard first"):
            await svc.start_assessment(db, 999999, "Computer Science")


def test_extract_json_value_variants():
    assert svc._extract_json_value('[{"a": 1}]') == [{"a": 1}]
    assert svc._extract_json_value('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        svc._extract_json_value("nope")
