from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import assessment as svc

router = APIRouter(prefix="/assessment", tags=["assessment"])


class StartRequest(BaseModel):
    user_id: int
    subject: str


@router.post("/start")
async def start(req: StartRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.start_assessment(db, req.user_id, req.subject)
    except ValueError as e:
        raise HTTPException(400, str(e))


class AnswerRequest(BaseModel):
    assessment_id: str
    question_index: int
    answer: str


@router.post("/answer")
async def answer(req: AnswerRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await svc.grade_answer(db, req.assessment_id, req.question_index, req.answer)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IndexError:
        raise HTTPException(400, "Invalid question index")
