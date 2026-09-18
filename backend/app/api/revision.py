from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import LearnerConceptState
from app.services.revision import due_concepts, next_due_at, record_review

router = APIRouter(prefix="/revision", tags=["revision"])


@router.get("/due")
async def get_due(user_id: int, db: AsyncSession = Depends(get_db)):
    return {"due": await due_concepts(db, user_id)}


class ReviewRequest(BaseModel):
    user_id: int
    concept_id: int
    score: float = Field(ge=0.0, le=1.0)  # answer quality or self-rating


@router.post("/review")
async def post_review(req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    state = await db.get(LearnerConceptState, (req.user_id, req.concept_id))
    if state is None:
        raise HTTPException(404, "No state for this user/concept")
    record_review(state, req.score)
    await db.commit()
    due_at = next_due_at(state)
    return {
        "concept_id": req.concept_id,
        "mastery": state.mastery,
        "retention_score": state.retention_score,
        "next_due_at": due_at.isoformat() if due_at else None,
    }
