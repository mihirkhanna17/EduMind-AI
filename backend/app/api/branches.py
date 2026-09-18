from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Branch
from app.services import branching

router = APIRouter(prefix="/branches", tags=["branches"])


class OpenBranch(BaseModel):
    user_id: int
    session_id: int
    parent_block_id: int | None = None  # None → free-form "new chat"
    concept_id: int | None = None  # anchor for free-form chats
    question: str
    # Thread the student is currently on: "session-<id>" for the main lesson,
    # or another branch's thread_id when nesting.
    parent_thread_id: str | None = None


@router.post("")
async def open_branch(req: OpenBranch, request: Request, db: AsyncSession = Depends(get_db)):
    parent_thread = req.parent_thread_id or f"session-{req.session_id}"
    try:
        return await branching.open_branch(
            db,
            request.app.state.graph,
            req.user_id,
            req.session_id,
            req.parent_block_id,
            req.question,
            parent_thread,
            concept_id=req.concept_id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{branch_id}")
async def delete_branch(branch_id: int, db: AsyncSession = Depends(get_db)):
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(404, "Branch not found")
    await db.delete(branch)
    await db.commit()
    return {"deleted": branch_id}


class BranchMessage(BaseModel):
    message: str


@router.post("/{branch_id}/message")
async def continue_branch(
    branch_id: int, req: BranchMessage, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        return await branching.continue_branch(
            db, request.app.state.graph, branch_id, req.message
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("")
async def list_branches(parent_block_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(Branch).where(Branch.parent_block_id == parent_block_id).order_by(Branch.id)
        )
    ).all()
    return {
        "branches": [
            {"branch_id": b.id, "thread_id": b.thread_id, "question": b.question}
            for b in rows
        ]
    }


@router.get("/concept/{concept_id}")
async def branches_for_concept(
    concept_id: int, user_id: int, db: AsyncSession = Depends(get_db)
):
    """Every branch the student ever opened under this concept — block-anchored
    branches AND free-form chats — so nothing is ever lost."""
    from sqlalchemy import or_

    from app.models import LessonBlock, Session

    rows = (
        await db.execute(
            select(Branch)
            .outerjoin(LessonBlock, LessonBlock.id == Branch.parent_block_id)
            .outerjoin(Session, Session.id == LessonBlock.session_id)
            .where(
                or_(
                    (LessonBlock.concept_id == concept_id) & (Session.user_id == user_id),
                    Branch.concept_id == concept_id,
                )
            )
            .order_by(Branch.id.desc())
            .limit(30)
        )
    ).all()
    return {
        "branches": [
            {
                "branch_id": b.id,
                "thread_id": b.thread_id,
                "question": b.question,
                "response": b.response,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for (b,) in rows
        ]
    }


@router.get("/{branch_id}/history")
async def get_history(branch_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(404, "Branch not found")
    history = await branching.branch_history(request.app.state.graph, branch.thread_id)
    return {"branch_id": branch_id, "thread_id": branch.thread_id, "messages": history}
