"""Phase 6 verification: pedagogical block generation (mocked model),
lesson storage, response-cache cohort behavior, chunking + retrieval."""

import json
import uuid

import pytest
from sqlalchemy import select

import app.services.teaching as teaching
from app.db import SessionLocal
from app.models import LessonBlock, Session, User
from app.services.documents import chunk_text
from app.services.onboarding import seed_concepts_for_user
from app.services.response_cache import cache
from app.services.subject_templates import get_template, seed_builtin_templates
from app.services.teaching import (
    BLOCK_SEQUENCE,
    generate_lesson_streaming,
    parse_lesson,
)

LESSON_JSON = "\n".join(
    f"<<<{t}>>>\ncontent for {t}" for t in BLOCK_SEQUENCE
)


async def setup_user_session():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"teach-{uuid.uuid4().hex[:10]}@example.com", name="T")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Computer Science")
        concepts = await seed_concepts_for_user(db, user.id, template)
        session = Session(user_id=user.id, mode="teach")
        db.add(session)
        await db.commit()
        arrays = next(c for c in concepts if c.name == "Arrays")
        return user.id, session.id, arrays.id


def fake_stream(counter):
    async def fake_stream_model(task, messages):
        counter["n"] += 1
        # stream in 3 chunks to exercise delta assembly
        third = len(LESSON_JSON) // 3
        yield {"text": LESSON_JSON[:third], "replace": False}
        yield {"text": LESSON_JSON[third : 2 * third], "replace": False}
        yield {"text": LESSON_JSON[2 * third :], "replace": False}

    return fake_stream_model


def mock_visual_classifier(
    monkeypatch,
    reply='{"image": false, "image_query": "", "simulation": false, "sim_query": ""}',
):
    async def fake_call_model(task, messages):
        return reply

    monkeypatch.setattr(teaching, "call_model", fake_call_model)


@pytest.mark.asyncio
async def test_lesson_generation_stores_all_seven_blocks(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(teaching, "stream_model", fake_stream(counter))
    mock_visual_classifier(monkeypatch)
    user_id, session_id, concept_id = await setup_user_session()

    async with SessionLocal() as db:
        events = [
            e
            async for e in generate_lesson_streaming(db, user_id, session_id, concept_id)
        ]

    deltas = [e for e in events if e["event"] == "delta"]
    done = events[-1]
    assert len(deltas) == 3
    assert done["event"] == "done"
    assert [b["type"] for b in done["blocks"]] == BLOCK_SEQUENCE

    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(LessonBlock).where(LessonBlock.session_id == session_id)
            )
        ).all()
    assert len(rows) == 7
    assert all(r.concept_id == concept_id for r in rows)


@pytest.mark.asyncio
async def test_same_cohort_second_lesson_is_cache_hit(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(teaching, "stream_model", fake_stream(counter))
    mock_visual_classifier(monkeypatch)
    user_id, session_id, concept_id = await setup_user_session()

    async with SessionLocal() as db:
        [e async for e in generate_lesson_streaming(db, user_id, session_id, concept_id)]
        events2 = [
            e async for e in generate_lesson_streaming(db, user_id, session_id, concept_id)
        ]

    assert counter["n"] == 1  # one real generation only
    cached_delta = next(e for e in events2 if e["event"] == "delta")
    assert cached_delta.get("cached") is True
    # cached lesson still stored for this session (7 + 7 rows total)
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(LessonBlock).where(LessonBlock.session_id == session_id)
            )
        ).all()
    assert len(rows) == 14


@pytest.mark.asyncio
async def test_reference_material_bypasses_shared_cache(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(teaching, "stream_model", fake_stream(counter))
    mock_visual_classifier(monkeypatch)

    async def fake_search(db, user_id, q, limit=4):
        return ["chunk from the student's own slides"]

    monkeypatch.setattr(teaching, "search_chunks", fake_search)
    user_id, session_id, concept_id = await setup_user_session()

    async with SessionLocal() as db:
        [e async for e in generate_lesson_streaming(db, user_id, session_id, concept_id, "my slides")]
        [e async for e in generate_lesson_streaming(db, user_id, session_id, concept_id, "my slides")]

    assert counter["n"] == 2  # personal-material lessons are never cache-shared
    assert cache.get(f"teach:{concept_id}:default:low") is None


def test_parse_lesson_rejects_empty():
    with pytest.raises(ValueError):
        parse_lesson("no markers here at all")


def test_parse_lesson_accepts_adaptive_sections_and_skips_preamble():
    # section types are agent-chosen per concept/learner — parser is open-ended
    raw = "Sure, here's the lesson!\n<<<intuition>>>\nA\n<<<worked_example>>>\nX\n<<<summary>>>\nB"
    blocks = parse_lesson(raw)
    assert [b["type"] for b in blocks] == ["intuition", "worked_example", "summary"]


@pytest.mark.asyncio
async def test_visual_need_event_emitted_and_cached(monkeypatch):
    counter = {"n": 0}
    monkeypatch.setattr(teaching, "stream_model", fake_stream(counter))
    calls = {"n": 0}

    async def fake_call_model(task, messages):
        calls["n"] += 1
        return '{"image": true, "image_query": "array memory layout diagram", "simulation": true, "sim_query": "array indexing animation"}'

    monkeypatch.setattr(teaching, "call_model", fake_call_model)
    user_id, session_id, concept_id = await setup_user_session()

    async with SessionLocal() as db:
        events1 = [e async for e in teaching.generate_lesson_streaming(db, user_id, session_id, concept_id)]
        events2 = [e async for e in teaching.generate_lesson_streaming(db, user_id, session_id, concept_id)]

    visual = next(e for e in events1 if e["event"] == "visual")
    assert visual["image"] is True and visual["simulation"] is True  # judged independently
    assert "animation" in visual["sim_query"]
    assert "diagram" in visual["image_query"]
    assert any(e["event"] == "visual" for e in events2)
    assert calls["n"] == 1  # classifier decision cached per concept


def test_chunk_text_overlaps_and_covers():
    text = "x" * 3000
    chunks = chunk_text(text)
    assert all(len(c) <= 1200 for c in chunks)
    assert sum(len(c) for c in chunks) >= 3000  # overlap ⇒ total exceeds source
