"""Branch-based learning over LangGraph checkpoint threads.

Opening a branch = copying the parent thread's checkpointed state into a fresh
thread_id (LangGraph's checkpointer keys state by thread, so this IS the fork —
no hand-rolled snapshots). Returning to the lesson is just the client switching
its active thread pointer back; re-entering the branch resumes its thread.
Branches nest naturally: the parent thread can itself be a branch thread.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, LessonBlock
from app.models.router import Task, call_model

_BRANCH_PROMPT = """A student paused a lesson to ask a side-question about one specific part.

The lesson block they clicked ({block_type}):
{block_content}

Recent conversation:
{history}

Their side-question: {question}

Answer the side-question directly and concisely in markdown. Stay on this
sub-topic — do not re-teach the whole lesson. End by checking the question is
resolved (one short line)."""


def _history_tail(state_values: dict, limit: int = 6) -> str:
    history = state_values.get("message_history") or []
    tail = history[-limit:]
    return "\n".join(f"{m['role']}: {m['content'][:400]}" for m in tail) or "(start of session)"


async def open_branch(
    db: AsyncSession,
    graph,
    user_id: int,
    session_id: int,
    parent_block_id: int | None,
    question: str,
    parent_thread_id: str,
    concept_id: int | None = None,
) -> dict:
    """Anchored branch (parent_block_id set) or a free-form 'new chat' under a
    concept (parent_block_id None + concept_id set)."""
    block = None
    if parent_block_id is not None:
        block = await db.get(LessonBlock, parent_block_id)
        if block is None:
            raise ValueError(f"Lesson block {parent_block_id} not found")

    parent_cfg = {"configurable": {"thread_id": parent_thread_id}}
    parent_state = await graph.aget_state(parent_cfg)
    parent_values = dict(parent_state.values) if parent_state and parent_state.values else {}

    thread_id = f"branch-{uuid.uuid4().hex[:12]}"
    branch_cfg = {"configurable": {"thread_id": thread_id}}

    anchor_concept_id = block.concept_id if block else concept_id

    # Fork: copy the parent checkpoint into the new thread. message_history is
    # an add-reducer; the branch thread is empty, so this write copies it whole.
    seed = {
        "user_id": user_id,
        "session_id": session_id,
        "current_concept_id": anchor_concept_id,
        "mode": "branch",
        "message_history": list(parent_values.get("message_history") or []),
    }
    await graph.aupdate_state(branch_cfg, seed, as_node="__start__")

    if block is not None:
        prompt = _BRANCH_PROMPT.format(
            block_type=block.type,
            block_content=block.content,
            history=_history_tail(parent_values),
            question=question,
        )
    else:
        concept_name = ""
        if anchor_concept_id:
            from app.models import Concept

            concept = await db.get(Concept, anchor_concept_id)
            concept_name = concept.name if concept else ""
        prompt = (
            f"A student opened a fresh conversation while studying"
            f"{f' {concept_name!r}' if concept_name else ''}.\n"
            f"Recent context:\n{_history_tail(parent_values)}\n\n"
            f"Their message: {question}\n\n"
            "Reply as a great tutor in markdown — answer exactly what they asked, "
            "concise, and end with one short check-in question."
        )

    answer = await call_model(Task.teach_concept, [{"role": "user", "content": prompt}])

    branch = Branch(
        parent_block_id=parent_block_id,
        concept_id=anchor_concept_id,
        question=question,
        response=answer,
        thread_id=thread_id,
    )
    db.add(branch)
    await db.commit()

    await graph.aupdate_state(
        branch_cfg,
        {
            "active_branch_id": branch.id,
            "message_history": [
                {"role": "user", "content": question},
                {"role": "bot", "content": answer},
            ],
        },
        as_node="__start__",
    )
    return {
        "branch_id": branch.id,
        "thread_id": thread_id,
        "question": question,
        "response": answer,
    }


async def continue_branch(db: AsyncSession, graph, branch_id: int, message: str) -> dict:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise ValueError(f"Branch {branch_id} not found")

    branch_cfg = {"configurable": {"thread_id": branch.thread_id}}
    state = await graph.aget_state(branch_cfg)
    values = dict(state.values) if state and state.values else {}

    parent_block = await db.get(LessonBlock, branch.parent_block_id)
    answer = await call_model(
        Task.teach_concept,
        [
            {
                "role": "user",
                "content": _BRANCH_PROMPT.format(
                    block_type=parent_block.type if parent_block else "lesson",
                    block_content=parent_block.content if parent_block else "",
                    history=_history_tail(values),
                    question=message,
                ),
            }
        ],
    )
    await graph.aupdate_state(
        branch_cfg,
        {
            "message_history": [
                {"role": "user", "content": message},
                {"role": "bot", "content": answer},
            ]
        },
        as_node="__start__",
    )
    return {"branch_id": branch_id, "thread_id": branch.thread_id, "response": answer}


async def branch_history(graph, thread_id: str) -> list[dict]:
    """Full conversation of a branch thread — used when re-entering."""
    state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if not state or not state.values:
        return []
    return list(state.values.get("message_history") or [])
