"""Subject-adaptive onboarding: template lookup → dynamic generation fallback,
then per-user concept-graph seeding. Both paths produce SubjectTemplateData,
so seeding code doesn't care where the tree came from.
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerConceptState, SubjectTemplate
from app.models.router import Task, call_model
from app.schemas import SubjectTemplateData
from app.services.subject_templates import get_template

_DYNAMIC_PROMPT = """You are designing the onboarding for a personalized tutoring system.
The student wants to learn: "{subject}"

Produce a JSON object with exactly this shape (no prose, no markdown fences):
{{
  "subject": "{subject}",
  "starter_concepts": [
    {{"name": "...", "parent": null, "prerequisites": ["<name of another starter concept>"]}}
  ],
  "onboarding_questions": [
    {{"key": "snake_case_key", "text": "...", "type": "single_select" | "multi_select", "options": ["..."]}}
  ]
}}

Rules:
- 8 to 12 starter_concepts covering the subject's core first topics, ordered roughly by learning sequence.
- "prerequisites" may only reference names that appear in starter_concepts.
- 4 to 6 onboarding_questions that reveal the student's background, comfort level,
  what they've already covered, preferred explanation style, and goal.
- Every question needs 3-6 options."""


def _extract_json(raw: str) -> dict:
    """Tolerate markdown fences / stray prose around the JSON object."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model output: {raw[:200]}")
    return json.loads(text[start : end + 1])


async def generate_dynamic_template(subject: str) -> SubjectTemplateData:
    """One structured-JSON call for subjects not in the library."""
    raw = await call_model(
        Task.onboard_dynamic,
        [{"role": "user", "content": _DYNAMIC_PROMPT.format(subject=subject)}],
    )
    data = SubjectTemplateData.model_validate(_extract_json(raw))
    data.subject = subject
    return data


async def get_or_create_template(db: AsyncSession, subject: str) -> SubjectTemplateData:
    """Library hit → use it. Miss → generate once, persist so the next student
    of this subject costs zero model calls."""
    template = await get_template(db, subject)
    if template is not None:
        return template
    template = await generate_dynamic_template(subject)
    db.add(
        SubjectTemplate(
            subject=template.subject,
            starter_concepts=[c.model_dump() for c in template.starter_concepts],
            onboarding_questions=[q.model_dump() for q in template.onboarding_questions],
        )
    )
    await db.commit()
    return template


async def merge_concepts_for_user(
    db: AsyncSession, user_id: int, subject: str, starter_concepts: list
) -> list[Concept]:
    """Additive seeding: add concepts that don't exist yet (by name), resolving
    parents/prerequisites against both new and existing concepts. Used by the
    document-roadmap flow to extend an already-seeded subject."""
    existing = (
        await db.scalars(
            select(Concept).where(Concept.user_id == user_id, Concept.subject == subject)
        )
    ).all()
    by_name: dict[str, Concept] = {c.name.lower(): c for c in existing}

    added: list[Concept] = []
    for sc in starter_concepts:
        if sc.name.lower() in by_name:
            continue
        concept = Concept(subject=subject, name=sc.name, user_id=user_id, prerequisites=[])
        db.add(concept)
        by_name[sc.name.lower()] = concept
        added.append(concept)
    await db.flush()

    for sc in starter_concepts:
        concept = by_name[sc.name.lower()]
        if concept not in added:
            continue
        if sc.parent and sc.parent.lower() in by_name:
            concept.parent_id = by_name[sc.parent.lower()].id
        concept.prerequisites = [
            by_name[p.lower()].id for p in sc.prerequisites if p.lower() in by_name
        ]
        db.add(LearnerConceptState(user_id=user_id, concept_id=concept.id))

    await db.commit()
    return added


async def seed_concepts_for_user(
    db: AsyncSession, user_id: int, template: SubjectTemplateData
) -> list[Concept]:
    """Create the user's concept rows + zeroed learner_concept_state.

    Two passes: insert all concepts, then resolve parent/prerequisite names
    to ids (templates reference concepts by name).
    Idempotent per (user, subject): existing rows are returned untouched.
    """
    existing = (
        await db.scalars(
            select(Concept).where(
                Concept.user_id == user_id, Concept.subject == template.subject
            )
        )
    ).all()
    if existing:
        return list(existing)

    by_name: dict[str, Concept] = {}
    for sc in template.starter_concepts:
        concept = Concept(
            subject=template.subject, name=sc.name, user_id=user_id, prerequisites=[]
        )
        db.add(concept)
        by_name[sc.name] = concept
    await db.flush()  # assign ids

    for sc in template.starter_concepts:
        concept = by_name[sc.name]
        if sc.parent and sc.parent in by_name:
            concept.parent_id = by_name[sc.parent].id
        concept.prerequisites = [
            by_name[p].id for p in sc.prerequisites if p in by_name
        ]
        db.add(
            LearnerConceptState(
                user_id=user_id, concept_id=concept.id, confidence=0.0, mastery=0.0
            )
        )

    await db.commit()
    return list(by_name.values())
