from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import LessonBlock, Session
from app.services.teaching import BLOCK_SEQUENCE, generate_lesson_streaming

router = APIRouter(prefix="/teach", tags=["teach"])


@router.get("/lessons")
async def stored_lesson(user_id: int, concept_id: int, db: AsyncSession = Depends(get_db)):
    """The user's most recent stored lesson for a concept — lets the frontend
    restore a lesson on re-selecting the node instead of regenerating."""
    rows = (
        await db.scalars(
            select(LessonBlock)
            .join(Session, Session.id == LessonBlock.session_id)
            .where(
                Session.user_id == user_id,
                LessonBlock.concept_id == concept_id,
                LessonBlock.parent_block_id.is_(None),
            )
            .order_by(LessonBlock.id)
        )
    ).all()
    # keep the latest complete run: from the last "intuition" block onward
    start = 0
    for i, b in enumerate(rows):
        if b.type == BLOCK_SEQUENCE[0]:
            start = i
    latest = rows[start:]
    return {"blocks": [{"id": b.id, "type": b.type, "content": b.content} for b in latest]}


@router.get("/stream")
async def stream_lesson(
    user_id: int,
    session_id: int,
    concept_id: int,
    reference: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """SSE lesson stream (GET so the browser EventSource API works).

    Events: `delta` — raw generation text as it arrives;
            `done` — stored lesson blocks (id/type/content)."""

    async def event_source():
        async for event in generate_lesson_streaming(
            db, user_id, session_id, concept_id, reference_query=reference
        ):
            name = event.pop("event")
            yield f"event: {name}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
