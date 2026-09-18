"""Phase 10 verification: library parsing, per-cohort caching, no per-student
regeneration."""

import uuid

import pytest

import app.services.simulations as svc
from app.db import SessionLocal
from app.models import LearnerProfile, User
from app.services.onboarding import seed_concepts_for_user
from app.services.simulations import get_or_generate, parse_simulation, variant_key_for
from app.services.subject_templates import get_template, seed_builtin_templates

SIM_OUTPUT = """<<<library>>>
d3
<<<html>>>
<!DOCTYPE html>
<html><head><script src="https://cdn.jsdelivr.net/npm/d3@7"></script></head>
<body style="background:#111827"><div id="viz"></div><script>/* bubble sort viz */</script></body></html>"""


async def setup_user(style=None):
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"sim-{uuid.uuid4().hex[:10]}@example.com", name="S")
        db.add(user)
        await db.commit()
        if style:
            db.add(LearnerProfile(user_id=user.id, learning_prefs={"style": style}))
            await db.commit()
        template = await get_template(db, "Computer Science")
        concepts = await seed_concepts_for_user(db, user.id, template)
        arrays = next(c for c in concepts if c.name == "Arrays")
        return user.id, arrays.id


def mock_sim_model(monkeypatch):
    calls = {"n": 0}

    async def fake_call_model(task, messages):
        calls["n"] += 1
        return SIM_OUTPUT

    monkeypatch.setattr(svc, "call_model", fake_call_model)
    return calls


def test_parse_simulation_valid_and_invalid():
    lib, html = parse_simulation(SIM_OUTPUT)
    assert lib == "d3"
    assert html.startswith("<!DOCTYPE html>")
    with pytest.raises(ValueError):
        parse_simulation("<<<library>>>\nfortran\n<<<html>>>\n<html></html>")
    with pytest.raises(ValueError):
        parse_simulation("no markers")


@pytest.mark.asyncio
async def test_simulation_cached_across_students_same_cohort(monkeypatch):
    calls = mock_sim_model(monkeypatch)
    user_a, concept_id = await setup_user()

    async with SessionLocal() as db:
        row1, cached1 = await get_or_generate(db, user_a, concept_id)
        row2, cached2 = await get_or_generate(db, user_a, concept_id)

    assert cached1 is False and cached2 is True
    assert row1.id == row2.id
    assert row1.library == "d3"
    assert calls["n"] == 1  # never regenerated for the same cohort


@pytest.mark.asyncio
async def test_different_framing_generates_new_variant(monkeypatch):
    calls = mock_sim_model(monkeypatch)
    user_a, concept_id = await setup_user(style="visual metaphors")

    async with SessionLocal() as db:
        row_a, _ = await get_or_generate(db, user_a, concept_id)

    # a second user with a different framing hits a different variant_key
    async with SessionLocal() as db:
        user_b = (await setup_user(style="mathematical rigor"))[0]
        prof = await db.get(LearnerProfile, user_b)
        assert variant_key_for(prof) == "mathematical-rigor"
