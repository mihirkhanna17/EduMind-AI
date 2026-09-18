from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Concept, LearnerConceptState
from app.services.plan import learning_plan

router = APIRouter(tags=["graph"])


@router.get("/plan")
async def get_plan(user_id: int, subject: str, db: AsyncSession = Depends(get_db)):
    """Deterministic study order (prereqs + mastery) — 'what next' without asking."""
    return {"plan": await learning_plan(db, user_id, subject)}


class AddConcept(BaseModel):
    user_id: int
    subject: str
    name: str
    prerequisite_ids: list[int] = []


@router.post("/concepts")
async def add_concept(req: AddConcept, db: AsyncSession = Depends(get_db)):
    """Student-added topic: lands on the canvas like any seeded concept."""
    dupe = await db.scalar(
        select(Concept).where(
            Concept.user_id == req.user_id,
            Concept.subject == req.subject,
            Concept.name.ilike(req.name.strip()),
        )
    )
    if dupe:
        raise HTTPException(409, f"'{req.name}' is already on your canvas")
    concept = Concept(
        user_id=req.user_id,
        subject=req.subject,
        name=req.name.strip(),
        prerequisites=req.prerequisite_ids,
    )
    db.add(concept)
    await db.flush()
    db.add(LearnerConceptState(user_id=req.user_id, concept_id=concept.id))
    await db.commit()
    return {"id": concept.id, "name": concept.name, "subject": concept.subject}


@router.get("/graph")
async def knowledge_graph(user_id: int, subject: str, db: AsyncSession = Depends(get_db)):
    """Nodes + edges for the knowledge canvas. Plain Postgres adjacency:
    parent edges from concepts.parent_id, prerequisite edges from the int[]."""
    concepts = (
        await db.scalars(
            select(Concept).where(Concept.user_id == user_id, Concept.subject == subject)
        )
    ).all()
    states = {
        s.concept_id: s
        for s in (
            await db.scalars(
                select(LearnerConceptState).where(LearnerConceptState.user_id == user_id)
            )
        ).all()
    }

    nodes = []
    edges = []
    for c in concepts:
        state = states.get(c.id)
        nodes.append(
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "confidence": state.confidence if state else 0.0,
                "mastery": state.mastery if state else 0.0,
                "misconceptions": state.misconceptions if state else [],
                "last_reviewed": state.last_reviewed.isoformat() if state and state.last_reviewed else None,
            }
        )
        if c.parent_id:
            edges.append({"source": c.parent_id, "target": c.id, "kind": "parent"})
        for prereq_id in c.prerequisites or []:
            edges.append({"source": prereq_id, "target": c.id, "kind": "prerequisite"})

    return {"nodes": nodes, "edges": edges}
