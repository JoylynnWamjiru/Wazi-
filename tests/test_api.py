"""Tests for the admin API routes — sources CRUD, stats, disputes list.

Marked ``db`` — in-memory SQLite fixture. A bare ``chunks`` table is created
by raw SQL (the routes only COUNT/filter chunks; they never read the pgvector
embedding), so these run with no PostgreSQL.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.db

VALID_SOURCE = {
    "url": "https://oag.example/nakuru",
    "title": "Nakuru Executive Audit FY2023/24",
    "publisher": "OAG",
    "government_arm": "executive",
    "county": "nakuru",
    "report_type": "audit_report",
    "fiscal_year": "2023/24",
}

# A minimal chunks table: every column the ORM maps, embedding as plain TEXT so
# SQLite accepts it. The admin routes only count/filter, never bind embeddings.
_CHUNKS_TABLE = text("""
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


@pytest.fixture
def api(db):
    """Minimal app (routers only, no lifespan/init_db) + auth header."""
    from src.api.middleware import auth
    from src.api.routes.disputes import router as disputes_router
    from src.api.routes.sources import router as sources_router
    from src.api.routes.stats import router as stats_router

    with db.get_session() as s:
        s.execute(_CHUNKS_TABLE)

    app = FastAPI()
    app.include_router(sources_router)
    app.include_router(stats_router)
    app.include_router(disputes_router)

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth.ADMIN_PASSWORD}"}
    return client, headers


# --- Auth -------------------------------------------------------------------

def test_missing_token_is_rejected(api):
    client, _ = api
    r = client.get("/api/sources")
    assert r.status_code in (401, 403)


