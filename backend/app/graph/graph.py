from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.graph import nodes
from app.graph.state import EdumindState


def build_graph(checkpointer=None):
    """Router → conditional edge on classified mode → feature node.

    Teaching and assessment feed the misconception tracker before ending
    (it runs after every teach/assess turn per spec). Branching uses
    per-branch thread_ids against the same compiled graph — the checkpointer
    keys state by thread_id, so no extra plumbing is needed here.
    """
    g = StateGraph(EdumindState)

    g.add_node("router", nodes.router_node)
    g.add_node("diagnostic", nodes.diagnostic_node)
    g.add_node("teaching", nodes.teaching_node)
    g.add_node("branch", nodes.branch_node)
    g.add_node("image", nodes.image_node)
    g.add_node("simulation", nodes.simulation_node)
    g.add_node("misconception", nodes.misconception_node)
    g.add_node("revision", nodes.revision_node)
    g.add_node("twin_updater", nodes.twin_updater_node)

    g.set_entry_point("router")
    g.add_conditional_edges(
        "router",
        lambda s: s["mode"],
        {
            "teach": "teaching",
            "assess": "diagnostic",
            "branch": "branch",
            "diagram": "image",
            "revise": "revision",
            "end_session": "twin_updater",
        },
    )

    g.add_edge("teaching", "misconception")
    g.add_edge("diagnostic", "misconception")
    g.add_edge("misconception", END)
    g.add_edge("branch", END)
    g.add_edge("image", END)
    g.add_edge("simulation", END)
    g.add_edge("revision", END)
    g.add_edge("twin_updater", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())
