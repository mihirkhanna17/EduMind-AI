"""LangGraph nodes. Stubs are replaced phase by phase — the graph shape
stays fixed.
"""

from __future__ import annotations

import json

from app.graph.state import EdumindState
from app.models.router import Task, call_model

VALID_MODES = {"teach", "assess", "branch", "diagram", "revise", "end_session"}

_CLASSIFY_SYSTEM = """You classify a student's message into exactly one mode for a tutoring system.
Modes:
- teach: wants a concept explained, a lesson, or to continue learning
- assess: wants a quiz/test, or is answering an assessment question
- branch: a side-question about something inside the current lesson ("wait, why...", "what if...")
- diagram: about an image/diagram/figure (uploading, pointing at, or asking about one)
- revise: wants to review/revise previously learned material or spaced repetition
- end_session: is done for now ("that's all", "bye", "end session")

Reply with the mode word only, nothing else."""


async def router_node(state: EdumindState) -> dict:
    """Cheap-model intent classification → sets state['mode']."""
    raw = await call_model(
        Task.classify_intent,
        [
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": state.get("user_message", "")},
        ],
    )
    mode = raw.strip().lower().split()[0] if raw.strip() else "teach"
    if mode not in VALID_MODES:
        mode = "teach"
    return {
        "mode": mode,
        "message_history": [{"role": "user", "content": state.get("user_message", "")}],
    }


# --- Stubs, replaced in later phases -------------------------------------

async def diagnostic_node(state: EdumindState) -> dict:
    """Assessment runs over its own REST endpoints (/assessment/start, /answer)
    so the frontend can render a proper quiz UI. In chat, this node hands off."""
    return {
        "response": (
            "Let's check where you stand. Starting a short diagnostic quiz — "
            "answer a few questions and I'll map your current level."
        ),
        "message_history": [{"role": "bot", "content": "[started diagnostic assessment]"}],
    }


_CHAT_TEACH_PROMPT = """You are Edumind's teaching agent in an ongoing tutoring conversation.
{concept_line}
Recent conversation:
{history}

Student's message: {message}

Answer the student's actual message — if they asked about something different from
the current concept, teach what they asked about; do not steer back. Reply as a
great tutor in markdown, focused (under 250 words), and end with one short
check-in question."""


async def teaching_node(state: EdumindState) -> dict:
    """Conversational teaching for chat-classified 'teach' turns. Answers the
    student's actual message with conversation history as context. (The full
    7-block pedagogical lesson runs on the explicit /teach/stream path.)"""
    from app.db import SessionLocal
    from app.models import Concept

    concept_line = ""
    concept_id = state.get("current_concept_id")
    if concept_id:
        async with SessionLocal() as db:
            concept = await db.get(Concept, concept_id)
        if concept:
            concept_line = f"Concept currently open on their canvas: {concept.name} ({concept.subject})."

    history = state.get("message_history") or []
    tail = "\n".join(f"{m['role']}: {m['content'][:350]}" for m in history[-8:]) or "(start of session)"

    answer = await call_model(
        Task.teach_concept,
        [
            {
                "role": "user",
                "content": _CHAT_TEACH_PROMPT.format(
                    concept_line=concept_line,
                    history=tail,
                    message=state.get("user_message", ""),
                ),
            }
        ],
    )
    return {
        "response": answer,
        "message_history": [{"role": "bot", "content": answer}],
    }


async def branch_node(state: EdumindState) -> dict:
    """Chat-detected side-question: answer it inline on the current thread.
    (Block-anchored branches with true thread-forking go through POST /branches,
    which copies this thread's checkpoint into a new thread_id.)"""
    history = state.get("message_history") or []
    tail = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in history[-6:])
    answer = await call_model(
        Task.teach_concept,
        [
            {
                "role": "user",
                "content": (
                    "A student asked a side-question during a lesson.\n"
                    f"Recent conversation:\n{tail or '(none)'}\n\n"
                    f"Side-question: {state.get('user_message', '')}\n\n"
                    "Answer it directly and concisely in markdown without re-teaching the lesson."
                ),
            }
        ],
    )
    return {
        "response": answer,
        "message_history": [{"role": "bot", "content": answer}],
    }


