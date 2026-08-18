"""WhatsApp webhook receiver — the citizen entry point.

Accepts form-encoded POSTs from either messaging provider:

- **Africa's Talking** sends fields ``from`` (wa_id) and ``text`` (body).
- **Twilio** sends ``From`` (``whatsapp:+254...``), ``WaId`` (``254...``)
  and ``Body`` (message), signed with an ``X-Twilio-Signature`` header
  that is verified before the payload is touched.

Flow:
    1. Provider POSTs a form-encoded message
    2. Twilio requests have their signature validated (403 on failure)
    3. Webhook canonicalizes + hashes the wa_id → ``user_id`` immediately
    4. Finds or creates a User + Session; stores the user message
    5. Commits the session explicitly so the message_id is durable
       BEFORE the background task fires
    6. Sends an immediate acknowledgment: "Natafuta jibu..."
    7. Queues pipeline processing in a thread pool (not the event loop)
       so synchronous RAG + LLM calls don't block the async server
    8. Returns 200 OK within ~200ms

The pipeline (retrieval + generation) runs in a thread pool.  When it
finishes, the answer is sent as a second WhatsApp message.  This means
the citizen sees two messages: the ack, then the answer.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from src.api.messaging import (
    TWILIO_WEBHOOK_BASE_URL,
    send_whatsapp,
    validate_twilio_signature,
)
from src.api.middleware.identity import hash_wa_id
from src.api.middleware.rate_limit import block_notice_limiter, webhook_limiter
from src.shared.database import get_session
from src.shared.language import detect_language
from src.shared.models import Message, Session, User

logger = logging.getLogger(__name__)

router = APIRouter()

# A citizen reports a wrong answer by replying with one of these (case- and
# spacing-insensitive). Kept as exact normalized matches, not substrings, so a
# genuine question that happens to contain "si kweli" isn't mistaken for a report.
#
# To add new keywords, append to this set. Future: load from an env var
# (e.g. WAZI_REPORT_KEYWORDS="si sahihi,si kweli,ripoti,report") for
# hot-reload without redeployment.
_REPORT_KEYWORDS = frozenset({
    "si sahihi",   # "not correct" (formal Swahili)
    "sio sahihi",
    "si kweli",    # "not true"
    "sio kweli",
    "ripoti",      # "report"
    "report",
})


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for keyword matching."""
    return " ".join(text.lower().split())


def _is_report(text: str) -> bool:
    """True if the message is a dispute-report keyword, not a question."""
    return _normalize(text) in _REPORT_KEYWORDS


def _canonical_wa_id(value: str) -> str:
    """Normalize a wa_id to E.164 (``+2547...``).

    Africa's Talking already sends ``+2547...``.  Twilio sends ``WaId``
    without the leading ``+`` (``2547...``) and ``From`` as
    ``whatsapp:+2547...``.  Canonicalizing to E.164 means the same citizen
    hashes to the same identity whichever provider delivered the message.
    """
    value = (value or "").strip()
    if value.startswith("whatsapp:"):
        value = value[len("whatsapp:"):]
    if value and not value.startswith("+"):
        value = "+" + value
    return value


