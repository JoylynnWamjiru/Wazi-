"""Tests for the Twilio inbound webhook path.

Twilio posts form-encoded ``Body`` / ``From`` / ``WaId`` fields (and signs
each request).  These tests confirm the webhook parses that shape,
canonicalizes the wa_id to E.164 so a Twilio ``WaId`` (no ``+``) hashes to
the same identity as an Africa's Talking ``from`` field, and wires the report
keyword into the existing dispute flow.  The outbound send is stubbed so no
network call is made.  Marked ``db`` — SQLite fixture.
"""

import pytest

pytestmark = pytest.mark.db

PHONE_E164 = "+254700000001"
WAID = "254700000001"  # Twilio's WaId — no leading "+"
FROM = "whatsapp:+254700000001"  # Twilio's From


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


def _post_twilio(client, body: str | None = None, **extra_fields):
    data = {"From": FROM, "WaId": WAID}
    if body is not None:
        data["Body"] = body
    data.update(extra_fields)
    return client.post("/whatsapp/incoming", data=data)


def _seed_answer_for_phone(seed, db):
    """Create the user (by hashed E.164 phone) + session + one answer."""
    from src.api.middleware.identity import hash_wa_id

    uid = seed.user(hash_wa_id(PHONE_E164))
    sid = seed.session(uid)
    seed.message(sid, "assistant", "Kshs 14.13 bilioni. Chanzo: nakuru_birr_q1.pdf")
    return uid


def _dispute_count(db) -> int:
    from src.shared.models import Dispute

    with db.get_session() as s:
        return s.query(Dispute).count()


def test_twilio_report_keyword_files_dispute(client, seed, db):
    """A Twilio-shaped report maps to the same user and files a dispute."""
    _seed_answer_for_phone(seed, db)

    resp = _post_twilio(client, "SI SAHIHI")

    assert resp.status_code == 200
    assert _dispute_count(db) == 1
    # The reply goes back to the canonicalized E.164 number, not Twilio's
    # "whatsapp:+254..." From value.
    assert client.sent
    assert client.sent[0]["phone"] == PHONE_E164
    assert any("Asante kwa kuripoti" in s["message"] for s in client.sent)


def test_twilio_missing_body_is_ignored(client, db):
    """A Twilio payload with no Body is silently dropped (200, no sends)."""
    resp = _post_twilio(client, None)

    assert resp.status_code == 200
    assert client.sent == []