def test_wrong_token_is_401(api):
    client, _ = api
    r = client.get("/api/sources", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# --- Sources CRUD -----------------------------------------------------------

def test_create_source_returns_201_pending(api):
    client, headers = api
    r = client.post("/api/sources", json=VALID_SOURCE, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == VALID_SOURCE["title"]
    assert body["ingestion_status"] == "pending"
    assert body["chunk_count"] == 0
    assert isinstance(body["id"], int)


def test_get_and_list_reflect_created_source(api):
    client, headers = api
    created = client.post("/api/sources", json=VALID_SOURCE, headers=headers).json()

    got = client.get(f"/api/sources/{created['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == VALID_SOURCE["title"]

    listed = client.get("/api/sources", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 1
    assert any(s["id"] == created["id"] for s in payload["sources"])


def test_get_missing_source_is_404(api):
    client, headers = api
    assert client.get("/api/sources/999999", headers=headers).status_code == 404


def test_patch_updates_title(api):
    client, headers = api
    created = client.post("/api/sources", json=VALID_SOURCE, headers=headers).json()

    r = client.patch(
        f"/api/sources/{created['id']}",
        json={"title": "Renamed audit"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed audit"


def test_delete_source_then_404(api):
    client, headers = api
    created = client.post("/api/sources", json=VALID_SOURCE, headers=headers).json()

    deleted = client.delete(f"/api/sources/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    assert client.get(f"/api/sources/{created['id']}", headers=headers).status_code == 404


# --- Stats ------------------------------------------------------------------

def test_stats_shape_on_empty_db(api):
    client, headers = api
    r = client.get("/api/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()

    for key in ("total_sources", "total_chunks", "total_messages",
                "total_disputes", "sources_by_status", "disputes_by_status",
                "unique_citizens", "queries_today", "queries_this_week"):
        assert key in body

    assert body["total_chunks"] == 0
    # Every enum value present even when its count is zero.
    assert set(body["sources_by_status"]) >= {"pending", "in_progress", "completed", "failed"}
    assert "pending_review" in body["disputes_by_status"]


def test_stats_counts_a_created_source(api):
    client, headers = api
    before = client.get("/api/stats", headers=headers).json()["total_sources"]
    client.post("/api/sources", json=VALID_SOURCE, headers=headers)
    after = client.get("/api/stats", headers=headers).json()
    assert after["total_sources"] == before + 1
    assert after["sources_by_status"]["pending"] >= 1


# --- Disputes list ----------------------------------------------------------

def test_disputes_list_empty(api):
    client, headers = api
    r = client.get("/api/disputes", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"disputes": [], "total": 0, "limit": 50, "offset": 0}


def test_disputes_list_after_a_report(api, seed):
    client, headers = api
    from src.api.middleware.anti_bot import create_dispute

    uid = seed.user("hash_x")
    sid = seed.session(uid)
    answer_id = seed.message(sid, "assistant", "Kshs 14.13 bilioni")
    verdict = create_dispute(answer_id, uid)
    assert verdict["created"] is True

    r = client.get("/api/disputes", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["disputes"][0]["message_id"] == answer_id
    assert body["disputes"][0]["report_count"] == 1


def test_get_dispute_returns_retrieved_passages(api, seed):
    """The moderation view exposes the exact source passages the model was
    shown — the human-verification loop's core evidence."""
    import json

    from src.api.middleware.anti_bot import create_dispute

    client, headers = api
    uid = seed.user("hash_y")
    sid = seed.session(uid)
    passages = [
        {
            "source_title": "Auditor-General's Report — Nakuru County Executive",
            "page_number": 3,
            "government_arm": "executive",
            "chunk_text": "Kshs 14.13 bilioni",
        }
    ]
    answer_id = seed.message(
        sid, "assistant", "Kshs 14.13 bilioni", retrieved_chunks=json.dumps(passages)
    )
    assert create_dispute(answer_id, uid)["created"] is True

    listed = client.get("/api/disputes", headers=headers).json()
    dispute_id = listed["disputes"][0]["id"]

    body = client.get(f"/api/disputes/{dispute_id}", headers=headers).json()
    assert body["retrieved_chunks"] == passages
    assert body["message_preview"]["text"] == "Kshs 14.13 bilioni"


def test_get_dispute_returns_user_question(api, seed):
    """A real Q&A pair (user question followed by an answer) must load without
    a DetachedInstanceError — the user question is read inside the session."""
    from src.api.middleware.anti_bot import create_dispute

    client, headers = api
    uid = seed.user("hash_q")
    sid = seed.session(uid)
    seed.message(sid, "user", "Mradi wa Keringet iliendaje?")
    answer_id = seed.message(sid, "assistant", "Ujenzi ulisimama.")
    assert create_dispute(answer_id, uid)["created"] is True

    listed = client.get("/api/disputes", headers=headers).json()
    dispute_id = listed["disputes"][0]["id"]

    body = client.get(f"/api/disputes/{dispute_id}", headers=headers).json()
    assert body["user_question"]["text"] == "Mradi wa Keringet iliendaje?"
    assert body["message_preview"]["text"] == "Ujenzi ulisimama."


def test_escalation_report_packages_passages_as_proof(api, seed):
    """Escalating a dispute packages the retrieved passages into the report,
    so the recipient receives the source evidence alongside the answer."""
    import json

    from src.api.middleware.anti_bot import create_dispute

    client, headers = api
    uid = seed.user("hash_z")
    sid = seed.session(uid)
    passages = [
        {
            "source_title": "County Governments BIRR",
            "page_number": 7,
            "government_arm": "consolidated",
            "chunk_text": "Pending bills stood at Kshs 2.1 bilioni.",
        }
    ]
    answer_id = seed.message(
        sid, "assistant", "Pending bills were Kshs 2.1 bilioni.",
        retrieved_chunks=json.dumps(passages),
    )
    assert create_dispute(answer_id, uid)["created"] is True

    listed = client.get("/api/disputes", headers=headers).json()
    dispute_id = listed["disputes"][0]["id"]

    # under_review -> escalated (valid transition chain).
    client.patch(
        f"/api/disputes/{dispute_id}",
        json={"status": "under_review"},
        headers=headers,
    )
    r = client.patch(
        f"/api/disputes/{dispute_id}",
        json={"status": "escalated", "escalation_recipient": "eacc@example.go.ke"},
        headers=headers,
    )
    assert r.status_code == 200
    report = r.json()["escalation_report"]
    assert report["recipient"] == "eacc@example.go.ke"
    assert report["content"]["retrieved_passages"] == passages
    assert report["content"]["citation"] is None
