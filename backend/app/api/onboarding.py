from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import LearnerProfile, SubjectTemplate
from app.schemas import OnboardingQuestion
from app.services.onboarding import get_or_create_template, seed_concepts_for_user

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/subjects")
async def list_subjects(db: AsyncSession = Depends(get_db)):
    """Subjects with a ready template. Any other subject string is also valid —
    it just routes through the Dynamic Onboarding Agent (one model call)."""
    rows = (await db.scalars(select(SubjectTemplate.subject))).all()
    return {"subjects": rows}


@router.get("/questions")
async def get_questions(subject: str, db: AsyncSession = Depends(get_db)):
    """Subject-specific onboarding questions (template, or generated+persisted)."""
    template = await get_or_create_template(db, subject)
    return {
        "subject": template.subject,
        "questions": [q.model_dump() for q in template.onboarding_questions],
    }


class CompleteRequest(BaseModel):
    user_id: int
    subject: str
    # Answers to the subject-specific questions, keyed by question key.
    answers: dict = {}
    # Structured multi-step form payloads (feature 1) — stored as-is.
    academic_profile: dict = {}
    goals: dict = {}
    time_constraints: dict = {}
    learning_prefs: dict = {}
    behavioral_prefs: dict = {}


@router.post("/complete")
async def complete_onboarding(req: CompleteRequest, db: AsyncSession = Depends(get_db)):
    """Persist the learner profile and auto-seed the user's concept graph."""
    profile = await db.get(LearnerProfile, req.user_id)
    if profile is None:
        profile = LearnerProfile(user_id=req.user_id)
        db.add(profile)
    # Subject answers live inside academic_profile, keyed per subject.
    academic = dict(profile.academic_profile or {})
    academic.setdefault("subject_answers", {})[req.subject] = req.answers
    if req.academic_profile:
        academic.update(req.academic_profile)
    profile.academic_profile = academic
    profile.goals = req.goals or profile.goals or {}
    profile.time_constraints = req.time_constraints or profile.time_constraints or {}
    profile.learning_prefs = req.learning_prefs or profile.learning_prefs or {}
    profile.behavioral_prefs = req.behavioral_prefs or profile.behavioral_prefs or {}
    await db.commit()

    template = await get_or_create_template(db, req.subject)
    concepts = await seed_concepts_for_user(db, req.user_id, template)
    return {
        "subject": template.subject,
        "seeded_concepts": [{"id": c.id, "name": c.name} for c in concepts],
    }
