"""FastAPI application entry point for Wazi.

Start with:
    uvicorn src.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.shared.database import init_db

# --- Routers ---
from src.api.webhooks import router as webhook_router
from src.api.routes.disputes import router as disputes_router
from src.api.routes.sources import router as sources_router
from src.api.routes.stats import router as stats_router
from src.api.routes.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="Wazi API",
    description="WhatsApp RAG pipeline for Kenyan county budget transparency",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Routers ---
# Webhook is public (no auth — AT sends the request, not a user).
app.include_router(webhook_router, tags=["whatsapp"])

# Admin API routes — all require Bearer token authentication.
app.include_router(disputes_router, tags=["disputes"])
app.include_router(sources_router, tags=["sources"])
app.include_router(stats_router, tags=["stats"])
app.include_router(sessions_router, tags=["sessions"])


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and DO health checks."""
    return {"status": "healthy", "service": "wazi-api"}