async def image_node(state: EdumindState) -> dict:
    """Chat-classified diagram intent: the heavy lifting (upload/fetch/crop)
    happens over the /images endpoints so the canvas can render overlays;
    this node guides the student there."""
    return {
        "response": (
            "Let's look at it visually. Upload the diagram (or ask me to fetch/draw "
            "one) and it will appear on your canvas — then click any region to ask "
            "about it."
        ),
        "message_history": [{"role": "bot", "content": "[image intent → canvas]"}],
    }


async def simulation_node(state: EdumindState) -> dict:
    """Serves (or generates once) the concept's cached simulation. Triggered
    via /simulations by the frontend when the Teaching Agent flags a concept
    as better shown than described."""
    from app.db import SessionLocal
    from app.services.simulations import get_or_generate

    concept_id = state.get("current_concept_id")
    if not concept_id:
        return {"response": "Pick a concept first and I'll build a simulation for it."}
    async with SessionLocal() as db:
        row, cached = await get_or_generate(db, state["user_id"], concept_id)
    note = "(from cache)" if cached else "(freshly generated)"
    return {
        "response": f"Simulation ready {note} — opening it on your canvas.",
        "message_history": [{"role": "bot", "content": f"[simulation {row.id} ready]"}],
    }


_MISCONCEPTION_PROMPT = """A student is learning "{concept}". Below is their latest message.
Decide if it reveals a WRONG MENTAL MODEL (a misconception), not merely a question
or missing knowledge.

Student message: {message}

Return JSON only: {{"misconception": "<short description of the wrong model>" or null}}"""


async def misconception_node(state: EdumindState) -> dict:
    """Cheap-model check after every teach/assess turn; appends to
    learner_concept_state.misconceptions when a wrong mental model shows."""
    from app.db import SessionLocal
    from app.models import Concept
    from app.services.assessment import _extract_json_value, append_misconception

    concept_id = state.get("current_concept_id")
    message = state.get("user_message", "")
    if not concept_id or len(message.split()) < 4:  # too short to reveal a model
        return {}

    async with SessionLocal() as db:
        concept = await db.get(Concept, concept_id)
        if concept is None:
            return {}
        raw = await call_model(
            Task.track_misconception,
            [
                {
                    "role": "user",
                    "content": _MISCONCEPTION_PROMPT.format(
                        concept=concept.name, message=message
                    ),
                }
            ],
        )
        try:
            found = _extract_json_value(raw).get("misconception")
        except (ValueError, AttributeError, json.JSONDecodeError):
            return {}
        if found:
            await append_misconception(
                db, state["user_id"], concept.subject, concept.name, found
            )
    return {}


async def revision_node(state: EdumindState) -> dict:
    """Pure logic — surfaces due concepts from the SM-2 scheduler."""
    from app.db import SessionLocal
    from app.services.revision import due_concepts

    async with SessionLocal() as db:
        due = await due_concepts(db, state["user_id"])
    if not due:
        response = "Nothing is due for revision right now — you're all caught up."
    else:
        lines = "\n".join(
            f"- **{d['name']}** ({d['subject']}) — {d['overdue_days']} days overdue"
            for d in due[:8]
        )
        response = f"Due for revision:\n{lines}\n\nPick one and we'll run a quick review."
    return {
        "response": response,
        "message_history": [{"role": "bot", "content": response}],
    }


async def twin_updater_node(state: EdumindState) -> dict:
    """Session end via chat: one batched snapshot, same path as /sessions/end."""
    from app.db import SessionLocal
    from app.services.twin import build_snapshot

    async with SessionLocal() as db:
        snapshot = await build_snapshot(db, state["user_id"], state.get("session_id"))
    response = (
        f"Session wrapped up — your learning twin is updated to v{snapshot.version}. "
        "Check the dashboard to see how you've changed."
    )
    return {
        "response": response,
        "message_history": [{"role": "bot", "content": response}],
    }
