"""Learning plan: a deterministic study order so the student never has to ask
"what next". Pure logic, no LLM calls.

Topological order over prerequisites; a concept is:
- done    — mastery ≥ 0.6
- ready   — every prerequisite is done (or it has none)
- locked  — some prerequisite still isn't done
The plan lists ready-but-not-done concepts first (in prereq order), then locked
ones, then done ones — the first entry is always "up next".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerConceptState

DONE_MASTERY = 0.6


async def learning_plan(db: AsyncSession, user_id: int, subject: str) -> list[dict]:
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
    ids = {c.id for c in concepts}

    # Kahn's algorithm over prerequisite edges (stable: alphabetical tiebreak)
    remaining = {c.id: [p for p in (c.prerequisites or []) if p in ids] for c in concepts}
    by_id = {c.id: c for c in concepts}
    order: list[int] = []
    while remaining:
        ready_now = sorted(
            (cid for cid, prereqs in remaining.items() if not prereqs),
            key=lambda cid: by_id[cid].name,
        )
        if not ready_now:  # cycle — take what's left deterministically
            ready_now = sorted(remaining, key=lambda cid: by_id[cid].name)
        for cid in ready_now:
            order.append(cid)
            del remaining[cid]
        for prereqs in remaining.values():
            for cid in ready_now:
                if cid in prereqs:
                    prereqs.remove(cid)

    def mastery(cid: int) -> float:
        s = states.get(cid)
        return s.mastery if s else 0.0

    def entry(cid: int) -> dict:
        c = by_id[cid]
        m = mastery(cid)
        prereqs = [p for p in (c.prerequisites or []) if p in ids]
        if m >= DONE_MASTERY:
            status = "done"
        elif all(mastery(p) >= DONE_MASTERY for p in prereqs):
            status = "ready"
        else:
            status = "locked"
        return {
            "concept_id": cid,
            "name": c.name,
            "mastery": round(m, 3),
            "status": status,
            "prerequisites": [by_id[p].name for p in prereqs],
        }

    entries = [entry(cid) for cid in order]
    rank = {"ready": 0, "locked": 1, "done": 2}
    # stable sort keeps prerequisite order within each status group
    return sorted(entries, key=lambda e: rank[e["status"]])