@router.post("/whatsapp/incoming")
async def incoming_message(request: Request, background: BackgroundTasks):
    """Receive a WhatsApp message from Africa's Talking or Twilio.

    Both providers POST ``application/x-www-form-urlencoded``:

    - Africa's Talking: ``from`` (wa_id) and ``text`` (body)
    - Twilio: ``From`` (``whatsapp:+254...``), ``WaId`` (``254...``),
      ``Body`` (message) — plus an ``X-Twilio-Signature`` header.

    Responds 200 OK immediately.  Pipeline processing happens in the
    background so the provider doesn't time out waiting for the LLM.
    """
    form = await request.form()

    provider = "twilio" if "Body" in form else "africastalking"
    # Log field NAMES (not values) so the real payload shape can be verified
    # against live Twilio traffic without logging any PII.
    logger.info("Incoming webhook provider=%s fields=%s", provider, sorted(form.keys()))

    # Twilio signs every request — verify before touching the payload.
    if provider == "twilio":
        url = TWILIO_WEBHOOK_BASE_URL or str(request.url)
        if not validate_twilio_signature(
            url, dict(form), request.headers.get("X-Twilio-Signature")
        ):
            logger.warning("Rejected webhook with invalid Twilio signature")
            return Response(status_code=403)

    if provider == "twilio":
        raw_wa_id = _canonical_wa_id(form.get("WaId") or form.get("From") or "")
        message_text = form.get("Body")
    else:
        raw_wa_id = _canonical_wa_id(form.get("from") or "")
        message_text = form.get("text")

    # Silently ignore empty or malformed messages.
    if not raw_wa_id or not message_text:
        logger.debug("Ignoring message with missing sender/body fields")
        return Response(status_code=200)

    # Hash the wa_id BEFORE anything else touches it.
    user_id = hash_wa_id(raw_wa_id)

    # Rate-limit per citizen (hashed id) before touching the DB or the LLM, so
    # a flooding number can't run up DeepSeek cost or overload the pipeline.
    allowed, retry_after = webhook_limiter.check(user_id)
    if not allowed:
        # Send the "slow down" reply at most once per window (a second, tiny
        # limiter) so a flood of blocked messages can't amplify into a flood
        # of outbound WhatsApp sends.
        notify, _ = block_notice_limiter.check(user_id)
        if notify:
            await send_whatsapp(
                phone=raw_wa_id,
                message=(
                    f"Umetuma maswali mengi kwa muda mfupi. Tafadhali subiri "
                    f"sekunde {int(retry_after)} kisha ujaribu tena. 🙏"
                ),
            )
        return Response(status_code=200)

    is_report = _is_report(message_text)

    # Upsert user and create session.  Commit explicitly BEFORE
    # queuing the background task so the message_id is durable.
    with get_session() as session:
        user = session.query(User).filter_by(hashed_wa_id=user_id).first()
        if user is None:
            user = User(hashed_wa_id=user_id)
            session.add(user)
            session.flush()

        user.last_active_at = datetime.now(timezone.utc)
        user_db_id = user.id

        # Use the most recent active session, or create a new one.
        active_session = (
            session.query(Session)
            .filter_by(user_id=user.id, is_active=True)
            .order_by(Session.created_at.desc())
            .first()
        )
        if active_session is None:
            active_session = Session(user_id=user.id)
            session.add(active_session)
            session.flush()

        # Store the incoming message (question OR report keyword) for history.
        user_msg = Message(
            session_id=active_session.id,
            role="user",
            text=message_text,
        )
        session.add(user_msg)
        session.flush()
        message_id = user_msg.id

        # A report targets the citizen's most recent assistant answer in
        # this session — resolve it while the session is open.
        target_answer_id = None
        if is_report:
            last_answer = (
                session.query(Message)
                .filter(
                    Message.session_id == active_session.id,
                    Message.role == "assistant",
                )
                .order_by(Message.id.desc())
                .first()
            )
            target_answer_id = last_answer.id if last_answer else None
        # The context manager commits on exit — ids are now durable.

    # --- Dispute-report path -------------------------------------------------
    if is_report:
        reply = await asyncio.to_thread(_handle_report, user_db_id, target_answer_id)
        await send_whatsapp(phone=raw_wa_id, message=reply)
        return Response(status_code=200)

    # --- Normal question path ------------------------------------------------
    # Send immediate acknowledgment.
    await send_whatsapp(
        phone=raw_wa_id,
        message="Natafuta jibu lako kwenye nyaraka za kaunti... ⏳",
    )

    # Queue the pipeline in the BACKGROUND — runs in a thread pool so
    # synchronous RAG + LLM calls don't block the async event loop.
    # The raw_wa_id is captured in the closure and garbage-collected
    # after the task completes — it is never stored or logged.
    background.add_task(
        _process_and_reply,
        raw_phone=raw_wa_id,
        message_id=message_id,
        query=message_text,
    )

    return Response(status_code=200)


def _bilingual(en: str, sw: str) -> str:
    """Join English and Swahili versions into one inclusive message."""
    return f"{en}\n{sw}"


def _source_label(reply: str) -> str:
    """Choose the citation label to match the reply's language."""
    return "Chanzo" if detect_language(reply) == "sw" else "Source"


