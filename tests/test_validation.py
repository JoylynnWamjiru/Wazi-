"""Tests for the linguist-validation API (/api/validation/*).

Self-contained: sets a SQLite DATABASE_URL and builds its own in-memory DB +
fixture, so it runs with no PostgreSQL AND without depending on the shared
tests/conftest.py (which lands separately in #18). Once both are in main the
two coexist — this file uses its own `api` fixture, no name clash.
"""

import os
import tempfile

# Must be set before src.shared.database is imported (it builds the engine at
# import). A file URL so the default pool accepts pool_size.
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.gettempdir(), "wazi_val_test.db"),
)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def api(monkeypatch):
    """In-memory SQLite + a minimal app mounting only the validation router."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from src.shared import database
    from src.shared.models import Base, Message, Session, User, Validation
    from src.api.middleware import auth
    from src.api.routes.validation import router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Session.__table__,
            Message.__table__,
            Validation.__table__,
        ],
    )
    monkeypatch.setattr(database, "_SessionFactory", sessionmaker(bind=engine))

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth.ADMIN_PASSWORD}"}
    return client, headers, database


def _seed_answer(database, answer="Kshs 14.13 bilioni", citation="source 1, page 2"):
    """Create a user question + assistant answer; return the answer's id."""
    from src.shared.models import Message, Session, User

    with database.get_session() as s:
        u = User(hashed_wa_id="h1")
        s.add(u)
        s.flush()
        sess = Session(user_id=u.id)
        s.add(sess)
        s.flush()
        q = Message(session_id=sess.id, role="user", text="Pesa ngapi?")
        s.add(q)
        s.flush()
        a = Message(session_id=sess.id, role="assistant", text=answer, citation=citation)
        s.add(a)
        s.flush()
        return a.id


def _valid_body(**over):
    body = {"tone_score": 4, "grounded": True, "register": "formal_swahili", "notes": "ok"}
    body.update(over)
    return body


# --- Auth -------------------------------------------------------------------

def test_queue_requires_auth(api):
    client, _, _ = api
    assert client.get("/api/validation/queue").status_code in (401, 403)


# --- Queue ------------------------------------------------------------------

def test_queue_lists_unrated_answer_with_context(api):
    client, headers, database = api
    answer_id = _seed_answer(database)

    r = client.get("/api/validation/queue", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    item = body["queue"][0]
    assert item["message_id"] == answer_id
    assert item["question"] == "Pesa ngapi?"      # preceding user message
    assert item["citation"] == "source 1, page 2"


# --- Submit -----------------------------------------------------------------

def test_submit_validation_then_removed_from_queue(api):
    client, headers, database = api
    answer_id = _seed_answer(database)

    r = client.post(f"/api/validation/{answer_id}", json=_valid_body(), headers=headers)
    assert r.status_code == 201
    assert r.json()["register"] == "formal_swahili"

    # Rated answers no longer appear in the queue.
    q = client.get("/api/validation/queue", headers=headers).json()
    assert q["count"] == 0


def test_tone_score_out_of_range_is_422(api):
    client, headers, database = api
    answer_id = _seed_answer(database)
    r = client.post(f"/api/validation/{answer_id}", json=_valid_body(tone_score=6), headers=headers)
    assert r.status_code == 422


def test_invalid_register_is_422(api):
    client, headers, database = api
    answer_id = _seed_answer(database)
    r = client.post(f"/api/validation/{answer_id}", json=_valid_body(register="klingon"), headers=headers)
    assert r.status_code == 422


def test_cannot_validate_a_user_message(api):
    client, headers, database = api
    from src.shared.models import Message, Session, User

    with database.get_session() as s:
        u = User(hashed_wa_id="h2"); s.add(u); s.flush()
        sess = Session(user_id=u.id); s.add(sess); s.flush()
        q = Message(session_id=sess.id, role="user", text="swali"); s.add(q); s.flush()
        qid = q.id

    r = client.post(f"/api/validation/{qid}", json=_valid_body(), headers=headers)
    assert r.status_code == 422


def test_validate_missing_message_is_404(api):
    client, headers, _ = api
    assert client.post("/api/validation/999999", json=_valid_body(), headers=headers).status_code == 404


# --- Stats ------------------------------------------------------------------

def test_stats_reflect_a_submitted_validation(api):
    client, headers, database = api
    answer_id = _seed_answer(database)
    client.post(f"/api/validation/{answer_id}", json=_valid_body(tone_score=5, grounded=True), headers=headers)

    stats = client.get("/api/validation/stats", headers=headers).json()
    assert stats["total_validations"] == 1
    assert stats["average_tone"] == 5.0
    assert stats["grounded_pct"] == 100.0
    assert stats["by_register"]["formal_swahili"] == 1
    assert stats["pending_review"] == 0
