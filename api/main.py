"""
limes_outpost.api.main
~~~~~~~~~~~~~~~~~~~
FastAPI application factory.

Run locally:
    uvicorn limes_outpost.api.main:app --reload --port 8000

Run via Docker:
    Defined in docker-compose.yml as the `api` service.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from limes_outpost.api.routers import auth, ventures, queue, pipeline, publish, analytics, pulse, inbox
from limes_outpost.utils.db import get_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup, clean up on shutdown."""
    # Warm the DB pool so the first request isn't slow
    get_pool()
    yield
    # Pool cleanup handled by process exit — psycopg2 SimpleConnectionPool
    # has no async close, so we leave it to the OS on shutdown.


app = FastAPI(
    title="LimesOutpost API",
    description="Autonomous Content OS — REST API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────
# Tighten origins before production — wildcard is fine for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/auth",     tags=["Auth"])
app.include_router(ventures.router,  prefix="/ventures", tags=["Ventures"])
app.include_router(queue.router,     prefix="/ventures", tags=["Queue"])
app.include_router(pipeline.router,  prefix="/ventures", tags=["Pipeline"])
app.include_router(publish.router,   prefix="/ventures", tags=["Publish"])
app.include_router(analytics.router, prefix="/ventures", tags=["Analytics"])
app.include_router(pulse.router,     prefix="/ventures/{venture_id}/pulse", tags=["pulse"])
app.include_router(inbox.router,     prefix="/ventures/{venture_id}/inbox", tags=["Inbox"])

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "limes_outpost-api"}