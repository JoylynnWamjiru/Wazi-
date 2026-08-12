"""System / end-to-end tests — full FastAPI app with all routers mounted.

Tests every endpoint through the full middleware stack (auth, routing,
validation) using TestClient.  Uses the in-memory SQLite fixture — all
routes except pgvector retrieval work against SQLite.

Marked ``db`` — no PostgreSQL needed.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Full app fixture — all routers, real middleware
# ---------------------------------------------------------------------------

@pytest.fixture
def app(db):
    """Mount ALL routers into a single FastAPI app with the patched DB."""
    from src.api import webhooks
    from src.api.middleware import auth
    from src.api.routes.disputes import router as disputes_router
    from src.api.routes.sessions import router as sessions_router
    from src.api.routes.sources import router as sources_router
    from src.api.routes.stats import router as stats_router
    from src.api.routes.validation import router as validation_router

    # Create minimal chunks table for routes that COUNT chunks.
    from sqlalchemy import text
    chunks_sql = text("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            government_arm VARCHAR,
            county VARCHAR,
            chunk_text TEXT,
            embedding TEXT,
            page_number INTEGER,
            chunk_index INTEGER,
            created_at DATETIME
        )
    """)
    validations_sql = text("""
        CREATE TABLE IF NOT EXISTS validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            tone_score INTEGER NOT NULL,
            grounded BOOLEAN NOT NULL,
            register VARCHAR NOT NULL,
            reviewer VARCHAR,
            notes TEXT,
            created_at DATETIME
        )
    """)
    with db.get_session() as s:
        s.execute(chunks_sql)
        s.execute(validations_sql)

    # Stub send_whatsapp so webhook tests don't call Africa's Talking.
    async def _fake_send(phone: str, message: str):
        pass

    import src.api.webhooks as wh
    wh.send_whatsapp = _fake_send  # type: ignore[assignment]

    application = FastAPI()
    application.include_router(wh.router)
    application.include_router(sources_router)
    application.include_router(stats_router)
    application.include_router(disputes_router)
    application.include_router(sessions_router)
    application.include_router(validation_router)

    client = TestClient(application)
    admin_headers = {"Authorization": f"Bearer {auth.ADMIN_PASSWORD}"}
    return client, admin_headers


# ---------------------------------------------------------------------------
# WhatsApp webhook — full citizen flow
# ---------------------------------------------------------------------------

def test_full_question_flow_returns_200_and_creates_session(app, seed):
    """A citizen's question creates a user, session, and message, then
    returns 200 immediately (pipeline runs in background)."""
    client, _ = app
    phone = "+254700000042"

    r = client.post("/whatsapp/incoming", data={"from": phone, "text": "Pesa ngapi?"})
    assert r.status_code == 200

    # Verify the session was created.
    from src.shared.database import get_session
    from src.shared.models import Message, Session, User
    from src.api.middleware.identity import hash_wa_id

    with get_session() as s:
        user = s.query(User).filter_by(hashed_wa_id=hash_wa_id(phone)).first()
        assert user is not None
        sess = s.query(Session).filter_by(user_id=user.id).first()
        assert sess is not None
        msg = s.query(Message).filter_by(session_id=sess.id, role="user").first()
        assert msg is not None
        assert msg.text == "Pesa ngapi?"


def test_dispute_keyword_flow_returns_200(app, seed):
    """Reporting a wrong answer files a dispute (or returns a graceful
    message if no prior answer exists)."""
    client, _ = app
    phone = "+254700000043"

    # First, get an answer by asking a question.
    client.post("/whatsapp/incoming", data={"from": phone, "text": "Pesa ngapi?"})

    # Then report it.
    r = client.post("/whatsapp/incoming", data={"from": phone, "text": "SI SAHIHI"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Full admin API surface
# ---------------------------------------------------------------------------

def test_sources_full_lifecycle(app):
    """Create → Get → List → Patch → Delete a source through the full app."""
    client, headers = app

    # Create.
    r = client.post("/api/sources", json={
        "url": "https://example.com/system-test.pdf",
        "title": "System Test Source",
        "publisher": "OAG",
        "government_arm": "executive",
        "county": "nakuru",
        "report_type": "audit_report",
        "fiscal_year": "2024/25",
    }, headers=headers)
    assert r.status_code == 201
    src_id = r.json()["id"]

    # Get.
    r = client.get(f"/api/sources/{src_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "System Test Source"

    # List.
    r = client.get("/api/sources", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    # Patch.
    r = client.patch(f"/api/sources/{src_id}", json={"title": "Renamed"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"

    # Delete.
    r = client.delete(f"/api/sources/{src_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Verify gone.
    r = client.get(f"/api/sources/{src_id}", headers=headers)
    assert r.status_code == 404


def test_stats_has_all_required_keys(app):
    client, headers = app
    r = client.get("/api/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("total_sources", "total_chunks", "total_messages",
                "total_disputes", "sources_by_status", "disputes_by_status",
                "unique_citizens", "queries_today", "queries_this_week"):
        assert key in body, f"Missing key: {key}"


def test_sessions_and_messages_work_together(app):
    """After a webhook creates a session, /api/sessions and /api/messages
    reflect it."""
    client, headers = app
    phone = "+254700000044"

    # Create a session via webhook.
    client.post("/whatsapp/incoming", data={"from": phone, "text": "Habari?"})

    # Check sessions.
    r = client.get("/api/sessions", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    # Get session_id and check messages.
    sid = r.json()["sessions"][0]["id"]
    r = client.get(f"/api/messages?session_id={sid}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["messages"]) >= 1


def test_disputes_list_after_webhook_report(app, seed):
    """A dispute created via webhook report keyword appears in /api/disputes."""
    client, headers = app
    phone = "+254700000045"

    # Seed: question + answer.
    from src.shared.database import get_session
    from src.shared.models import Message, Session, User
    from src.api.middleware.identity import hash_wa_id

    client.post("/whatsapp/incoming", data={"from": phone, "text": "Pesa ngapi?"})

    with get_session() as s:
        user = s.query(User).filter_by(hashed_wa_id=hash_wa_id(phone)).first()
        sess = s.query(Session).filter_by(user_id=user.id).first()
        s.add(Message(session_id=sess.id, role="assistant",
                      text="Jibu. Chanzo: test.pdf"))

    # Report it.
    client.post("/whatsapp/incoming", data={"from": phone, "text": "si kweli"})

    # Check disputes.
    r = client.get("/api/disputes", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_validation_queue_and_stats(app, seed):
    """The validation endpoints work through the full app."""
    client, headers = app

    # Queue (should be empty initially).
    r = client.get("/api/validation/queue", headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] >= 0

    # Stats.
    r = client.get("/api/validation/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "total_validations" in body
    assert "average_tone" in body
    assert "pending_review" in body


def test_all_endpoints_require_auth(app):
    """Every /api/* endpoint rejects requests without a token."""
    client, _ = app
    endpoints = [
        "/api/sources", "/api/stats", "/api/disputes",
        "/api/sessions", "/api/messages",
        "/api/validation/queue", "/api/validation/stats",
    ]
    for ep in endpoints:
        r = client.get(ep)
        assert r.status_code in (401, 403), f"{ep} allowed unauthenticated: {r.status_code}"


def test_404_on_nonexistent_resource(app):
    """GET /api/sources/999999 → 404."""
    client, headers = app
    r = client.get("/api/sources/999999", headers=headers)
    assert r.status_code == 404
