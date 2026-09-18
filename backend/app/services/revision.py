"""Spaced-repetition scheduler — simplified SM-2, pure logic, no LLM calls.

`retention_score` plays SM-2's easiness-factor role (default 2.5, floor 1.3).
Review quality (0..1 score from an answer or self-rating) adjusts it with the
SM-2 easiness update; the review interval derives from mastery band × easiness,
so structurally-shaky concepts resurface fast and solid ones back off.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerConceptState

MIN_EASINESS = 1.3
_MASTERY_WEIGHT = 0.3  # EWMA weight of a new review in mastery


def updated_easiness(easiness: float, score: float) -> float:
    """SM-2 easiness update with q mapped from a 0..1 score to 0..5."""
    q = round(max(0.0, min(1.0, score)) * 5)
    new = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return round(max(MIN_EASINESS, new), 4)


def review_interval_days(mastery: float, easiness: float) -> int:
    """SM-2 uses repetition count; we derive the band from mastery instead
    (mastery is the durable signal we already track per concept)."""
    if mastery < 0.3:
        return 1
    if mastery < 0.6:
        return 3
    return max(6, round(6 * easiness))


def next_due_at(state: LearnerConceptState) -> datetime | None:
    """None = never reviewed → it's new material, not revision material."""
    if state.last_reviewed is None:
        return None
    last = state.last_reviewed
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last + timedelta(days=review_interval_days(state.mastery or 0.0, state.retention_score or 2.5))


def record_review(state: LearnerConceptState, score: float, now: datetime | None = None) -> None:
    state.retention_score = updated_easiness(state.retention_score or 2.5, score)
    state.mastery = round(
        (1 - _MASTERY_WEIGHT) * (state.mastery or 0.0) + _MASTERY_WEIGHT * score, 4
    )
    state.last_reviewed = now or datetime.now(timezone.utc)


async def due_concepts(db: AsyncSession, user_id: int, now: datetime | None = None) -> list[dict]:
    """Concepts whose review window has lapsed, most overdue first."""
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(LearnerConceptState, Concept)
            .join(Concept, Concept.id == LearnerConceptState.concept_id)
            .where(LearnerConceptState.user_id == user_id)
        )
    ).all()

    due = []
    for state, concept in rows:
        due_at = next_due_at(state)
        if due_at is None or due_at > now:
            continue
        due.append(
            {
                "concept_id": concept.id,
                "name": concept.name,
                "subject": concept.subject,
                "mastery": state.mastery,
                "retention_score": state.retention_score,
                "due_at": due_at.isoformat(),
                "overdue_days": round((now - due_at).total_seconds() / 86400, 1),
            }
        )
    due.sort(key=lambda d: d["overdue_days"], reverse=True)
    return due
