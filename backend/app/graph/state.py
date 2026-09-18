from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

Mode = Literal["teach", "assess", "branch", "diagram", "revise", "end_session"]


class EdumindState(TypedDict, total=False):
    user_id: int
    session_id: int
    twin_ref: int | None
    current_concept_id: int | None
    mode: Mode
    # Appended to by nodes; LangGraph merges with operator.add.
    message_history: Annotated[list[dict], operator.add]
    active_branch_id: int | None
    retrieved_context: str | None
    # Per-turn I/O
    user_message: str
    response: str
