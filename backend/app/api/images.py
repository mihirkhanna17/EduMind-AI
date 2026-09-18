from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Diagram
from app.services import images as svc

router = APIRouter(prefix="/images", tags=["images"])


def _diagram_out(d: Diagram) -> dict:
    return {"diagram_id": d.id, "image_url": d.image_url, "source": d.source, "regions": d.regions}


@router.post("/upload")
async def upload_image(
    file: UploadFile, concept_id: int | None = None, db: AsyncSession = Depends(get_db)
):
    data = await file.read()
    return _diagram_out(
        await svc.ingest_uploaded_image(db, file.filename or "image.png", data, concept_id=concept_id)
    )


class FetchRequest(BaseModel):
    query: str
    concept_id: int | None = None


@router.post("/fetch")
async def fetch_image(req: FetchRequest, db: AsyncSession = Depends(get_db)):
    try:
        return _diagram_out(await svc.ingest_web_image(db, req.query, concept_id=req.concept_id))
    except RuntimeError as e:  # search not configured
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


class GenerateRequest(BaseModel):
    description: str
    concept_id: int | None = None


@router.post("/generate")
async def generate_image(req: GenerateRequest, db: AsyncSession = Depends(get_db)):
    try:
        return _diagram_out(await svc.generate_diagram(db, req.description, concept_id=req.concept_id))
    except ValueError as e:
        raise HTTPException(502, str(e))


@router.get("/concept/{concept_id}")
async def images_for_concept(concept_id: int, db: AsyncSession = Depends(get_db)):
    """All visuals created for a concept — restored when the concept is opened."""
    from sqlalchemy import select

    from app.models import Diagram

    rows = (
        await db.scalars(
            select(Diagram).where(Diagram.concept_id == concept_id).order_by(Diagram.id.desc()).limit(10)
        )
    ).all()
    return {"diagrams": [_diagram_out(d) for d in rows]}


@router.get("/{diagram_id}")
async def get_diagram(diagram_id: int, db: AsyncSession = Depends(get_db)):
    d = await db.get(Diagram, diagram_id)
    if d is None:
        raise HTTPException(404, "Diagram not found")
    return _diagram_out(d)  # regions from cache — zero model calls


class AskRequest(BaseModel):
    region_label: str
    question: str
    context: str = ""


@router.post("/{diagram_id}/ask")
async def ask_region(diagram_id: int, req: AskRequest, db: AsyncSession = Depends(get_db)):
    d = await db.get(Diagram, diagram_id)
    if d is None:
        raise HTTPException(404, "Diagram not found")
    try:
        answer = await svc.ask_about_region(d, req.region_label, req.question, req.context)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"answer": answer}


class CropRequest(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)  # [x, y, w, h] normalized


@router.post("/{diagram_id}/crop")
async def crop(diagram_id: int, req: CropRequest, db: AsyncSession = Depends(get_db)):
    d = await db.get(Diagram, diagram_id)
    if d is None:
        raise HTTPException(404, "Diagram not found")
    description, cached = await svc.describe_crop(db, d, req.bbox)
    return {"description": description, "cached": cached}
