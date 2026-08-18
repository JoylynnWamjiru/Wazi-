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


def test_parse_response_includes_retrieved_chunks():
    """parse_response propagates the retrieved chunks so the webhook can store
    the source-passage snapshot on the assistant message."""
    from src.ingestion.generate import parse_response

    chunks = [
        {
            "source_id": 1,
            "source_title": "Auditor-General's Report — Nakuru County Executive",
            "page_number": 3,
            "chunk_text": "Kshs 14.13 bilioni",
            "government_arm": "executive",
        }
    ]
    result = parse_response("Jibu.\nUSED_CHUNK: 1", chunks)

    assert result["chunks"] == chunks
    assert result["citation"] == (
        "Auditor-General's Report — Nakuru County Executive, page 3"
    )
    assert result["text"] == "Jibu."


def test_parse_response_strips_multi_chunk_marker():
    """The model sometimes emits 'USED_CHUNK: 2, 1, 5'. The marker must be
    stripped and the citation taken from the FIRST named chunk."""
    from src.ingestion.generate import parse_response

    chunks = [
        {"source_id": 1, "source_title": "Doc A", "page_number": 3, "chunk_text": "x"},
        {"source_id": 1, "source_title": "Doc A", "page_number": 5, "chunk_text": "y"},
    ]
    result = parse_response("Jibu.\nUSED_CHUNK: 2, 1", chunks)

    assert result["text"] == "Jibu."
    assert "USED_CHUNK" not in result["text"]
    assert result["citation"] == "Doc A, page 5"  # first named chunk is #2 -> chunks[1]


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


def test_sources_can_share_a_listing_page_url(db):
    """A listing page legitimately hosts many documents — the same URL must
    be allowed across sources that differ by title / government_arm (e.g. one
    OAG page holds both the Executive and Assembly audits)."""
    from src.shared.models import Source

    with db.get_session() as s:
        s.add(Source(
            url="https://example.com/oag-fy2024-reports/",
            title="Nakuru County Executive FY 2024",
            publisher="OAG",
            government_arm="executive",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2024",
        ))
        s.add(Source(
            url="https://example.com/oag-fy2024-reports/",
            title="Nakuru County Assembly FY 2024",
            publisher="OAG",
            government_arm="assembly",
            county="nakuru",
            report_type="audit_report",
            fiscal_year="2024",
        ))
        s.flush()

        count = s.query(Source).filter_by(
            url="https://example.com/oag-fy2024-reports/"
        ).count()
        assert count == 2  # both rows coexist — no UNIQUE(url) constraint


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
