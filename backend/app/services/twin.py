"""Digital Twin: a curated, versioned VIEW over learner state — no new data.

One batched `twin_summarize` call per session end (never per message) produces
the cognitive/behavioral read; knowledge state and the misconception ledger are
assembled straight from learner_concept_state. Snapshots are immutable rows,
so "how you've changed since last month" is a pure diff of two versions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Branch,
    Concept,
    LearnerConceptState,
    LearnerProfile,
    LessonBlock,
    Session,
    TwinSnapshot,
)
from app.models.router import Task, call_model
from app.services.assessment import _extract_json_value

_SUMMARIZE_PROMPT = """You are summarizing one tutoring session into a learner's evolving profile.

Session activity:
{activity}

Knowledge state after the session (confidence/mastery per concept, 0-1):
{knowledge}

Unresolved misconceptions on record:
{misconceptions}

Previous cognitive profile (may be empty):
{previous}

Return JSON only (no fences):
{{"cognitive_profile": {{"observed_style": "<how this learner seems to learn best>",
  "pacing": "<fast/steady/needs-scaffolding + one clause>",
  "strengths": ["..."], "gaps": ["..."]}},
 "behavioral_profile": {{"engagement": "<one clause>",
  "question_asking": "<one clause about branch/side-question behavior>",
  "recommendations": ["<2-3 concrete next actions>"]}}}}"""


async def _knowledge_state(db: AsyncSession, user_id: int) -> dict:
    rows = (
        await db.execute(
            select(LearnerConceptState, Concept)
            .join(Concept, Concept.id == LearnerConceptState.concept_id)
            .where(LearnerConceptState.user_id == user_id)
        )
    ).all()
    return {
        str(concept.id): {
            "name": concept.name,
            "subject": concept.subject,
            "confidence": state.confidence,
            "mastery": state.mastery,
            "retention_score": state.retention_score,
        }
        for state, concept in rows
    }


async def _misconception_ledger(db: AsyncSession, user_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(LearnerConceptState, Concept)
            .join(Concept, Concept.id == LearnerConceptState.concept_id)
            .where(LearnerConceptState.user_id == user_id)
        )
    ).all()
    ledger = []
    for state, concept in rows:
        for m in state.misconceptions or []:
            ledger.append({"concept": concept.name, **m})
    return ledger


async def _session_activity(db: AsyncSession, user_id: int, session_id: int | None) -> dict:
    activity: dict = {"session_id": session_id}
    if session_id:
        blocks = await db.scalar(
            select(func.count(LessonBlock.id)).where(LessonBlock.session_id == session_id)
        )
        branches = await db.scalar(
            select(func.count(Branch.id))
            .join(LessonBlock, LessonBlock.id == Branch.parent_block_id)
            .where(LessonBlock.session_id == session_id)
        )
        session = await db.get(Session, session_id)
        activity.update(
            {
                "lesson_blocks": blocks or 0,
                "branches_opened": branches or 0,
                "mode": session.mode if session else "teach",
                "started_at": session.started_at.isoformat() if session and session.started_at else None,
            }
        )
    total_sessions = await db.scalar(
        select(func.count(Session.id)).where(Session.user_id == user_id)
    )
    activity["total_sessions"] = total_sessions or 0
    return activity


async def build_snapshot(
    db: AsyncSession, user_id: int, session_id: int | None = None
) -> TwinSnapshot:
    knowledge = await _knowledge_state(db, user_id)
    ledger = await _misconception_ledger(db, user_id)
    activity = await _session_activity(db, user_id, session_id)

    previous = await db.scalar(
        select(TwinSnapshot)
        .where(TwinSnapshot.user_id == user_id)
        .order_by(TwinSnapshot.version.desc())
        .limit(1)
    )

    unresolved = [m for m in ledger if not m.get("resolved")]
    try:
        raw = await call_model(
            Task.twin_summarize,
            [
                {
                    "role": "user",
                    "content": _SUMMARIZE_PROMPT.format(
                        activity=json.dumps(activity),
                        knowledge=json.dumps(
                            {v["name"]: {"confidence": v["confidence"], "mastery": v["mastery"]}
                             for v in knowledge.values()}
                        ),
                        misconceptions=json.dumps([m["text"] for m in unresolved]) or "[]",
                        previous=json.dumps(previous.cognitive_profile) if previous else "{}",
                    ),
                }
            ],
        )
        summary = _extract_json_value(raw)
        cognitive = summary.get("cognitive_profile") or {}
        behavioral = summary.get("behavioral_profile") or {}
    except Exception:
        # A failed summary must never lose the session's knowledge snapshot.
        cognitive = previous.cognitive_profile if previous else {}
        behavioral = {"engagement": "summary unavailable this session"}

    behavioral = {**behavioral, "last_session_activity": activity}

    snapshot = TwinSnapshot(
        user_id=user_id,
        version=(previous.version + 1) if previous else 1,
        cognitive_profile=cognitive,
        knowledge_state=knowledge,
        misconception_ledger=ledger,
        behavioral_profile=behavioral,
        snapshotted_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    await db.commit()
    return snapshot


def diff_snapshots(old: TwinSnapshot, new: TwinSnapshot) -> dict:
    """What changed between two versions — powers the dashboard diff view."""
    changes = []
    old_k, new_k = old.knowledge_state or {}, new.knowledge_state or {}
    for cid, cur in new_k.items():
        prev = old_k.get(cid)
        if prev is None:
            changes.append({"concept": cur["name"], "kind": "new", "mastery": cur["mastery"]})
            continue
        d_mastery = round(cur["mastery"] - prev["mastery"], 4)
        d_conf = round(cur["confidence"] - prev["confidence"], 4)
        if abs(d_mastery) >= 0.01 or abs(d_conf) >= 0.01:
            changes.append(
                {
                    "concept": cur["name"],
                    "kind": "improved" if (d_mastery + d_conf) > 0 else "slipped",
                    "mastery_delta": d_mastery,
                    "confidence_delta": d_conf,
                }
            )

    def keyset(ledger):
        return {(m["concept"], m["text"]) for m in (ledger or [])}

    old_m, new_m = keyset(old.misconception_ledger), keyset(new.misconception_ledger)
    return {
        "from_version": old.version,
        "to_version": new.version,
        "from_date": old.snapshotted_at.isoformat() if old.snapshotted_at else None,
        "to_date": new.snapshotted_at.isoformat() if new.snapshotted_at else None,
        "concept_changes": changes,
        "new_misconceptions": [{"concept": c, "text": t} for c, t in (new_m - old_m)],
        "resolved_misconceptions": [{"concept": c, "text": t} for c, t in (old_m - new_m)],
    }
