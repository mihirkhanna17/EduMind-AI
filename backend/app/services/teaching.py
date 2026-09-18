"""Adaptive Teaching Engine.

Every lesson follows the pedagogical template:
intuition → analogy → theory → real_world_example → counter_example
→ interactive_question → summary

One mid-tier call generates all seven blocks as JSON; blocks are stored as
lesson_blocks rows. Near-identical lessons are served from the response cache
(keyed by concept + learner cohort features), and generation is streamable.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerConceptState, LearnerProfile, LessonBlock
from app.models.router import Task, call_model, stream_model
from app.services.documents import search_chunks
from app.services.response_cache import cache

BLOCK_SEQUENCE = [
    "intuition",
    "analogy",
    "theory",
    "real_world_example",
    "counter_example",
    "interactive_question",
    "summary",
]

# Long markdown inside JSON breaks too often (unescaped quotes/newlines), so
# lessons use explicit section markers instead — trivially parseable and the
# stream stays human-readable.
_LESSON_PROMPT = """You are Edumind's teaching agent. Teach ONE concept as a structured lesson,
designing the lesson STRUCTURE for this specific concept and this specific learner.

Concept: {concept} (subject: {subject})
Learner profile:
- current confidence in this concept: {confidence:.2f} (0 = new, 1 = solid)
- learning preferences: {prefs}
- known misconceptions to gently correct: {misconceptions}
{context_section}
First decide which sections THIS concept and THIS learner actually need — do not
use a fixed template. Choose 4-7 sections from:
  intuition, analogy, theory, worked_example, real_world_example, counter_example,
  common_mistakes, practice, interactive_question, summary
Rules:
- pick what fits: a math-heavy concept may want theory + worked_example; a
  conceptual one may want intuition + analogy; a procedure may want practice
- if misconceptions are listed, include counter_example or common_mistakes to fix them
- ALWAYS end with interactive_question (ONE question) then summary (3-5 bullets)
- order the sections in whatever sequence teaches best for this learner's preferences

Begin each section with its marker on its own line, then markdown content:
<<<section_name>>>
content...

Each section is 60-180 words (summary may be shorter). No text before the first
marker. LaTeX is supported: wrap inline math in \\( \\) and display math in \\[ \\].
Calibrate depth to confidence: low → slower, more scaffolding; high → denser."""


def _cohort_key(confidence: float, prefs: dict) -> str:
    """Cache cohort: learners with the same style + level band share lessons."""
    band = "low" if confidence < 0.34 else "mid" if confidence < 0.67 else "high"
    style = str(prefs.get("style", "default")).lower().replace(" ", "-")[:40]
    return f"{style}:{band}"


async def _lesson_inputs(db: AsyncSession, user_id: int, concept_id: int) -> dict:
    concept = await db.get(Concept, concept_id)
    if concept is None:
        raise ValueError(f"Concept {concept_id} not found")
    state = await db.get(LearnerConceptState, (user_id, concept_id))
    profile = await db.get(LearnerProfile, user_id)
    prefs = (profile.learning_prefs if profile else {}) or {}
    confidence = state.confidence if state else 0.0
    misconceptions = [
        m["text"] for m in (state.misconceptions or []) if not m.get("resolved")
    ] if state else []
    return {
        "concept": concept,
        "confidence": confidence,
        "prefs": prefs,
        "misconceptions": misconceptions,
    }


def _build_prompt(inputs: dict, retrieved: list[str]) -> str:
    context_section = ""
    if retrieved:
        joined = "\n---\n".join(retrieved)
        context_section = (
            "\nThe learner uploaded course material. Ground the lesson in it where relevant:\n"
            f"<course_material>\n{joined}\n</course_material>\n"
        )
    return _LESSON_PROMPT.format(
        concept=inputs["concept"].name,
        subject=inputs["concept"].subject,
        confidence=inputs["confidence"],
        prefs=json.dumps(inputs["prefs"]) if inputs["prefs"] else "none given",
        misconceptions="; ".join(inputs["misconceptions"]) or "none recorded",
        context_section=context_section,
    )


def parse_lesson(raw: str) -> list[dict]:
    """Split marker-delimited lesson text into typed blocks. Section types are
    open-ended — the agent designs the structure per concept/learner."""
    import re

    parts = re.split(r"<<<\s*([a-z_]+)\s*>>>", raw)
    # parts = [preamble, type1, content1, type2, content2, ...]
    blocks = []
    for i in range(1, len(parts) - 1, 2):
        block_type = parts[i].strip()
        content = parts[i + 1].strip()
        if content:
            blocks.append({"type": block_type, "content": content})
    if not blocks:
        raise ValueError(f"No lesson sections found in output: {raw[:200]}")
    return blocks


async def store_lesson(
    db: AsyncSession,
    session_id: int,
    concept_id: int,
    blocks: list[dict],
    parent_block_id: int | None = None,
) -> list[LessonBlock]:
    rows = []
    for b in blocks:
        row = LessonBlock(
            session_id=session_id,
            concept_id=concept_id,
            type=b["type"],
            content=b["content"],
            parent_block_id=parent_block_id,
        )
        db.add(row)
        rows.append(row)
    await db.commit()
    return rows


async def generate_lesson_streaming(
    db: AsyncSession,
    user_id: int,
    session_id: int,
    concept_id: int,
    reference_query: str | None = None,
) -> AsyncIterator[dict]:
    """Yields {"event": "delta", "text": ...} during generation, then one
    {"event": "done", "blocks": [...]} with stored block ids.

    Cache hit → a single delta with the full lesson, then done (blocks are
    still stored per session so branching has anchors)."""
    inputs = await _lesson_inputs(db, user_id, concept_id)
    # Lessons ground themselves in the student's uploaded material by default —
    # the concept name is the retrieval query unless a specific one is given.
    query = reference_query or inputs["concept"].name
    try:
        retrieved = await search_chunks(db, user_id, query)
    except Exception:
        retrieved = []

    cache_key = f"teach:{concept_id}:{_cohort_key(inputs['confidence'], inputs['prefs'])}"
    raw = cache.get(cache_key) if not retrieved else None  # personal material → no shared cache

    if raw is None:
        prompt = _build_prompt(inputs, retrieved)
        collected: list[str] = []
        async for ev in stream_model(Task.teach_concept, [{"role": "user", "content": prompt}]):
            if ev["replace"]:
                collected = [ev["text"]]
                yield {"event": "replace", "text": ev["text"]}
            else:
                collected.append(ev["text"])
                yield {"event": "delta", "text": ev["text"]}
        raw = "".join(collected)
        if not retrieved:
            cache.set(cache_key, raw)
    else:
        yield {"event": "delta", "text": raw, "cached": True}

    blocks = parse_lesson(raw)
    rows = await store_lesson(db, session_id, concept_id, blocks)
    yield {
        "event": "done",
        "blocks": [
            {"id": r.id, "type": r.type, "content": r.content} for r in rows
        ],
    }

    # Visualization-need agent: one cheap call, cached per concept. It decides
    # image and simulation INDEPENDENTLY — a topic can deserve both, either,
    # or neither. The frontend auto-fetches images and offers simulations.
    suggestion = await classify_visual_need(inputs["concept"])
    if suggestion["image"] or suggestion["simulation"]:
        yield {"event": "visual", **suggestion}


_VISUAL_PROMPT = """A student just finished a text lesson on "{concept}" ({subject}).
Judge, for THIS specific topic, each of these independently:

