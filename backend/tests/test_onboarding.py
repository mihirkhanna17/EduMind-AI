"""Phase 4 verification. Template + seeding tests run against the live dev
Postgres (docker compose); dynamic-agent tests mock the model call."""

import uuid

import pytest
from sqlalchemy import select

import app.services.onboarding as onboarding_svc
from app.db import SessionLocal
from app.models import Concept, LearnerConceptState, SubjectTemplate, User
from app.schemas import SubjectTemplateData
from app.services.onboarding import (
    _extract_json,
    generate_dynamic_template,
    get_or_create_template,
    seed_concepts_for_user,
)
from app.services.subject_templates import get_template, seed_builtin_templates

DYNAMIC_JSON = """```json
{
  "subject": "Music Theory",
  "starter_concepts": [
    {"name": "Notes & Pitch", "parent": null, "prerequisites": []},
    {"name": "Scales", "parent": null, "prerequisites": ["Notes & Pitch"]},
    {"name": "Chords", "parent": null, "prerequisites": ["Scales"]}
  ],
  "onboarding_questions": [
    {"key": "instrument", "text": "Do you play an instrument?", "type": "single_select",
     "options": ["No", "Piano", "Guitar", "Other"]}
  ]
}
```"""


async def make_user(db) -> User:
    user = User(email=f"test-{uuid.uuid4().hex[:10]}@example.com", name="Test")
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_builtin_templates_seed_idempotently():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        await seed_builtin_templates(db)  # second run must not duplicate
        rows = (
            await db.scalars(
                select(SubjectTemplate).where(
                    SubjectTemplate.subject.in_(["Computer Science", "Physics"])
                )
            )
        ).all()
        assert len(rows) == 2
        cs = await get_template(db, "computer science")  # case-insensitive
        assert cs is not None
        assert len(cs.starter_concepts) == 10
        assert len(cs.onboarding_questions) == 5


@pytest.mark.asyncio
async def test_seed_concepts_resolves_names_and_creates_state():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = await make_user(db)
        template = await get_template(db, "Computer Science")

        concepts = await seed_concepts_for_user(db, user.id, template)
        assert len(concepts) == 10

        by_name = {c.name: c for c in concepts}
        dp = by_name["Dynamic Programming"]
        assert set(dp.prerequisites) == {by_name["Recursion"].id, by_name["Arrays"].id}

        states = (
            await db.scalars(
                select(LearnerConceptState).where(LearnerConceptState.user_id == user.id)
            )
        ).all()
        assert len(states) == 10
        assert all(s.confidence == 0.0 for s in states)

        # idempotent: re-running must not duplicate
        again = await seed_concepts_for_user(db, user.id, template)
        assert len(again) == 10
        total = (
            await db.scalars(select(Concept).where(Concept.user_id == user.id))
        ).all()
        assert len(total) == 10


def test_extract_json_handles_fences_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('Sure! Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        _extract_json("no json here")


@pytest.mark.asyncio
async def test_dynamic_template_parses_model_output(monkeypatch):
    async def fake_call_model(task, messages):
        return DYNAMIC_JSON

    monkeypatch.setattr(onboarding_svc, "call_model", fake_call_model)
    template = await generate_dynamic_template("Music Theory")
    assert isinstance(template, SubjectTemplateData)
    assert [c.name for c in template.starter_concepts] == ["Notes & Pitch", "Scales", "Chords"]


@pytest.mark.asyncio
async def test_dynamic_template_persisted_so_second_student_is_free(monkeypatch):
    calls = {"n": 0}

    async def fake_call_model(task, messages):
        calls["n"] += 1
        return DYNAMIC_JSON.replace("Music Theory", subject)

    subject = f"Underwater Basket Weaving {uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(onboarding_svc, "call_model", fake_call_model)

    async with SessionLocal() as db:
        try:
            first = await get_or_create_template(db, subject)
            second = await get_or_create_template(db, subject)
        finally:
            row = await db.scalar(
                select(SubjectTemplate).where(SubjectTemplate.subject == subject)
            )
            if row is not None:
                await db.delete(row)
                await db.commit()

    assert calls["n"] == 1  # generated once, served from DB after
    assert first.subject == second.subject == subject
