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


API_DESCRIPTION = """
Wazi answers citizen questions about **Nakuru County** government spending in
Swahili, Sheng, or English — grounded **only** in official audit and budget
documents, with a source citation on every reply.

### Two kinds of endpoint
- **Public webhook** (`/whatsapp/incoming`) — Africa's Talking posts incoming
  WhatsApp messages here. No auth: the sender is the messaging provider, and
  the raw phone number is HMAC-hashed on receipt and never stored.
- **Admin API** (`/api/*`) — everything else. Requires a Bearer token
  (`Authorization: Bearer <ADMIN_PASSWORD>`). Powers the moderation dashboard.

### Responsible-computing posture
No PII is stored (phone numbers are hashed), disputes and chat history have no
join path, and answers come only from a curated corpus — the model refuses
("sina taarifa za kutosha") rather than guess.
"""

tags_metadata = [
    {"name": "whatsapp", "description": "Public webhook that receives citizen "
        "WhatsApp messages from Africa's Talking. Hashes the sender id, runs "
        "the RAG pipeline, and handles the `SI SAHIHI` dispute-report keyword."},
    {"name": "disputes", "description": "Moderation queue for citizen reports "
        "that an answer may be wrong. Admin-only: list, inspect, and move "
        "disputes through the review lifecycle."},
    {"name": "sources", "description": "Registry of official government "
        "documents in the corpus. Admin-only CRUD + manual ingestion trigger."},
    {"name": "stats", "description": "Aggregate corpus and usage statistics for "
        "the dashboard. Admin-only."},
    {"name": "sessions", "description": "Read-only browsing of conversation "
        "sessions and messages for moderation. Admin-only."},
]

app = FastAPI(
    title="Wazi API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    contact={"name": "Team WAZIRI", "url": "https://github.com/JoylynnWamjiru/Wazi-"},
    license_info={"name": "MIT"},
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