1. image — would a labeled diagram, illustration, or real photo significantly
   deepen understanding? (structures, setups, spatial relationships, anatomy,
   apparatus, geometry of the situation…)
2. simulation — would an interactive/animated demonstration significantly
   deepen understanding? (motion, processes over time, algorithms, cause-effect
   the student can manipulate…)

Both can be true, one, or neither — judge from the nature of the topic itself.

Return JSON only:
{{"image": true|false, "image_query": "<specific image search phrase, e.g. 'torque on a rotating rigid body labeled diagram'>",
 "simulation": true|false, "sim_query": "<what the simulation should demonstrate>"}}"""


async def classify_visual_need(concept) -> dict:
    """Cheap-model check, cached per concept forever."""
    cache_key = f"visual2:{concept.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return json.loads(cached)
    try:
        raw = await call_model(
            Task.classify_visual,
            [
                {
                    "role": "user",
                    "content": _VISUAL_PROMPT.format(
                        concept=concept.name, subject=concept.subject
                    ),
                }
            ],
        )
        from app.services.assessment import _extract_json_value

        data = _extract_json_value(raw)
        result = {
            "image": bool(data.get("image")),
            "image_query": str(data.get("image_query") or concept.name),
            "simulation": bool(data.get("simulation")),
            "sim_query": str(data.get("sim_query") or concept.name),
        }
    except Exception:
        result = {"image": False, "image_query": "", "simulation": False, "sim_query": ""}
    cache.set(cache_key, json.dumps(result), ttl_seconds=30 * 24 * 3600)
    return result


async def generate_lesson(
    db: AsyncSession,
    user_id: int,
    session_id: int,
    concept_id: int,
    reference_query: str | None = None,
) -> list[LessonBlock]:
    """Non-streaming variant used by the graph's teaching node."""
    result: list[LessonBlock] = []
    async for event in generate_lesson_streaming(
        db, user_id, session_id, concept_id, reference_query
    ):
        if event["event"] == "done":
            ids = [b["id"] for b in event["blocks"]]
            result = (
                await db.scalars(select(LessonBlock).where(LessonBlock.id.in_(ids)))
            ).all()
    return list(result)
