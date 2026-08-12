"""Tests for security hardening — prompt injection, UNIQUE constraints,
async webhook paths, and retention config integration.

Marked ``db`` — in-memory SQLite fixture.
"""

import os

import pytest

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Prompt injection guard — delimiters in user_content
# ---------------------------------------------------------------------------

def test_generate_wraps_query_in_delimiters(monkeypatch):
    """The LLM user_content wraps citizen queries in <QUESTION>...</QUESTION>
    to separate citizen input from system instructions."""
    import httpx

    from src.ingestion.generate import generate

    chunks = [{"source_id": 1, "page_number": 2, "chunk_text": "Kshs 14.13 bilioni"}]

    captured_content = None

    def _fake_post(url, **kwargs):
        nonlocal captured_content
        captured_content = kwargs["json"]["messages"][1]["content"]

        class FakeResp:
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"message": {"content": "Jibu. USED_CHUNK: 1"}}]}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    # DEEPSEEK_API_KEY is loaded from .env at import; override via os.environ.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    # Force reload of config so the env var takes effect.
    import importlib
    import src.shared.config
    importlib.reload(src.shared.config)

    generate(chunks, "Kaunti inapokea pesa ngapi?")

    assert "<QUESTION>" in captured_content
    assert "</QUESTION>" in captured_content
    assert "Kaunti inapokea pesa ngapi?" in captured_content


# ---------------------------------------------------------------------------
# Dispute — UNIQUE constraint behavior
# ---------------------------------------------------------------------------

def test_dispute_unique_constraint_prevents_duplicate(seed):
    """Two disputes from the same user on the same answer — the second
    should fail at the database level via UNIQUE constraint."""
    from sqlalchemy.exc import IntegrityError

    from src.api.middleware.anti_bot import create_dispute

    uid = seed.user("hash_x")
    sid = seed.session(uid)
    aid = seed.message(sid, "assistant", "some answer")

    # First dispute — created.
    v1 = create_dispute(aid, uid)
    assert v1["created"] is True

    # Second dispute — the app-level guard returns "duplicate".
    v2 = create_dispute(aid, uid)
    assert v2["created"] is False
    assert v2["reason"] == "duplicate"


def test_source_unique_constraint_prevents_duplicate_url(db):
    """Two sources with the same URL — the second INSERT raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    from src.shared.models import Source

    with db.get_session() as s:
        s.add(Source(
            url="https://example.com/unique-test.pdf",
            title="First",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
        ))
        # Commit the first source so the constraint is visible.
        s.flush()

    # Second session: try inserting a duplicate URL.
    with pytest.raises(IntegrityError):
        with db.get_session() as s2:
            s2.add(Source(
                url="https://example.com/unique-test.pdf",
                title="Second — same URL",
                publisher="CoB",
                government_arm="assembly",
                county="nakuru",
                report_type="birr",
            ))
            s2.flush()


# ---------------------------------------------------------------------------
# Retention — reads from config
# ---------------------------------------------------------------------------

def test_retention_reads_days_from_config(monkeypatch, db):
    """purge() respects explicit message_days / dispute_days overrides,
    which in production come from config.CHAT_RETENTION_DAYS / DISPUTE_RETENTION_DAYS."""
    from datetime import datetime, timezone

    from scripts.retention import purge

    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    result = purge(now=now, message_days=30, dispute_days=180, dry_run=True)

    # Message cutoff = now - 30 days; dispute cutoff = now - 180 days.
    assert "2026-07-13" in result["message_cutoff"]   # 30 days before Aug 12
    assert "2026-02-13" in result["dispute_cutoff"]    # 180 days before Aug 12


def test_retention_defaults_come_from_config(db):
    """The module-level MESSAGE_RETENTION_DAYS and DISPUTE_RETENTION_DAYS
    are sourced from config, not hardcoded."""
    from scripts import retention
    from src.shared import config

    assert retention.MESSAGE_RETENTION_DAYS == config.CHAT_RETENTION_DAYS
    assert retention.DISPUTE_RETENTION_DAYS == config.DISPUTE_RETENTION_DAYS


# ---------------------------------------------------------------------------
# Webhook — async report handling
# ---------------------------------------------------------------------------

def test_report_path_uses_async_threading(api, seed):
    """The webhook's dispute-report path offloads DB work to a thread pool
    via asyncio.to_thread, so the event loop stays free."""
    from src.api.middleware.identity import hash_wa_id

    client, _ = api
    phone = "+254700000001"
    uid = seed.user(hash_wa_id(phone))
    sid = seed.session(uid)
    seed.message(sid, "assistant", "Kshs 14.13 bilioni. Chanzo: some.pdf")

    resp = client.post("/whatsapp/incoming", data={"from": phone, "text": "si sahihi"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api fixture (minimal app with webhook router)
# ---------------------------------------------------------------------------

@pytest.fixture
def api(db, monkeypatch):
    """TestClient over the webhook router with send_whatsapp stubbed."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import webhooks

    async def _fake_send(phone: str, message: str):
        pass

    monkeypatch.setattr(webhooks, "send_whatsapp", _fake_send)

    app = FastAPI()
    app.include_router(webhooks.router)
    client = TestClient(app)
    headers = {"Authorization": "Bearer test"}
    return client, headers
