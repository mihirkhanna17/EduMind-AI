"""Multimodal Simulation Agent.

Generates a small self-contained HTML/JS simulation for concepts better shown
than described, choosing the library per concept type (p5 / matter / d3 / three).
Cached per (concept, variant): the same bubble-sort animation is NEVER
regenerated per student — only a meaningfully different learner framing
(different variant_key) triggers a new generation.

Delivery contract (enforced by the frontend): rendered exclusively inside
<iframe srcdoc sandbox="allow-scripts"> — no same-origin access, generated
code never touches the main app DOM.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, LearnerProfile, SimulationCache
from app.models.router import Task, call_model

LIBRARIES = {"p5", "matter", "d3", "three"}

_SIM_PROMPT = """Create a small interactive simulation that teaches "{concept}" (subject: {subject}).
Learner framing: {framing}

First choose the ONE best-suited library:
- p5    → generative sketches, simple physics, waves, particles
- matter → 2D rigid-body mechanics (collisions, gravity, constraints)
- d3    → data & graph structures, sorting/searching visualizations, trees
- three → genuinely 3D/spatial concepts

Output exactly two sections with these markers:

<<<library>>>
(one word: p5, matter, d3, or three)
<<<html>>>
(a COMPLETE self-contained HTML document)

STRICT layout rules — the iframe is only ~400px wide and ~320px tall:
- ONE compact control bar at the TOP: a single flex row (flex-wrap), height ≤ 60px,
  dark translucent background, containing ALL controls AND a one-line instruction
- the canvas fills ALL remaining space below the bar (use body {{ display:flex;
  flex-direction:column; height:100vh; margin:0 }} and size the canvas to its container)
- NEVER use floating/absolutely-positioned panels over the canvas, NO welcome
  overlays, NO modals, NO text drawn on top of interactive areas
- handle window resize; nothing may overflow or overlap
- font-size ≥ 12px; short labels; background #111827; bright, high-contrast colors

Behavior rules:
- loads only the chosen library from cdn.jsdelivr.net or cdnjs.cloudflare.com
- all other JS/CSS inline; no other network requests, no localStorage, no cookies
- starts animating immediately; at least one control (click/drag/slider/button)
  that changes the simulation meaningfully
- must run inside a sandboxed iframe (allow-scripts only)"""


def variant_key_for(profile: LearnerProfile | None) -> str:
    """Same style cohort ⇒ same cached simulation."""
    prefs = (profile.learning_prefs if profile else {}) or {}
    style = str(prefs.get("style", "default")).lower().strip().replace(" ", "-")[:40]
    return style or "default"


def parse_simulation(raw: str) -> tuple[str, str]:
    lib_match = re.search(r"<<<library>>>\s*(\w+)", raw)
    html_match = re.search(r"<<<html>>>\s*(.*)", raw, re.DOTALL)
    if not lib_match or not html_match:
        raise ValueError("Simulation output missing library/html sections")
    library = lib_match.group(1).strip().lower()
    if library not in LIBRARIES:
        raise ValueError(f"Unknown simulation library {library!r}")
    html = html_match.group(1).strip()
    html = re.sub(r"^```(?:html)?|```$", "", html, flags=re.MULTILINE).strip()
    if "<html" not in html.lower():
        raise ValueError("Simulation html section is not a complete document")
    return library, html


async def get_or_generate(
    db: AsyncSession, user_id: int, concept_id: int, force: bool = False
) -> tuple[SimulationCache, bool]:
    """Returns (cache_row, was_cached). force=True regenerates and replaces the
    cached simulation (the 'this one is messy' escape hatch)."""
    concept = await db.get(Concept, concept_id)
    if concept is None:
        raise ValueError(f"Concept {concept_id} not found")
    profile = await db.get(LearnerProfile, user_id)
    variant = variant_key_for(profile)

    existing = await db.scalar(
        select(SimulationCache).where(
            SimulationCache.concept_id == concept_id,
            SimulationCache.variant_key == variant,
        )
    )
    if existing is not None and not force:
        return existing, True

    prefs = (profile.learning_prefs if profile else {}) or {}
    raw = await call_model(
        Task.teach_concept,  # spec: reuse the mid-tier teach route
        [
            {
                "role": "user",
                "content": _SIM_PROMPT.format(
                    concept=concept.name,
                    subject=concept.subject,
                    framing=prefs.get("style", "no specific preference"),
                ),
            }
        ],
    )
    library, html = parse_simulation(raw)
    if existing is not None:  # force-regeneration replaces in place
        existing.library = library
        existing.code = html
        await db.commit()
        return existing, False
    row = SimulationCache(
        concept_id=concept_id, variant_key=variant, library=library, code=html
    )
    db.add(row)
    await db.commit()
    return row, False
