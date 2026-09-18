# Edumind — AI Teaching Operating System

**Not a chatbot.** Edumind continuously models a student's knowledge, teaches
through a structured pedagogical engine, tracks *why* a student is wrong (not
just that they are), schedules spaced revision, and evolves a versioned
**digital twin** of the learner over time. Every AI call is routed through a
single cost-governing choke point, so the system stays affordable at scale.

Built for the AI for X Hackathon (industry: Education). Full deliverables
pack (architecture diagrams, workflow maps, demo script) is in
[docs/HACKATHON_DELIVERABLES.md](docs/HACKATHON_DELIVERABLES.md).

```
Repo:   https://github.com/OJsri/EduMind-AI
Stack:  Next.js 16 (frontend)  +  FastAPI / LangGraph (backend)  +  Postgres 16 / pgvector (state)
Models: Poe-hosted (GPT-5-mini, Claude-Sonnet-4.5, Gemini-2.5-Flash), routed by task
```

---

## Table of contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Repository layout](#repository-layout)
4. [Data model](#data-model)
5. [Model routing (cost control)](#model-routing-cost-control)
6. [API surface](#api-surface)
7. [Run it locally](#run-it-locally)
8. [Configuration](#configuration)
9. [Testing](#testing)
10. [Deploying to the cloud](#deploying-to-the-cloud)
11. [Known limitations / v2 scope](#known-limitations--v2-scope)

---

## What it does

A student's journey through Edumind:

1. **Sign up → subject-adaptive onboarding.** Pick a known subject (CS,
   Physics have hand-built templates) or type any other subject — a Dynamic
   Onboarding Agent generates and persists a curriculum for it on the fly.
2. **Living Knowledge Map.** A custom-built infinite canvas (pan/zoom, bezier
   edges, minimap, focus mode — no React Flow) shows every concept, colored by
   mastery, ringed by confidence.
3. **Diagnostic assessment.** Adaptive quiz; MCQs grade deterministically
   (free), short answers are graded by an LLM that names the *reasoning
   error*, not just "wrong." Confidence updates via EWMA.
4. **Adaptive lessons.** The Teaching Agent designs each lesson's *structure*
   per concept and learner (not a fixed template), grounds it in the
   student's own uploaded PDFs/slides via RAG (Postgres full-text search),
   and streams it block-by-block over SSE.
5. **Visual-Need Agent.** A dedicated, cached-per-concept agent independently
   decides whether an image, a simulation, both, or neither would help —
   diagrams are auto-fetched (SerpAPI) and inserted inline; simulations
   (p5/matter/d3/three, chosen per concept) run sandboxed in an `iframe
   srcdoc`.
6. **Branching.** Any side-question — or a cropped region of a diagram — forks
   the LangGraph checkpoint into a new, independently resumable thread. Deep
   dives never derail the main lesson.
7. **Revision.** An SM-2 variant (easiness = retention_score) surfaces exactly
   what's decaying — pure logic, zero LLM calls.
8. **Digital twin.** At session end, one batched call synthesizes a versioned
   cognitive/behavioral profile; the dashboard shows a radar chart, an open
   misconception ledger, and a diff against the previous snapshot.

## Architecture

Edumind is layered like an operating system: a presentation layer, an
orchestration kernel, a pool of specialized agent "processes," a
cost-governing model router (the scheduler), and a persistent state layer.

```
┌─────────────────────────────── Presentation — Next.js 16 / TypeScript ───────────────────────────────┐
│  Learn Workspace (lesson · chat · branches)   Knowledge Map (custom canvas)   Twin Dashboard            │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                  │ REST + SSE
┌─────────────────────────────── Orchestration Kernel — FastAPI + LangGraph ───────────────────────────┐
│  StateGraph over a shared EdumindState, checkpointed per thread_id                                     │
│                                                                                                          │
│   ┌────────┐                                                                                            │
│   │ Router │ classifies intent → conditional edge dispatches to exactly one agent                       │
│   └───┬────┘                                                                                            │
│       ├─ teach ──────► Teaching ──► Misconception                                                        │
│       ├─ assess ─────► Diagnostic ─► Misconception                                                       │
│       ├─ branch ─────► Branch (forks checkpoint → new thread_id)                                         │
│       ├─ diagram ────► Image                                                                             │
│       ├─ simulate ───► Simulation                                                                        │
│       ├─ revise ─────► Revision (pure logic, SM-2)                                                       │
│       └─ end_session ► Twin Updater (1 batched call)                                                     │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                  │ every model call declares a Task
┌─────────────────────────── Model Router — app/models/router.py (single choke point) ─────────────────┐
│  classify_intent / generate_quiz / classify_visual  ──► GPT-5-mini        (cheap, hot path)             │
│  grade_answer / teach_concept / onboard_dynamic /                                                        │
│  twin_summarize                                     ──► Claude-Sonnet-4.5 (mid, judgment/pedagogy)       │
│  diagram_segment                                    ──► Gemini-2.5-Flash  (vision, once per image)       │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                  │
┌─────────────────────────────── State Layer — Postgres 16 + pgvector (Docker, :5433) ─────────────────┐
│  learner model (concepts, mastery, misconceptions)  │  content (lessons, branches, diagrams, sims)     │
│  versioned twin snapshots                            │  caches (response, simulation, crop, vector)     │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Principles that make this an OS, not a chatbot:**

- **Single kernel.** Every turn enters one LangGraph `StateGraph`; the Router
  node classifies intent and a conditional edge dispatches to exactly one
  agent — the same way an OS scheduler dispatches to a process.
- **Model routing is a hard architectural boundary.** No feature code calls a
  model directly — it declares a `Task`; `app/models/router.py` decides which
  Poe bot pays. Change one line, the whole system re-routes.
- **Persistent state is the product.** The learner model, misconception
  ledger, and versioned twin snapshots live in Postgres — the intelligence is
  in accumulated state, not any single prompt.
  ​- **Branch = process fork.** A side-question forks the LangGraph checkpoint
  into a new `thread_id`, resumable forever, exactly like forking a process.
- **Cache before compute.** Diagram regions/crops, simulations, and
  cohort-keyed lessons are served from cache before any model is touched.

A full sequence diagram of a single "teach me this" request (state read → RAG
retrieve → cache check → model call → state write → cache write) is in
[docs/HACKATHON_DELIVERABLES.md § 6](docs/HACKATHON_DELIVERABLES.md#6-data-flow-diagram).

## Repository layout

```
EduMind/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, router mounting
│   │   ├── config.py                pydantic-settings (.env)
│   │   ├── db.py                    async SQLAlchemy engine/session
│   │   ├── schemas.py               Pydantic request/response models
│   │   ├── graph/
│   │   │   ├── graph.py             LangGraph StateGraph wiring (nodes + edges)
│   │   │   ├── nodes.py             router/diagnostic/teaching/branch/image/
│   │   │   │                        simulation/misconception/revision/twin_updater
│   │   │   └── state.py             shared EdumindState
│   │   ├── models/
│   │   │   ├── router.py            ★ the cost-control choke point (Task → Poe bot)
│   │   │   └── tables.py            SQLAlchemy ORM models (14 tables)
│   │   ├── services/                 business logic per domain (one file per
│   │   │                             concern: teaching, assessment, branching,
│   │   │                             images, simulations, revision, twin,
│   │   │                             onboarding, documents/RAG, response cache)
│   │   └── api/                      FastAPI routers — one per resource
│   │       (auth, onboarding, graph, teach, assessment, branches, images,
│   │        simulations, revision, twin, sessions, profile, documents)
│   ├── alembic/                      migrations
│   ├── tests/                        pytest suite (async, real Postgres)
│   ├── conftest.py                   Windows event-loop policy for tests
│   ├── run.py                        ★ backend entry point — use this, not `uvicorn` CLI
│   ├── probe_bots.py                 checks which Poe bots currently accept API access
│   └── .env.example
├── frontend/
│   ├── app/                          Next.js App Router pages: /, /onboarding,
│   │                                 /learn, /dashboard, /profile
│   ├── components/                   LessonPanel, AssessmentPanel, SidePanel,
│   │                                 BranchMain, DiagramViewer, canvas/ (custom
│   │                                 infinite-canvas knowledge map)
│   └── lib/                          API client, markdown/KaTeX rendering
├── docs/
│   ├── HACKATHON_DELIVERABLES.md     architecture diagrams, workflow/decision
│   │                                 maps, model design, demo script
│   └── DEPLOYMENT.md                 free-tier cloud deploy (Vercel/Netlify + Render + Neon)
├── docker-compose.yml                Postgres+pgvector (and optional Redis)
├── netlify.toml / render.yaml        cloud deploy configs
└── README.md                         this file
```

## Data model

14 tables in Postgres (pgvector extension enabled), created/migrated via
Alembic:

| Table | Purpose |
|---|---|
| `users`, `learner_profiles` | accounts + onboarding preferences |
| `concepts`, `learner_concept_state` | the concept graph + per-user mastery/confidence/misconceptions |
| `sessions` | learning session boundaries (drives twin batching) |
| `lesson_blocks` | streamed lesson content, per concept/cohort |
| `branches` | forked side-quest threads (nullable `parent_block_id` + `concept_id` → free-form "new chat" under a topic) |
| `documents`, `document_chunks` | uploaded PDFs/slides, chunked for RAG (`embedding` column reserved for a future embedding provider — currently NULL, RAG runs on Postgres full-text search since Poe has no embeddings endpoint) |
| `diagrams`, `crop_cache` | fetched/generated/uploaded images, segmented regions, hashed-crop Q&A cache |
| `simulation_cache` | generated p5/matter/d3/three code, cached per concept+cohort |
| `twin_snapshots` | versioned digital-twin profiles (for the diff view) |
| `subject_templates` | built-in + dynamically-generated curricula per subject |

## Model routing (cost control)

Every LLM call in the codebase goes through **one function**,
[`backend/app/models/router.py`](backend/app/models/router.py) — feature code
never imports the Poe SDK directly. It declares a `Task` enum value; the
router maps it to a Poe bot:

| Task | Model | Fires |
|---|---|---|
| `classify_intent` | GPT-5-mini | every message (hot path → cheapest) |
| `generate_quiz` | GPT-5-mini | per assessment |
| `classify_visual` | GPT-5-mini | once per concept, cached forever |
| `track_misconception` | GPT-5-mini | after teach/assess turns |
| `grade_answer` | Claude-Sonnet-4.5 | short answers only (MCQs skip it — free) |
| `teach_concept` | Claude-Sonnet-4.5 | lessons, branches, simulation codegen |
| `onboard_dynamic` | Claude-Sonnet-4.5 | unknown subjects only, then cached |
| `twin_summarize` | Claude-Sonnet-4.5 | once per session end, batched |
| `diagram_segment` | Gemini-2.5-Flash | once per image, cached forever; arbitrary crops hashed and cached separately |

> The spec called for `Claude-Sonnet-5` and `GPT-5.6-Sol`, but both currently
> reject Poe API access ("This bot does not support API access" — see
> `probe_bots.py`). The nearest-capable equivalents above are substituted;
> reverting is a two-line edit to `ROUTES` in `router.py` once Poe enables them.

Long-form generations (lessons, simulations, diagrams) use a
`<<<section>>>` marker format instead of JSON — unescaped quotes/newlines in
free-form model text reliably break JSON parsing; short structured outputs
(quizzes) still use JSON.

## API surface

FastAPI routers, one per resource (`backend/app/api/`):

| Router | Endpoints |
|---|---|
| `auth` | `POST /signup`, `POST /login` |
| `onboarding` | `GET /subjects`, `GET /questions`, `POST /complete` |
| `graph` | `GET /plan`, `POST /concepts`, `GET /graph` |
| `teach` | `GET /lessons`, `GET /stream` (SSE) |
| `assessment` | `POST /start`, `POST /answer` |
| `branches` | `POST /`, `GET /`, `GET /concept/{id}`, `GET /{id}/history`, `POST /{id}/message`, `DELETE /{id}` |
| `images` | `POST /upload`, `POST /fetch`, `POST /generate`, `GET /concept/{id}`, `GET /{id}`, `POST /{id}/ask`, `POST /{id}/crop` |
| `simulations` | `GET /cached`, `POST /` |
| `revision` | `GET /due`, `POST /review` |
| `twin` | `POST /{user_id}/snapshot`, `GET /{user_id}`, `GET /{user_id}/history`, `GET /{user_id}/diff` |
| `sessions` | `GET /`, `POST /start`, `POST /{id}/end` |
| `profile` | `GET /{user_id}`, `PUT /{user_id}` |
| `documents` | `POST /roadmap`, `POST /upload`, `GET /search` |

Interactive docs at `http://localhost:8000/docs` once the backend is running.

## Run it locally

Prerequisites: **Docker Desktop** (running), **Python 3.13**, **Node 20+**.

```powershell
# 0. clone & enter
git clone https://github.com/OJsri/EduMind-AI.git
cd EduMind-AI

# 1. database (Postgres 16 + pgvector, port 5433)
docker compose up -d postgres

# 2. backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then edit .env — set POE_API_KEY (see Configuration below)
.venv\Scripts\alembic upgrade head
.venv\Scripts\python run.py   # ★ use run.py, NOT `uvicorn` CLI directly

# 3. frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

Backend serves on `http://localhost:8000` (docs at `/docs`, health at
`/health`). Frontend serves on `http://localhost:3000` and calls the backend
via `NEXT_PUBLIC_API_URL` (defaults to `localhost:8000` in dev).

> **Why `run.py` and not `python -m uvicorn`?** On Windows, `psycopg`'s async
> driver breaks under the default `ProactorEventLoop`. `run.py` sets
> `WindowsSelectorEventLoopPolicy` before starting the server and owns the
> event loop itself; `conftest.py` applies the same policy for the test
> suite. Starting the backend any other way on Windows will surface
> intermittent DB errors.

## Configuration

All backend config lives in `backend/.env` (copy from `.env.example`):

| Variable | Required | Purpose |
|---|---|---|
| `POE_API_KEY` | **yes** | Poe API key — every model call goes through it |
| `DATABASE_URL` | yes (has a working default) | `postgresql+psycopg://edumind:edumind@localhost:5433/edumind` for the Docker Postgres above |
| `SERPAPI_KEY` | optional | preferred image-search provider (Google Images via SerpAPI, free tier ~100 searches/mo) |
| `IMAGE_SEARCH_API_KEY` / `IMAGE_SEARCH_CX` | optional | fallback: Google Programmable Search Engine |
| `REDIS_URL` | optional | leave empty — session state falls back to in-memory; only needed for multi-process deploys |

Without any image-search key configured, `/images/fetch` returns 503 —
everything else (upload, and the model-drawn SVG generation path) still works
fully.

## Testing

```powershell
cd backend
.venv\Scripts\python -m pytest -q
```

The suite runs async against a real Postgres instance (via the Docker
container above) — no mocked DB. `conftest.py` installs the Windows
selector event-loop policy so tests match production behavior.

To re-check which Poe bots currently accept API access (bots occasionally
change availability):

```powershell
.venv\Scripts\python probe_bots.py
```

## Deploying to the cloud

Full step-by-step guide (Neon for Postgres, Render for the backend, Vercel or
Netlify for the frontend — all free tiers) is in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Short version:

1. **Neon** → new project → copy the connection string, add `+psycopg` after
   `postgresql` → this is your `DATABASE_URL`.
2. **Render** → New → Blueprint → point at this repo (reads `render.yaml`) →
   set `POE_API_KEY`, `SERPAPI_KEY`, `DATABASE_URL`.
3. **Vercel** (or Netlify, via `netlify.toml`) → import repo, root directory
   `frontend`, set `NEXT_PUBLIC_API_URL` to the Render URL.
4. Back in Render, set `FRONTEND_ORIGINS` to the deployed frontend URL to
   close the CORS loop.

The backend must run as a long-lived process (not serverless) — it holds
LangGraph branch-thread checkpoints, in-flight assessment state, and streams
lessons over SSE for longer than typical serverless time limits allow.

## Known limitations / v2 scope

- **Teaching personas, exam mode, assignment mode, curiosity mode** are
  explicitly out of scope for this MVP — the graph is structured so they can
  land as new LangGraph nodes without touching existing ones.
- **Embeddings** are not wired up: Poe has no embeddings endpoint, so
  `document_chunks.embedding` stays NULL and RAG runs on Postgres full-text
  search. The pgvector column is the seam for a future embedding provider.
- **Uploaded image files are ephemeral** on serverless/free-tier hosts (local
  disk resets on redeploy) — web-fetched diagram URLs, regions, lessons, and
  the twin all persist fine since they live in Postgres.
- The spec's originally-named `Claude-Sonnet-5` / `GPT-5.6-Sol` Poe bots
  reject API access as of this writing; `Claude-Sonnet-4.5` /
  `Gemini-2.5-Flash` are substituted (see [Model routing](#model-routing-cost-control)).
