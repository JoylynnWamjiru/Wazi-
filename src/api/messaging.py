"""WhatsApp messaging via Africa's Talking API.

Provides a single ``send_whatsapp()`` function that the webhook handler
and the dispute correction flow both use to send outbound messages.

When AT_API_KEY is not configured, messages are logged to stdout instead
of being sent — this allows development and testing without a live
WhatsApp number (which requires billing setup).

Usage:
    from src.api.messaging import send_whatsapp

    result = await send_whatsapp(
        phone="+254711XXXYYY",
        message="Mradi wa Keringet uligharimu Kshs 16,999,852...",
    )
"""

import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

AT_API_KEY = os.getenv("AT_API_KEY")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
WA_BOT_NUMBER = os.getenv("WA_BOT_NUMBER")

# Live vs sandbox — the base URL changes.
# Sandbox sends to a simulator; live sends to real phones.
# Until billing is set up, this stays on sandbox and messages are logged.
AT_BASE_URL = (
    "https://chat.sandbox.africastalking.com"
    if AT_USERNAME == "sandbox"
    else "https://chat.africastalking.com"
)


async def send_whatsapp(phone: str, message: str) -> dict:
    """Send a WhatsApp message to a citizen.

    In development (no AT_API_KEY), messages are logged to the console
    instead of being sent.  This allows full end-to-end testing without
    a provisioned WhatsApp number.

    Args:
        phone: The citizen's phone number (raw wa_id — only held in
               transient memory, never stored or logged by the caller).
        message: The text to send (should be <1000 chars for WhatsApp).

    Returns:
        A dict with ``status`` and either ``message_id`` (on success) or
        ``error`` (on failure).

        ``{"status": "sent", "message_id": "ATXid_..."}``
        ``{"status": "logged", "message": "<the text>"}``  (dev mode)
        ``{"status": "error", "error": "..."}``
    """
    if not AT_API_KEY:
        logger.info("DEV MODE — message to %s: %s", phone[-4:], message[:80])
        return {"status": "logged", "message": message}

    if not WA_BOT_NUMBER:
        return {"status": "error", "error": "WA_BOT_NUMBER not configured"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{AT_BASE_URL}/whatsapp/message/send",
                headers={
                    "apikey": AT_API_KEY,
                    "content-type": "application/json",
                },
                json={
                    "username": AT_USERNAME,
                    "waNumber": WA_BOT_NUMBER,
                    "phoneNumber": phone,
                    "body": {"message": message},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"status": "sent", "message_id": data.get("messageId")}

    except httpx.HTTPError as exc:
        logger.error("AT send failed: %s", exc)
        return {"status": "error", "error": str(exc)}
