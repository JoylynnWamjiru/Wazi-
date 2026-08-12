"""WhatsApp webhook receiver — the citizen entry point.

Africa's Talking sends incoming WhatsApp messages as form-encoded POST
requests to the callback URL configured in the AT dashboard.

Flow:
    1. AT sends POST with form fields (``from``, ``text``, etc.)
    2. Webhook hashes ``wa_id`` → ``user_id`` immediately
    3. Finds or creates a User + Session; stores the user message
    4. Commits the session explicitly so the message_id is durable
       BEFORE the background task fires
    5. Sends an immediate acknowledgment: "Natafuta jibu..."
    6. Queues pipeline processing in a thread pool (not the event loop)
       so synchronous RAG + LLM calls don't block the async server
    7. Returns 200 OK to AT within ~200ms

The pipeline (retrieval + generation) runs in a thread pool.  When it
finishes, the answer is sent as a second WhatsApp message.  This means
the citizen sees two messages: the ack, then the answer.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from src.api.messaging import send_whatsapp
from src.api.middleware.identity import hash_wa_id
from src.api.middleware.rate_limit import webhook_limiter
from src.shared.database import get_session
from src.shared.models import Message, Session, User

logger = logging.getLogger(__name__)

router = APIRouter()

# A citizen reports a wrong answer by replying with one of these (case- and
# spacing-insensitive). Kept as exact normalized matches, not substrings, so a
# genuine question that happens to contain "si kweli" isn't mistaken for a report.
REPORT_KEYWORDS = frozenset({
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
    return _normalize(text) in REPORT_KEYWORDS


@router.post("/whatsapp/incoming")
async def incoming_message(request: Request, background: BackgroundTasks):
    """Receive a WhatsApp message from Africa's Talking.

    The webhook payload is ``application/x-www-form-urlencoded`` with
    fields like ``from`` (wa_id) and ``text`` (message body).

    Responds 200 OK immediately.  Pipeline processing happens in the
    background so AT doesn't time out waiting for the LLM.
    """
    form = await request.form()

    raw_wa_id = form.get("from")
    message_text = form.get("text")

    # Silently ignore empty or malformed messages.
    if not raw_wa_id or not message_text:
        logger.debug("Ignoring message with missing from/text fields")
        return Response(status_code=200)

    # Hash the wa_id BEFORE anything else touches it.
    user_id = hash_wa_id(raw_wa_id)

    # Rate-limit per citizen (hashed id) before touching the DB or the LLM, so
    # a flooding number can't run up DeepSeek cost or overload the pipeline.
    allowed, retry_after = webhook_limiter.check(user_id)
    if not allowed:
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
        reply = _handle_report(user_db_id, target_answer_id)
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


def _handle_report(user_db_id: int, target_answer_id: int | None) -> str:
    """File a dispute against the citizen's last answer, guarded by anti-bot
    checks.  Returns the citizen-facing reply for each outcome."""
    if target_answer_id is None:
        return "Hakuna jibu la hivi karibuni la kuripoti. Uliza swali kwanza. 🙏"

    from src.api.middleware.anti_bot import create_dispute

    verdict = create_dispute(
        message_id=target_answer_id,
        user_id=user_db_id,
        reason="Citizen flagged answer via WhatsApp report keyword",
    )

    if verdict["created"]:
        if verdict["flagged_for_review"]:
            return (
                "Asante. Jibu hili limeripotiwa na watu kadhaa na sasa "
                "litapewa kipaumbele cha ukaguzi na msimamizi. 🙏"
            )
        return "Asante kwa kuripoti. Jibu hili litakaguliwa na msimamizi. 🙏"

    if verdict["reason"] == "duplicate":
        return "Tayari ulisharipoti jibu hili. Asante kwa msaada wako. 🙏"
    if verdict["reason"] == "rate_limited":
        wait = int(verdict.get("retry_after") or 0)
        return f"Tafadhali subiri sekunde {wait} kabla ya kuripoti tena."
    # message_not_found / not_an_answer — shouldn't normally happen.
    return "Hakuna jibu la hivi karibuni la kuripoti. Uliza swali kwanza. 🙏"


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
            reply += f"\n\n📄 Chanzo: {citation}"

    except Exception:
        logger.exception("Pipeline failed for query: %s", query[:100])
        reply = "Samahani, sina jibu la uhakika kwa swali hili sasa hivi."

    # Store the assistant's answer.
    with get_session() as session:
        msg = session.query(Message).filter_by(id=message_id).first()
        if msg is None:
            logger.error("Message %s not found — cannot store answer", message_id)
            return
        assistant_msg = Message(
            session_id=msg.session_id,
            role="assistant",
            text=reply,
            citation=answer.get("citation") if answer else None,
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
