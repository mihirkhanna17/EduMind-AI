from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import DocumentChunk
from app.models.router import Task, call_model
from app.schemas import StarterConcept
from app.services.assessment import _extract_json_value
from app.services.documents import ingest_document, search_chunks
from app.services.onboarding import merge_concepts_for_user

router = APIRouter(prefix="/documents", tags=["documents"])

_ROADMAP_PROMPT = """Below are excerpts from a student's own study material for "{subject}".
Design a learning roadmap FROM THIS MATERIAL: the concepts it covers, ordered for learning.

<material>
{excerpt}
</material>

Return a JSON array only (no prose, no fences) of 6-14 concepts:
[{{"name": "<concept as named in the material>", "parent": null, "prerequisites": ["<name of another listed concept>"]}}]
- prerequisites may only reference other names in this list
- order roughly by learning sequence
- use the material's own terminology"""


class RoadmapRequest(BaseModel):
    user_id: int
    document_id: int
    subject: str


@router.post("/roadmap")
async def generate_roadmap(req: RoadmapRequest, db: AsyncSession = Depends(get_db)):
    """One mid-tier call: study material → concept roadmap, merged into the
    student's canvas. Lessons then auto-ground in the same material via RAG."""
    chunks = (
        await db.scalars(
            select(DocumentChunk.content)
            .where(DocumentChunk.document_id == req.document_id)
            .order_by(DocumentChunk.id)
            .limit(10)
        )
    ).all()
    if not chunks:
        raise HTTPException(404, "Document has no extractable text")
    excerpt = "\n---\n".join(chunks)[:12000]

    raw = await call_model(
        Task.onboard_dynamic,
        [{"role": "user", "content": _ROADMAP_PROMPT.format(subject=req.subject, excerpt=excerpt)}],
    )
    try:
        starter = [StarterConcept.model_validate(c) for c in _extract_json_value(raw)]
    except Exception as e:
        raise HTTPException(502, f"Roadmap generation failed: {e}")

    added = await merge_concepts_for_user(db, req.user_id, req.subject, starter)
    return {
        "added_concepts": [{"id": c.id, "name": c.name} for c in added],
        "skipped_existing": len(starter) - len(added),
    }


@router.post("/upload")
async def upload(user_id: int, file: UploadFile, db: AsyncSession = Depends(get_db)):
    data = await file.read()
    try:
        doc = await ingest_document(db, user_id, file.filename or "upload", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"document_id": doc.id, "filename": doc.filename, "source_type": doc.source_type}


@router.get("/search")
async def search(user_id: int, q: str, db: AsyncSession = Depends(get_db)):
    return {"chunks": await search_chunks(db, user_id, q)}
