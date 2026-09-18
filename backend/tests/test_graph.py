"""Phase 3 verification: router node classifies (mocked model) and the
conditional edge dispatches to the right feature node."""

import pytest

import app.graph.nodes as nodes
from app.graph.graph import build_graph


def mock_classifier(monkeypatch, reply: str):
    async def fake_call_model(task, messages):
        return reply

    monkeypatch.setattr(nodes, "call_model", fake_call_model)
    # end_session reaches the twin updater — its batched call must be mocked too
    import app.services.twin as twin_svc

    monkeypatch.setattr(twin_svc, "call_model", fake_call_model)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "classified, expected_fragment",
    [
        ("teach", "teach"),  # conversational node echoes the mocked model reply
        ("assess", "diagnostic quiz"),
        ("branch", "branch"),  # inline answer comes from the mocked model
        ("diagram", "canvas"),  # live node guides to the canvas/image endpoints
        ("revise", "revision"),  # live node: either due list or caught-up message
        ("end_session", "twin is updated"),
    ],
)
async def test_router_dispatches_to_mode_node(monkeypatch, classified, expected_fragment):
    mock_classifier(monkeypatch, classified)
    graph = build_graph()

    result = await graph.ainvoke(
        {"user_id": 1, "session_id": 1, "user_message": "anything"},
        config={"configurable": {"thread_id": "t1"}},
    )

    assert result["mode"] == classified
    assert expected_fragment in result["response"]


@pytest.mark.asyncio
async def test_garbage_classification_falls_back_to_teach(monkeypatch):
    mock_classifier(monkeypatch, "??? no idea ???")
    graph = build_graph()

    result = await graph.ainvoke(
        {"user_id": 1, "session_id": 1, "user_message": "hm"},
        config={"configurable": {"thread_id": "t2"}},
    )

    assert result["mode"] == "teach"


@pytest.mark.asyncio
async def test_threads_are_isolated_by_thread_id(monkeypatch):
    """Foundation for Phase 7 branching: different thread_ids don't share state."""
    mock_classifier(monkeypatch, "teach")
    graph = build_graph()

    await graph.ainvoke(
        {"user_id": 1, "session_id": 1, "user_message": "main lesson"},
        config={"configurable": {"thread_id": "main"}},
    )
    await graph.ainvoke(
        {"user_id": 1, "session_id": 1, "user_message": "branch question"},
        config={"configurable": {"thread_id": "branch-1"}},
    )

    main_state = graph.get_state({"configurable": {"thread_id": "main"}})
    branch_state = graph.get_state({"configurable": {"thread_id": "branch-1"}})

    main_msgs = [m["content"] for m in main_state.values["message_history"] if m["role"] == "user"]
    branch_msgs = [m["content"] for m in branch_state.values["message_history"] if m["role"] == "user"]
    assert main_msgs == ["main lesson"]
    assert branch_msgs == ["branch question"]
