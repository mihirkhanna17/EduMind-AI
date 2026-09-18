"""Phase 2 verification: routing map + streaming, with fastapi_poe mocked."""

import pytest

import app.models.router as router
from app.models.router import ROUTES, Task, call_model, stream_model


class FakePartial:
    def __init__(self, text, replace=False):
        self.text = text
        self.is_replace_response = replace


def make_fake_get_bot_response(captured, chunks=None):
    async def fake(messages, bot_name, api_key):
        captured["bot_name"] = bot_name
        captured["api_key"] = api_key
        captured["messages"] = messages
        for chunk in chunks or [FakePartial("Hello"), FakePartial(" "), FakePartial("world")]:
            yield chunk

    return fake


def test_every_task_has_a_route():
    assert set(ROUTES) == set(Task)
    assert all(isinstance(bot, str) and bot for bot in ROUTES.values())


def test_cheap_tasks_use_cheap_model():
    for task in (Task.classify_intent, Task.generate_quiz, Task.track_misconception):
        assert ROUTES[task] == "GPT-5-mini"


@pytest.mark.asyncio
async def test_replace_response_discards_thinking_text(monkeypatch):
    """Reasoning bots stream 'Thinking...' then replace it with the answer."""
    captured = {}
    chunks = [
        FakePartial("Thinking... (1s elapsed)"),
        FakePartial("The answer", replace=True),
        FakePartial(" is 42."),
    ]
    monkeypatch.setattr(router.fp, "get_bot_response", make_fake_get_bot_response(captured, chunks))
    monkeypatch.setattr(router.settings, "poe_api_key", "test-key")

    result = await call_model(Task.classify_intent, [{"role": "user", "content": "x"}])
    assert result == "The answer is 42."


@pytest.mark.asyncio
async def test_call_model_routes_to_mapped_bot(monkeypatch):
    captured = {}
    monkeypatch.setattr(router.fp, "get_bot_response", make_fake_get_bot_response(captured))
    monkeypatch.setattr(router.settings, "poe_api_key", "test-key")

    result = await call_model(Task.teach_concept, [{"role": "user", "content": "hi"}])

    assert result == "Hello world"
    assert captured["bot_name"] == ROUTES[Task.teach_concept]
    assert captured["api_key"] == "test-key"
    assert captured["messages"][0].role == "user"


@pytest.mark.asyncio
async def test_stream_model_yields_deltas(monkeypatch):
    captured = {}
    monkeypatch.setattr(router.fp, "get_bot_response", make_fake_get_bot_response(captured))
    monkeypatch.setattr(router.settings, "poe_api_key", "test-key")

    deltas = [d["text"] async for d in stream_model(Task.classify_intent, [{"role": "user", "content": "x"}])]

    assert deltas == ["Hello", " ", "world"]
    assert captured["bot_name"] == "GPT-5-mini"


@pytest.mark.asyncio
async def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(router.settings, "poe_api_key", "")
    with pytest.raises(RuntimeError, match="POE_API_KEY"):
        await call_model(Task.classify_intent, [{"role": "user", "content": "x"}])
