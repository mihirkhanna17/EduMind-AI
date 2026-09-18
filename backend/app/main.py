from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fastapi.staticfiles import StaticFiles

from app.api import (
    assessment,
    auth,
    branches,
    documents,
    graph as graph_api,
    images,
    onboarding,
    profile,
    revision,
    sessions,
    simulations,
    teach,
    twin,
)
from app.db import SessionLocal
from app.graph.graph import build_graph
from app.services.subject_templates import seed_builtin_templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.graph = build_graph()
    async with SessionLocal() as db:
        await seed_builtin_templates(db)
    yield


app = FastAPI(title="Edumind", lifespan=lifespan)
from app.config import settings

_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
# deployed frontend(s), e.g. FRONTEND_ORIGINS=https://edumind-ai.netlify.app
_origins += [o.strip() for o in settings.frontend_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(graph_api.router)
app.include_router(assessment.router)
app.include_router(sessions.router)
app.include_router(teach.router)
app.include_router(documents.router)
app.include_router(branches.router)
app.include_router(revision.router)
app.include_router(images.router)
app.include_router(simulations.router)
app.include_router(twin.router)
app.include_router(profile.router)

from app.services.images import MEDIA_DIR  # noqa: E402

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
async def health():
    return {"status": "ok"}


class ChatRequest(BaseModel):
    user_id: int
    session_id: int
    message: str
    concept_id: int | None = None  # concept in focus (teaching/misconception context)
    thread_id: str | None = None  # branch threads pass their own id


@app.post("/chat")
async def chat(req: ChatRequest):
    """Phase 3 smoke endpoint: routes a message through the graph.

    Feature nodes are stubs until their phases land; the router node
    classifies for real (requires POE_API_KEY).
    """
    thread_id = req.thread_id or f"session-{req.session_id}"
    result = await app.state.graph.ainvoke(
        {
            "user_id": req.user_id,
            "session_id": req.session_id,
            "user_message": req.message,
            "current_concept_id": req.concept_id,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return {"mode": result.get("mode"), "response": result.get("response")}
