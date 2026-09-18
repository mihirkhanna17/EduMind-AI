from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import simulations as svc

router = APIRouter(prefix="/simulations", tags=["simulations"])


class SimRequest(BaseModel):
    user_id: int
    concept_id: int
    force: bool = False  # regenerate even if cached


@router.get("/cached")
async def cached_simulation(user_id: int, concept_id: int, db: AsyncSession = Depends(get_db)):
    """Cached-only lookup (no generation) — used to restore a concept's simulation."""
    from sqlalchemy import select

    from app.models import LearnerProfile, SimulationCache
    from app.services.simulations import variant_key_for

    profile = await db.get(LearnerProfile, user_id)
    row = await db.scalar(
        select(SimulationCache).where(
            SimulationCache.concept_id == concept_id,
            SimulationCache.variant_key == variant_key_for(profile),
        )
    )
    if row is None:
        return {"found": False}
    return {
        "found": True,
        "simulation_id": row.id,
        "concept_id": row.concept_id,
        "library": row.library,
        "code": row.code,
        "cached": True,
    }


@router.post("")
async def get_simulation(req: SimRequest, db: AsyncSession = Depends(get_db)):
    """Cached per (concept, learner cohort). The `code` is a complete HTML doc —
    render ONLY via <iframe srcdoc sandbox="allow-scripts">."""
    try:
        row, cached = await svc.get_or_generate(db, req.user_id, req.concept_id, force=req.force)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {
        "simulation_id": row.id,
        "concept_id": row.concept_id,
        "library": row.library,
        "code": row.code,
        "cached": cached,
    }
