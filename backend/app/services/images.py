"""Image Agent: sourcing (upload / web-fetch / generate) + universal crop-and-ask.

Cost rules enforced here:
- ONE vision call per image, on ingest (segmentation) — regions cached forever
  in diagrams.regions; "what is this" clicks are answered from cache, zero calls.
- Generated diagrams get their regions from the same generation call (the model
  knows where it drew things) — zero vision calls ever.
- Arbitrary crops: one vision call, cached in crop_cache keyed by
  sha256(diagram_id : rounded bbox) so similar crops across students are free.
- Questions about a known region are TEXT calls grounded in the cached
  description — never a repeat vision call.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CropCache, Diagram
from app.models.router import Task, call_model, call_model_vision
from app.services.assessment import _extract_json_value

MEDIA_DIR = pathlib.Path(__file__).resolve().parents[2] / "media"
MEDIA_DIR.mkdir(exist_ok=True)

_SEGMENT_PROMPT = """Identify the labeled/meaningful regions of this educational image.

Return a JSON array only (no prose, no fences). Each region:
{"label": "<short name>", "bbox": [x, y, w, h], "description": "<2-3 sentences: what it is and its role in the diagram>"}

bbox values are normalized 0.0-1.0 relative to image width/height (x,y = top-left).
Return 3-12 regions covering the diagram's meaningful parts."""

_CROP_PROMPT = """Look at the region of this image inside the normalized bounding box
[x={x:.2f}, y={y:.2f}, w={w:.2f}, h={h:.2f}] (x,y = top-left, values relative to image size).

Describe what is in that region and its role in the overall diagram, in 2-4 sentences.
Answer with the description only."""

_REGION_QA_PROMPT = """A student is studying a diagram ("{context}") and asked about one region of it.

Region: {label}
What that region shows: {description}

Student's question: {question}

Answer concisely in markdown using the region description and your knowledge.
If the question can't be answered from this region, say which part of the diagram to look at instead."""

_GENERATE_PROMPT = """Create a clean educational SVG diagram: {description}

Output exactly two sections with these markers:

<<<svg>>>
(complete, self-contained <svg> element, viewBox="0 0 800 600", legible text labels,
simple flat colors, no external references)
<<<regions>>>
(JSON array of the meaningful regions YOU drew: [{{"label": "...", "bbox": [x, y, w, h], "description": "..."}}]
with bbox normalized 0.0-1.0 relative to the 800x600 canvas)"""


def _round_bbox(bbox: list[float]) -> list[float]:
    """2-decimal rounding ⇒ crops within ~1% land on the same cache key."""
    return [round(float(v), 2) for v in bbox]


def crop_cache_key(diagram_id: int, bbox: list[float]) -> str:
    payload = f"{diagram_id}:{json.dumps(_round_bbox(bbox))}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def segment_image(image_path: str | None = None, image_url: str | None = None) -> list[dict]:
    """The one-time vision call. Returns validated region dicts."""
    raw = await call_model_vision(
        Task.diagram_segment, _SEGMENT_PROMPT, image_path=image_path, image_url=image_url
    )
    regions = _extract_json_value(raw)
    if not isinstance(regions, list):
        raise ValueError("Segmentation did not return a list")
    return [
        {
            "label": str(r["label"]),
            "bbox": _round_bbox(r["bbox"]),
            "description": str(r["description"]),
        }
        for r in regions
        if r.get("label") and r.get("bbox") and r.get("description")
    ]


async def ingest_uploaded_image(
    db: AsyncSession,
    filename: str,
    data: bytes,
    document_id: int | None = None,
    concept_id: int | None = None,
) -> Diagram:
    ext = pathlib.Path(filename).suffix.lower() or ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    path = MEDIA_DIR / name
    path.write_bytes(data)
    regions = await segment_image(image_path=str(path))
    diagram = Diagram(
        document_id=document_id,
        concept_id=concept_id,
        image_url=f"/media/{name}",
        source="upload",
        regions=regions,
    )
    db.add(diagram)
    await db.commit()
    return diagram


