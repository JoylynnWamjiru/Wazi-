"""WhatsApp webhook receiver — the citizen entry point.

Africa's Talking sends incoming WhatsApp messages as form-encoded POST
requests to the callback URL configured in the AT dashboard.

Flow:
    1. AT sends POST with form fields (``from``, ``text``, etc.)
    2. Webhook hashes ``wa_id`` → ``user_id`` immediately
    3. Finds or creates a User + Session in the database
    4. Sends an immediate acknowledgment: "Natafuta jibu..."
    5. Queues the actual pipeline processing as a background task
    6. Returns 200 OK to AT within ~200ms

The pipeline (retrieval + generation) runs asynchronously.  When it
finishes, the answer is sent as a second WhatsApp message.  This means
the citizen sees two messages: the ack, then the answer.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from src.api.messaging import send_whatsapp
from src.api.middleware.identity import hash_wa_id
from src.shared.database import get_session
from src.shared.models import Message, Session, User

logger = logging.getLogger(__name__)

router = APIRouter()


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

    # Upsert user and create session.
    with get_session() as session:
        user = session.query(User).filter_by(hashed_wa_id=user_id).first()
        if user is None:
            user = User(hashed_wa_id=user_id)
            session.add(user)
            session.flush()

        user.last_active_at = datetime.now(timezone.utc)

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

        # Store the user's question.
        user_msg = Message(
            session_id=active_session.id,
            role="user",
            text=message_text,
        )
        session.add(user_msg)
        session.flush()
        message_id = user_msg.id

    # Send immediate acknowledgment.
    await send_whatsapp(
        phone=raw_wa_id,
        message="Natafuta jibu lako kwenye nyaraka za kaunti... ⏳",
    )

    # Queue the pipeline in the background.
    # The raw_wa_id is captured in the closure and garbage-collected
    # after the task completes — it is never stored or logged.
    background.add_task(
        _process_and_reply,
        raw_phone=raw_wa_id,
        message_id=message_id,
        query=message_text,
    )

    return Response(status_code=200)


async def _process_and_reply(raw_phone: str, message_id: int, query: str) -> None:
    """Run the RAG pipeline and send the answer back to the citizen.

    The ``raw_phone`` parameter is held ONLY in this function's closure.
    It is never written to the database, logs are masked, and it is
    garbage-collected when this coroutine completes.
    """
    answer = None
    try:
        # TODO: replace this with the refactored pipeline once
        # orchestrate.py exists.  For now, import the existing one.
        from src.ingestion.pipeline import get_response

        answer = get_response(query)
        reply = answer["text"]
        citation = answer.get("citation", "N/A")

        if citation and citation != "N/A":
            reply += f"\n\n📄 Chanzo: {citation}"

    except Exception:
        logger.exception("Pipeline failed for query: %s", query[:100])
        reply = "Samahani, sina jibu la uhakika kwa swali hili sasa hivi."

    # Store the assistant's answer.
    with get_session() as session:
        assistant_msg = Message(
            session_id=_get_session_for_message(session, message_id),
            role="assistant",
            text=reply,
            citation=answer.get("citation") if answer else None,
        )
        session.add(assistant_msg)

    await send_whatsapp(phone=raw_phone, message=reply)


def _get_session_for_message(session, message_id: int) -> int:
    """Return the session_id for a given message."""
    msg = session.query(Message).filter_by(id=message_id).first()
    return msg.session_id if msg else None
