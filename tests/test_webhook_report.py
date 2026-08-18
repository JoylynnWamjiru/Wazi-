"""Integration test for the WhatsApp report-keyword path in the webhook.

Marked ``db`` — SQLite fixture. The outbound WhatsApp send is stubbed so
no network call is made.
"""

import pytest

pytestmark = pytest.mark.db

PHONE = "+254700000001"


@pytest.fixture
def client(db, monkeypatch):
    """A TestClient over the webhook router, with send_whatsapp stubbed."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api import webhooks

    sent: list[dict] = []

    async def _fake_send(phone: str, message: str):
        sent.append({"phone": phone, "message": message})

    monkeypatch.setattr(webhooks, "send_whatsapp", _fake_send)

    app = FastAPI()
    app.include_router(webhooks.router)
    tc = TestClient(app)
    tc.sent = sent  # expose captured sends to the test
    return tc


def _seed_answer_for_phone(seed, db):
    """Create the user (by hashed phone) + session + one assistant answer."""
    from src.api.middleware.identity import hash_wa_id

    uid = seed.user(hash_wa_id(PHONE))
    sid = seed.session(uid)
    seed.message(sid, "assistant", "Kshs 14.13 bilioni. Chanzo: nakuru_birr_q1.pdf")
    return uid


def _dispute_count(db) -> int:
    from src.shared.models import Dispute

    with db.get_session() as s:
        return s.query(Dispute).count()


def test_report_keyword_files_a_dispute(client, seed, db):
    _seed_answer_for_phone(seed, db)

    # 1. The keyword prompts for a reason — no dispute filed yet.
    resp = client.post("/whatsapp/incoming", data={"from": PHONE, "text": "SI SAHIHI"})
    assert resp.status_code == 200
    assert _dispute_count(db) == 0

    # 2. The follow-up reason files the dispute, with the reason stored.
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "The figure is wrong."})
    assert _dispute_count(db) == 1
    assert any("Asante kwa kuripoti" in s["message"] for s in client.sent)
    assert any("Thank you for reporting" in s["message"] for s in client.sent)

    from src.shared.models import Dispute
    with db.get_session() as s:
        assert s.query(Dispute).first().reason == "The figure is wrong."


def test_report_prompts_for_reason_before_filing(client, seed, db):
    _seed_answer_for_phone(seed, db)

    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "ripoti"})

    prompt = client.sent[-1]["message"]
    assert "why you think this answer is wrong" in prompt
    assert "kwa nini unafikiri jibu hili si sahihi" in prompt
    assert _dispute_count(db) == 0


def test_single_report_reply_is_bilingual_and_does_not_imply_review(client, seed, db):
    _seed_answer_for_phone(seed, db)

    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "si sahihi"})
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "The amount is wrong."})

    reply = client.sent[-1]["message"]  # the acknowledgment after the reason
    assert "Thank you for reporting" in reply
    assert "Tutakufahamisha" in reply          # "we will update you" (accurate)
    assert "Asante kwa kuripoti" in reply
    assert "litakaguliwa na msimamizi" not in reply  # must not claim auto-review


def test_report_with_no_prior_answer_files_nothing(client, seed, db):
    # A brand-new user reports before ever getting an answer.
    resp = client.post("/whatsapp/incoming", data={"from": "+254999999999", "text": "ripoti"})

    assert resp.status_code == 200
    assert _dispute_count(db) == 0
    assert any("Hakuna jibu" in s["message"] for s in client.sent)
    assert any("no recent answer" in s["message"] for s in client.sent)


def test_duplicate_report_is_rejected_with_a_message(client, seed, db):
    _seed_answer_for_phone(seed, db)

    # First report + reason -> dispute created.
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "si sahihi"})
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "wrong figure"})
    assert _dispute_count(db) == 1

    # Second report + reason -> duplicate (no new row).
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "si sahihi"})
    client.post("/whatsapp/incoming", data={"from": PHONE, "text": "still wrong"})

    assert _dispute_count(db) == 1
    assert any("Tayari ulisharipoti" in s["message"] for s in client.sent)
    assert any("You have already reported" in s["message"] for s in client.sent)