async def search_web_image(query: str) -> str:
    """Web image search → best result URL. Prefers SerpAPI (Google Images),
    falls back to Google Programmable Search if configured."""
    if settings.serpapi_key:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_images",
                    "q": query,
                    "api_key": settings.serpapi_key,
                    "safe": "active",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("images_results") or []
        # prefer a mid-size original that's likely a diagram, not a thumbnail
        for r in results[:8]:
            url = r.get("original")
            if url and url.lower().split("?")[0].endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                return url
        if results:
            return results[0].get("original") or results[0].get("thumbnail")
        raise ValueError(f"No image results for {query!r}")

    if settings.image_search_api_key and settings.image_search_cx:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.image_search_api_key,
                    "cx": settings.image_search_cx,
                    "q": query,
                    "searchType": "image",
                    "num": 3,
                    "safe": "active",
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items") or []
        if not items:
            raise ValueError(f"No image results for {query!r}")
        return items[0]["link"]

    raise RuntimeError(
        "Image search is not configured. Set SERPAPI_KEY (preferred) or "
        "IMAGE_SEARCH_API_KEY + IMAGE_SEARCH_CX in backend/.env."
    )


async def ingest_web_image(db: AsyncSession, query: str, concept_id: int | None = None) -> Diagram:
    url = await search_web_image(query)
    regions = await segment_image(image_url=url)
    diagram = Diagram(image_url=url, source="web", regions=regions, concept_id=concept_id)
    db.add(diagram)
    await db.commit()
    return diagram


async def generate_diagram(db: AsyncSession, description: str, concept_id: int | None = None) -> Diagram:
    """Schematic content: model draws SVG and reports its own regions —
    no vision call needed, ever, for generated diagrams."""
    raw = await call_model(
        Task.teach_concept,
        [{"role": "user", "content": _GENERATE_PROMPT.format(description=description)}],
    )
    svg_match = re.search(r"<<<svg>>>(.*?)<<<regions>>>", raw, re.DOTALL)
    regions_match = re.search(r"<<<regions>>>(.*)", raw, re.DOTALL)
    if not svg_match or not regions_match:
        raise ValueError("Diagram generation output missing svg/regions sections")
    svg = svg_match.group(1).strip()
    svg = re.sub(r"^```(?:svg|xml|html)?|```$", "", svg, flags=re.MULTILINE).strip()
    regions = [
        {
            "label": str(r["label"]),
            "bbox": _round_bbox(r["bbox"]),
            "description": str(r["description"]),
        }
        for r in _extract_json_value(regions_match.group(1))
    ]

    name = f"{uuid.uuid4().hex}.svg"
    (MEDIA_DIR / name).write_text(svg, encoding="utf-8")
    diagram = Diagram(
        image_url=f"/media/{name}", source="generated", regions=regions, concept_id=concept_id
    )
    db.add(diagram)
    await db.commit()
    return diagram


async def ask_about_region(diagram: Diagram, region_label: str, question: str, context: str = "") -> str:
    """Text-only call grounded in the cached region description."""
    region = next(
        (r for r in (diagram.regions or []) if r["label"].lower() == region_label.lower()), None
    )
    if region is None:
        raise ValueError(f"No region labeled {region_label!r} on diagram {diagram.id}")
    return await call_model(
        Task.teach_concept,
        [
            {
                "role": "user",
                "content": _REGION_QA_PROMPT.format(
                    context=context or f"a {diagram.source} diagram",
                    label=region["label"],
                    description=region["description"],
                    question=question,
                ),
            }
        ],
    )


async def describe_crop(db: AsyncSession, diagram: Diagram, bbox: list[float]) -> tuple[str, bool]:
    """Arbitrary crop → cached description. Returns (description, was_cached)."""
    key = crop_cache_key(diagram.id, bbox)
    cached = await db.get(CropCache, key)
    if cached is not None:
        return cached.description, True

    x, y, w, h = _round_bbox(bbox)
    prompt = _CROP_PROMPT.format(x=x, y=y, w=w, h=h)
    if diagram.image_url.startswith("/media/"):
        description = await call_model_vision(
            Task.diagram_segment, prompt, image_path=str(MEDIA_DIR / diagram.image_url.split("/")[-1])
        )
    else:
        description = await call_model_vision(Task.diagram_segment, prompt, image_url=diagram.image_url)

    db.add(
        CropCache(
            cache_key=key, diagram_id=diagram.id, bbox=_round_bbox(bbox), description=description
        )
    )
    await db.commit()
    return description, False
