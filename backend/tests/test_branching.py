"""Phase 7 verification: branch = forked checkpoint thread; parent thread
untouched; branches resume independently; nesting works."""

import uuid

import pytest

import app.services.branching as branching_svc
from app.db import SessionLocal
from app.graph.graph import build_graph
from app.models import LessonBlock, Session, User
from app.services.branching import branch_history, continue_branch, open_branch
from app.services.onboarding import seed_concepts_for_user
from app.services.subject_templates import get_template, seed_builtin_templates


async def setup_lesson():
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
        user = User(email=f"branch-{uuid.uuid4().hex[:10]}@example.com", name="B")
        db.add(user)
        await db.commit()
        template = await get_template(db, "Computer Science")
        concepts = await seed_concepts_for_user(db, user.id, template)
        session = Session(user_id=user.id, mode="teach")
        db.add(session)
        await db.commit()
        block = LessonBlock(
            session_id=session.id,
            concept_id=concepts[0].id,
            type="theory",
            content="An array stores elements contiguously; indexing is O(1).",
        )
        db.add(block)
        await db.commit()
        return user.id, session.id, block.id


def mock_branch_answers(monkeypatch, answers):
    calls = {"prompts": []}

    async def fake_call_model(task, messages):
        calls["prompts"].append(messages[0]["content"])
        return answers[len(calls["prompts"]) - 1]

    monkeypatch.setattr(branching_svc, "call_model", fake_call_model)
    return calls


@pytest.mark.asyncio
async def test_branch_forks_thread_and_parent_stays_clean(monkeypatch):
    calls = mock_branch_answers(monkeypatch, ["Because indexing is pointer math."])
    user_id, session_id, block_id = await setup_lesson()
    graph = build_graph()
    main_thread = f"session-{session_id}"

    # seed the main thread with some lesson history
    await graph.aupdate_state(
        {"configurable": {"thread_id": main_thread}},
        {
            "user_id": user_id,
            "session_id": session_id,
            "message_history": [{"role": "bot", "content": "lesson: arrays are contiguous"}],
        },
        as_node="__start__",
    )

    async with SessionLocal() as db:
        result = await open_branch(
            db, graph, user_id, session_id, block_id, "why O(1)?", main_thread
        )

    assert result["response"] == "Because indexing is pointer math."
    assert result["thread_id"].startswith("branch-")
    # the model saw the clicked block's content and the inherited history
    assert "contiguously" in calls["prompts"][0]
    assert "lesson: arrays are contiguous" in calls["prompts"][0]

    # branch thread: inherited history + its own Q/A
    branch_msgs = await branch_history(graph, result["thread_id"])
    contents = [m["content"] for m in branch_msgs]
    assert contents == [
        "lesson: arrays are contiguous",
        "why O(1)?",
        "Because indexing is pointer math.",
    ]

    # parent thread must NOT contain the branch conversation
    parent_state = await graph.aget_state({"configurable": {"thread_id": main_thread}})
    parent_contents = [m["content"] for m in parent_state.values["message_history"]]
    assert parent_contents == ["lesson: arrays are contiguous"]


@pytest.mark.asyncio
async def test_reentering_branch_resumes_and_nesting_inherits(monkeypatch):
    calls = mock_branch_answers(
        monkeypatch, ["First answer.", "Follow-up answer.", "Nested answer."]
    )
    user_id, session_id, block_id = await setup_lesson()
    graph = build_graph()
    main_thread = f"session-{session_id}"

    async with SessionLocal() as db:
        b1 = await open_branch(db, graph, user_id, session_id, block_id, "q1?", main_thread)
        # re-enter the branch later and continue it
        r2 = await continue_branch(db, graph, b1["branch_id"], "but what about caches?")
        assert r2["response"] == "Follow-up answer."
        # follow-up prompt included the branch's own prior conversation
        assert "q1?" in calls["prompts"][1] and "First answer." in calls["prompts"][1]

        # branch of a branch: fork FROM the branch thread
        b2 = await open_branch(
            db, graph, user_id, session_id, block_id, "nested q?", b1["thread_id"]
        )

    nested_msgs = [m["content"] for m in await branch_history(graph, b2["thread_id"])]
    # inherited the full branch-1 conversation, then its own Q/A
    assert nested_msgs == [
        "q1?",
        "First answer.",
        "but what about caches?",
        "Follow-up answer.",
        "nested q?",
        "Nested answer.",
    ]
    # branch-1 unaffected by the nested branch
    b1_msgs = [m["content"] for m in await branch_history(graph, b1["thread_id"])]
    assert b1_msgs == ["q1?", "First answer.", "but what about caches?", "Follow-up answer."]
