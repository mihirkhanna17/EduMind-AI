from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(user_id: int, db: AsyncSession = Depends(get_db)):
    """Session history with per-session lesson volume."""
    from sqlalchemy import func, select

    from app.models import LessonBlock

    rows = (
        await db.execute(
            select(Session, func.count(LessonBlock.id))
            .outerjoin(LessonBlock, LessonBlock.session_id == Session.id)
            .where(Session.user_id == user_id)
            .group_by(Session.id)
            .order_by(Session.started_at.desc())
            .limit(30)
        )
    ).all()
    return {
        "sessions": [
            {
                "session_id": s.id,
                "mode": s.mode,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "lesson_blocks": blocks,
            }
            for s, blocks in rows
        ]
    }


class StartSession(BaseModel):
    user_id: int
    mode: str = "teach"


@router.post("/start")
async def start_session(req: StartSession, db: AsyncSession = Depends(get_db)):
    session = Session(user_id=req.user_id, mode=req.mode)
    db.add(session)
    await db.commit()
    return {"session_id": session.id, "started_at": session.started_at}


@router.post("/{session_id}/end")
async def end_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Ends the session and runs the Digital Twin Updater — the ONE batched
    summarize call per session (never per message)."""
    from app.services.twin import build_snapshot

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    snapshot = await build_snapshot(db, session.user_id, session_id)
    return {
        "session_id": session.id,
        "ended_at": session.ended_at,
        "twin_version": snapshot.version,
    }
