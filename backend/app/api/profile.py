from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Concept, LearnerProfile, User

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{user_id}")
async def get_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    profile = await db.get(LearnerProfile, user_id)
    subjects = (
        await db.scalars(
            select(distinct(Concept.subject)).where(Concept.user_id == user_id)
        )
    ).all()
    return {
        "user": {"id": user_id, "email": user.email if user else "", "name": user.name if user else ""},
        "subjects": subjects,
        "learning_prefs": (profile.learning_prefs if profile else {}) or {},
        "goals": (profile.goals if profile else {}) or {},
        "time_constraints": (profile.time_constraints if profile else {}) or {},
    }


class ProfileUpdate(BaseModel):
    learning_prefs: dict | None = None
    goals: dict | None = None
    time_constraints: dict | None = None


@router.put("/{user_id}")
async def update_profile(user_id: int, req: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    profile = await db.get(LearnerProfile, user_id)
    if profile is None:
        profile = LearnerProfile(user_id=user_id)
        db.add(profile)
    if req.learning_prefs is not None:
        profile.learning_prefs = req.learning_prefs
    if req.goals is not None:
        profile.goals = req.goals
    if req.time_constraints is not None:
        profile.time_constraints = req.time_constraints
    await db.commit()
    return {"ok": True}
