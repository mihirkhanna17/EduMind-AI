"""Single entry point for every LLM call in Edumind.

Feature code never imports fastapi_poe directly — it declares *what* it is doing
(a Task), and this module decides which Poe bot pays for it. This is the
cost-control choke point: change a route here, the whole app follows.
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator

import fastapi_poe as fp

from app.config import settings


class Task(str, enum.Enum):
    classify_intent = "classify_intent"    # cheap — every turn
    grade_answer = "grade_answer"          # needs judgment
    teach_concept = "teach_concept"        # main pedagogy + simulation codegen
    generate_quiz = "generate_quiz"        # structured output, cheap
    diagram_segment = "diagram_segment"    # vision, once per image — cached forever
    twin_summarize = "twin_summarize"      # batched, once per session end
    track_misconception = "track_misconception"  # cheap, after teach/assess turns
    onboard_dynamic = "onboard_dynamic"    # structured JSON for unknown subjects
    classify_visual = "classify_visual"    # cheap — does this concept need a visual?


# NOTE: spec called for Claude-Sonnet-5 (mid-tier) and GPT-5.6-Sol (vision),
# but both reject Poe API access ("This bot does not support API access",
# verified 2026-07-16 via probe_bots.py). Nearest working equivalents are
# substituted; revert these two lines when Poe enables them.
ROUTES: dict[Task, str] = {
    Task.classify_intent: "GPT-5-mini",
    Task.grade_answer: "Claude-Sonnet-4.5",
    Task.teach_concept: "Claude-Sonnet-4.5",
    Task.generate_quiz: "GPT-5-mini",
    Task.diagram_segment: "Gemini-2.5-Flash",
    Task.twin_summarize: "Claude-Sonnet-4.5",
    Task.track_misconception: "GPT-5-mini",
    Task.onboard_dynamic: "Claude-Sonnet-4.5",
    Task.classify_visual: "GPT-5-mini",
}


def _to_protocol_messages(messages: list[dict]) -> list[fp.ProtocolMessage]:
    """messages: [{"role": "system"|"user"|"bot", "content": str, "attachments": [...]?}]"""
    out = []
    for m in messages:
        out.append(
            fp.ProtocolMessage(
                role=m["role"],
                content=m["content"],
                attachments=m.get("attachments") or [],
            )
        )
    return out


def _require_key() -> str:
    if not settings.poe_api_key:
        raise RuntimeError(
            "POE_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and add your Poe API key."
        )
    return settings.poe_api_key


async def stream_model(task: Task, messages: list[dict]) -> AsyncIterator[dict]:
    """Stream response events for the bot mapped to `task`.

    Yields {"text": str, "replace": bool}. `replace: True` means the bot
    replaced everything streamed so far (Poe's is_replace_response — e.g.
    reasoning bots stream "Thinking..." then swap in the real answer).
    Consumers must reset their accumulated text on replace."""
    bot = ROUTES[task]
    api_key = _require_key()
    async for partial in fp.get_bot_response(
        messages=_to_protocol_messages(messages),
        bot_name=bot,
        api_key=api_key,
    ):
        if getattr(partial, "is_suggested_reply", False):
            continue
        replace = bool(getattr(partial, "is_replace_response", False))
        if partial.text or replace:
            yield {"text": partial.text or "", "replace": replace}


async def call_model(task: Task, messages: list[dict]) -> str:
    """Non-streaming convenience: collect the full response (replace-aware)."""
    chunks: list[str] = []
    async for ev in stream_model(task, messages):
        if ev["replace"]:
            chunks = [ev["text"]]
        else:
            chunks.append(ev["text"])
    return "".join(chunks)


async def call_model_vision(
    task: Task,
    prompt: str,
    *,
    image_path: str | None = None,
    image_url: str | None = None,
) -> str:
    """Vision call: uploads the image as a Poe attachment, then queries the
    bot mapped to `task`. Callers are responsible for caching — vision calls
    are the expensive path and must never repeat for the same image+question."""
    api_key = _require_key()
    if image_path:
        with open(image_path, "rb") as f:
            attachment = await fp.upload_file(file=f, api_key=api_key)
    elif image_url:
        attachment = await fp.upload_file(file_url=image_url, api_key=api_key)
    else:
        raise ValueError("call_model_vision needs image_path or image_url")

    return await call_model(
        task,
        [{"role": "user", "content": prompt, "attachments": [attachment]}],
    )