def _handle_report(user_db_id: int, target_answer_id: int | None) -> str:
    """File a dispute against the citizen's last answer, guarded by anti-bot
    checks.  Returns a bilingual citizen-facing reply for each outcome.

    A single report is recorded but NOT escalated for human review — only
    ``DIVERSITY_THRESHOLD`` distinct reporters surface it.  The reply must
    not imply otherwise.
    """
    no_recent = _bilingual(
        "You have no recent answer to report. Please ask a question first.",
        "Hakuna jibu la hivi karibuni la kuripoti. Uliza swali kwanza.",
    ) + " 🙏"

    if target_answer_id is None:
        return no_recent

    from src.api.middleware.anti_bot import create_dispute

    verdict = create_dispute(
        message_id=target_answer_id,
        user_id=user_db_id,
        reason="Citizen flagged answer via WhatsApp report keyword",
    )

    if verdict["created"]:
        if verdict["flagged_for_review"]:
            return _bilingual(
                "Thank you. This answer has been reported by several people "
                "and will now be prioritized for review by a moderator.",
                "Asante. Jibu hili limeripotiwa na watu kadhaa na sasa "
                "litapewa kipaumbele cha ukaguzi na msimamizi.",
            ) + " 🙏"
        return _bilingual(
            "Thank you for reporting. We will update you on the status of "
            "this report.",
            "Asante kwa kuripoti. Tutakufahamisha kuhusu hali ya ripoti hii.",
        ) + " 🙏"

    if verdict["reason"] == "duplicate":
        return _bilingual(
            "You have already reported this answer. Thank you.",
            "Tayari ulisharipoti jibu hili. Asante kwa msaada wako.",
        ) + " 🙏"
    if verdict["reason"] == "rate_limited":
        wait = int(verdict.get("retry_after") or 0)
        return _bilingual(
            f"Please wait {wait} seconds before reporting again.",
            f"Tafadhali subiri sekunde {wait} kabla ya kuripoti tena.",
        )
    # message_not_found / not_an_answer — shouldn't normally happen.
    return no_recent


async def _process_and_reply(raw_phone: str, message_id: int, query: str) -> None:
    """Run the RAG pipeline in a thread pool and send the answer.

    The pipeline (FAISS/pgvector search + DeepSeek HTTP call) is
    synchronous and blocking — it runs in ``asyncio.to_thread()`` so
    it doesn't freeze the FastAPI event loop.

    The ``raw_phone`` parameter is held ONLY in this function's closure.
    It is never written to the database, logs are masked, and it is
    garbage-collected when this coroutine completes.
    """
    answer = None
    try:
        # Offload the blocking pipeline to a thread pool.
        answer = await asyncio.to_thread(_run_pipeline, query)
        reply = answer["text"]
        citation = answer.get("citation", "N/A")

        if citation and citation != "N/A":
            reply += f"\n\n📄 {_source_label(reply)}: {citation}"

    except Exception:
        logger.exception("Pipeline failed for query: %s", query[:100])
        reply = "Samahani, sina jibu la uhakika kwa swali hili sasa hivi."

    # Store the assistant's answer.
    with get_session() as session:
        msg = session.query(Message).filter_by(id=message_id).first()
        if msg is None:
            logger.error("Message %s not found — cannot store answer", message_id)
            return
        chunks = (answer or {}).get("chunks", [])
        assistant_msg = Message(
            session_id=msg.session_id,
            role="assistant",
            text=reply,
            citation=answer.get("citation") if answer else None,
            retrieved_chunks=(
                json.dumps(
                    [
                        {
                            "source_title": c.get("source_title"),
                            "page_number": c.get("page_number"),
                            "government_arm": c.get("government_arm"),
                            "chunk_text": c.get("chunk_text"),
                        }
                        for c in chunks
                    ]
                )
                if chunks
                else None
            ),
        )
        session.add(assistant_msg)

    await send_whatsapp(phone=raw_phone, message=reply)


def _run_pipeline(query: str) -> dict:
    """Synchronous wrapper around the RAG pipeline.

    Runs in a thread pool via ``asyncio.to_thread()`` so the event loop
    stays free.  Imports ``orchestrate.get_response`` directly — the clean
    entry point that ties pgvector retrieval + DeepSeek generation.
    """
    from src.ingestion.orchestrate import get_response
    return get_response(query)
