"""FastAPI application entry point for Wazi.

Start with:
    uvicorn src.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.shared.database import init_db


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


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and DO health checks."""
    return {"status": "healthy", "service": "wazi-api"}
