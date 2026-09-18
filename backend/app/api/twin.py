from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import TwinSnapshot
from app.services.twin import build_snapshot, diff_snapshots

router = APIRouter(prefix="/twin", tags=["twin"])


@router.post("/{user_id}/snapshot")
async def snapshot_now(user_id: int, db: AsyncSession = Depends(get_db)):
    """On-demand twin refresh (one batched call) — same path as session end."""
    snapshot = await build_snapshot(db, user_id, None)
    return {"version": snapshot.version}


def _out(s: TwinSnapshot) -> dict:
    return {
        "version": s.version,
        "snapshotted_at": s.snapshotted_at.isoformat() if s.snapshotted_at else None,
        "cognitive_profile": s.cognitive_profile,
        "knowledge_state": s.knowledge_state,
        "misconception_ledger": s.misconception_ledger,
        "behavioral_profile": s.behavioral_profile,
    }


@router.get("/{user_id}")
async def latest(user_id: int, db: AsyncSession = Depends(get_db)):
    snapshot = await db.scalar(
        select(TwinSnapshot)
        .where(TwinSnapshot.user_id == user_id)
        .order_by(TwinSnapshot.version.desc())
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(404, "No twin snapshot yet — finish a session first")
    return _out(snapshot)


@router.get("/{user_id}/history")
async def history(user_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(TwinSnapshot)
            .where(TwinSnapshot.user_id == user_id)
            .order_by(TwinSnapshot.version)
        )
    ).all()
    return {
        "versions": [
            {"version": s.version, "snapshotted_at": s.snapshotted_at.isoformat() if s.snapshotted_at else None}
            for s in rows
        ]
    }


@router.get("/{user_id}/diff")
async def diff(user_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.scalars(
            select(TwinSnapshot)
            .where(TwinSnapshot.user_id == user_id)
            .order_by(TwinSnapshot.version.desc())
            .limit(2)
        )
    ).all()
    if len(rows) < 2:
        raise HTTPException(404, "Need at least two snapshots to diff")
    new, old = rows[0], rows[1]
    return diff_snapshots(old, new)
