"""Phase 9 verification: one-time segmentation, crop-cache hit behavior,
region Q&A as text-only, generated diagrams needing zero vision calls."""

import json

import pytest
from sqlalchemy import select

import app.services.images as images_svc
from app.db import SessionLocal
from app.models import CropCache, Diagram
from app.services.images import (
    ask_about_region,
    crop_cache_key,
    describe_crop,
    generate_diagram,
    ingest_uploaded_image,
    segment_image,
)

REGIONS_JSON = json.dumps(
    [
        {"label": "Nucleus", "bbox": [0.4, 0.35, 0.2, 0.2], "description": "Control center holding DNA."},
        {"label": "Mitochondrion", "bbox": [0.1, 0.6, 0.15, 0.1], "description": "Produces ATP."},
    ]
)

GENERATED = """<<<svg>>>
<svg viewBox="0 0 800 600"><rect x="100" y="100" width="200" height="100" fill="#4a90d9"/><text x="120" y="160">Client</text></svg>
<<<regions>>>
[{"label": "Client", "bbox": [0.125, 0.167, 0.25, 0.167], "description": "The initiating host."}]"""


def mock_vision(monkeypatch, reply, counter):
    async def fake_vision(task, prompt, image_path=None, image_url=None):
        counter["vision"] += 1
        counter["last_prompt"] = prompt
        return reply

    monkeypatch.setattr(images_svc, "call_model_vision", fake_vision)


def mock_text(monkeypatch, reply, counter):
    async def fake_text(task, messages):
        counter["text"] += 1
        counter["last_text_prompt"] = messages[0]["content"]
        return reply

    monkeypatch.setattr(images_svc, "call_model", fake_text)


@pytest.mark.asyncio
async def test_upload_segments_once_and_regions_cached(monkeypatch):
    counter = {"vision": 0, "text": 0}
    mock_vision(monkeypatch, REGIONS_JSON, counter)

    async with SessionLocal() as db:
        diagram = await ingest_uploaded_image(db, "cell.png", b"\x89PNG fake")
        assert counter["vision"] == 1
        assert [r["label"] for r in diagram.regions] == ["Nucleus", "Mitochondrion"]
        assert diagram.image_url.startswith("/media/")

        # reading regions later = pure DB, no model involvement
        again = await db.get(Diagram, diagram.id)
        assert len(again.regions) == 2
        assert counter["vision"] == 1


@pytest.mark.asyncio
async def test_region_question_is_text_only(monkeypatch):
    counter = {"vision": 0, "text": 0}
    mock_vision(monkeypatch, REGIONS_JSON, counter)
    mock_text(monkeypatch, "Because it hosts oxidative phosphorylation.", counter)

    async with SessionLocal() as db:
        diagram = await ingest_uploaded_image(db, "cell2.png", b"\x89PNG fake")
        answer = await ask_about_region(diagram, "mitochondrion", "why is it called the powerhouse?")

    assert "oxidative" in answer
    assert counter["vision"] == 1  # only the ingest call
    assert counter["text"] == 1
    assert "Produces ATP." in counter["last_text_prompt"]  # grounded in cached description


@pytest.mark.asyncio
async def test_crop_cache_second_similar_crop_is_free(monkeypatch):
    counter = {"vision": 0, "text": 0}
    mock_vision(monkeypatch, REGIONS_JSON, counter)

    async with SessionLocal() as db:
        diagram = await ingest_uploaded_image(db, "cell3.png", b"\x89PNG fake")
        mock_vision(monkeypatch, "That area shows the rough endoplasmic reticulum.", counter)

        d1, cached1 = await describe_crop(db, diagram, [0.201, 0.302, 0.1, 0.1])
        # a *slightly* different box rounds to the same key → cache hit
        d2, cached2 = await describe_crop(db, diagram, [0.199, 0.298, 0.104, 0.096])

    assert cached1 is False and cached2 is True
    assert d1 == d2
    assert counter["vision"] == 2  # 1 ingest + 1 crop, not 3

    assert crop_cache_key(1, [0.201, 0.302, 0.1, 0.1]) == crop_cache_key(1, [0.2, 0.3, 0.1, 0.1])
    assert crop_cache_key(1, [0.2, 0.3, 0.1, 0.1]) != crop_cache_key(2, [0.2, 0.3, 0.1, 0.1])


@pytest.mark.asyncio
async def test_generated_diagram_uses_zero_vision_calls(monkeypatch):
    counter = {"vision": 0, "text": 0}
    mock_vision(monkeypatch, REGIONS_JSON, counter)
    mock_text(monkeypatch, GENERATED, counter)

    async with SessionLocal() as db:
        diagram = await generate_diagram(db, "TCP three-way handshake")

    assert counter["vision"] == 0
    assert counter["text"] == 1
    assert diagram.source == "generated"
    assert diagram.image_url.endswith(".svg")
    assert diagram.regions[0]["label"] == "Client"
    svg_path = images_svc.MEDIA_DIR / diagram.image_url.split("/")[-1]
    assert svg_path.read_text(encoding="utf-8").startswith("<svg")


@pytest.mark.asyncio
async def test_segment_rejects_non_list(monkeypatch):
    counter = {"vision": 0}
    mock_vision(monkeypatch, '{"not": "a list"}', counter)
    with pytest.raises(ValueError):
        await segment_image(image_url="https://example.com/x.png")
