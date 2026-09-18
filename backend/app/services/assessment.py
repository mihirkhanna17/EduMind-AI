"""Diagnostic assessment: cheap-model quiz generation, deterministic MCQ
grading, mid-tier short-answer grading, confidence writes per answer."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerConceptState
from app.models.router import Task, call_model
from app.services.session_store import store

# EWMA weight for new evidence when updating confidence.
_EVIDENCE_WEIGHT = 0.4


class QuizQuestion(BaseModel):
    concept: str
    type: Literal["mcq", "short_answer"]
    question: str
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None
    answer_guide: str | None = None  # what a good short answer contains


_QUIZ_PROMPT = """Create a short diagnostic quiz for a student starting "{subject}".
Concepts to probe: {concepts}

Return a JSON array (no prose, no markdown fences) of exactly {n} questions:
- {n_mcq} of type "mcq": {{"concept": "<one of the concepts>", "type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0}}
- 1 of type "short_answer": {{"concept": "<one of the concepts>", "type": "short_answer", "question": "...", "answer_guide": "<key points a correct answer must contain>"}}

Rules: each question probes a different concept; MCQs have exactly 4 options with
one clearly correct; difficulty is introductory-to-intermediate (this is a placement
diagnostic, not an exam)."""

_GRADE_PROMPT = """You are grading a short-answer response on "{concept}".

Question: {question}
Key points a correct answer contains: {guide}
Student's answer: {answer}

Don't just mark it wrong — diagnose WHY. Look for the underlying reasoning error
(a wrong mental model, a confused prerequisite, an overgeneralized rule), not the
surface mistake.

Return JSON only (no fences): {{"score": <0.0-1.0>,
"feedback": "<1-2 sentences addressed to the student — name the reasoning error if there is one, not just the wrong answer>",
"misconception": "<the wrong mental model behind the mistake, phrased as what the student seems to believe, or null if none>"}}"""


def _extract_json_value(raw: str):
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise ValueError(f"No JSON in model output: {raw[:200]}")
    end = max(text.rfind("]"), text.rfind("}"))
    payload = text[start : end + 1]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        # models emit LaTeX-ish lone backslashes ("\tau") — escape and retry
        return json.loads(re.sub(r'\\(?![\\/"bfnrtu])', r"\\\\", payload))


async def generate_quiz(subject: str, concept_names: list[str], n: int = 6) -> list[QuizQuestion]:
    raw = await call_model(
        Task.generate_quiz,
        [
            {
                "role": "user",
                "content": _QUIZ_PROMPT.format(
                    subject=subject,
                    concepts=", ".join(concept_names[:n]),
                    n=n,
                    n_mcq=n - 1,
                ),
            }
        ],
    )
    questions = [QuizQuestion.model_validate(q) for q in _extract_json_value(raw)]
    return questions


async def start_assessment(db: AsyncSession, user_id: int, subject: str) -> dict:
    concepts = (
        await db.scalars(
            select(Concept).where(Concept.user_id == user_id, Concept.subject == subject)
        )
    ).all()
    if not concepts:
        raise ValueError(f"No concepts seeded for user {user_id} in {subject!r} — onboard first")

    questions = await generate_quiz(subject, [c.name for c in concepts])
    assessment_id = uuid.uuid4().hex
    store.set(
        f"assessment:{assessment_id}",
        {
            "user_id": user_id,
            "subject": subject,
            "questions": [q.model_dump() for q in questions],
            "answered": {},
        },
    )
    # Client-facing copy: never leak correct_index / answer_guide.
    public = [
        {"index": i, "concept": q.concept, "type": q.type, "question": q.question, "options": q.options}
        for i, q in enumerate(questions)
    ]
    return {"assessment_id": assessment_id, "questions": public}


async def _update_confidence(
    db: AsyncSession, user_id: int, subject: str, concept_name: str, score: float
) -> float | None:
    concept = await db.scalar(
        select(Concept).where(
            Concept.user_id == user_id,
            Concept.subject == subject,
            Concept.name == concept_name,
        )
    )
    if concept is None:
        return None
    state = await db.get(LearnerConceptState, (user_id, concept.id))
    if state is None:
        state = LearnerConceptState(user_id=user_id, concept_id=concept.id)
        db.add(state)
    state.confidence = round(
        (1 - _EVIDENCE_WEIGHT) * (state.confidence or 0.0) + _EVIDENCE_WEIGHT * score, 4
    )
    state.last_reviewed = datetime.now(timezone.utc)
    await db.commit()
    return state.confidence


async def grade_answer(
    db: AsyncSession, assessment_id: str, question_index: int, answer: str
) -> dict:
    key = f"assessment:{assessment_id}"
    session = store.get(key)
    if session is None:
        raise ValueError("Unknown or expired assessment")
    q = QuizQuestion.model_validate(session["questions"][question_index])

    misconception = None
    if q.type == "mcq":
        # Deterministic — zero model calls.
        try:
            chosen = int(answer)
        except ValueError:
            chosen = q.options.index(answer) if answer in q.options else -1
        score = 1.0 if chosen == q.correct_index else 0.0
        feedback = (
            "Correct!"
            if score == 1.0
            else f"Not quite — the correct answer is: {q.options[q.correct_index]}"
        )
    else:
        raw = await call_model(
            Task.grade_answer,
            [
                {
                    "role": "user",
                    "content": _GRADE_PROMPT.format(
                        concept=q.concept, question=q.question, guide=q.answer_guide, answer=answer
                    ),
                }
            ],
        )
        graded = _extract_json_value(raw)
        score = max(0.0, min(1.0, float(graded.get("score", 0.0))))
        feedback = graded.get("feedback", "")
        misconception = graded.get("misconception")

    updated = await _update_confidence(
        db, session["user_id"], session["subject"], q.concept, score
    )
    if misconception:
        await append_misconception(db, session["user_id"], session["subject"], q.concept, misconception)

    session["answered"][str(question_index)] = score
    store.set(key, session)
    return {
        "score": score,
        "feedback": feedback,
        "misconception": misconception,
        "concept": q.concept,
        "updated_confidence": updated,
        "answered": len(session["answered"]),
        "total": len(session["questions"]),
    }


async def append_misconception(
    db: AsyncSession, user_id: int, subject: str, concept_name: str, misconception: str
) -> None:
    concept = await db.scalar(
        select(Concept).where(
            Concept.user_id == user_id,
            Concept.subject == subject,
            Concept.name == concept_name,
        )
    )
    if concept is None:
        return
    state = await db.get(LearnerConceptState, (user_id, concept.id))
    if state is None:
        state = LearnerConceptState(user_id=user_id, concept_id=concept.id)
        db.add(state)
    entries = list(state.misconceptions or [])
    entries.append(
        {"text": misconception, "detected_at": datetime.now(timezone.utc).isoformat(), "resolved": False}
    )
    state.misconceptions = entries
    await db.commit()
