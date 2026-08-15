"""WhatsApp messaging — provider-agnostic outbound layer.

Supports two providers, selected by ``MESSAGING_PROVIDER``:

- ``africastalking`` (default) — Africa's Talking WhatsApp API
- ``twilio`` — Twilio WhatsApp (sandbox or production number)

Provides a single ``send_whatsapp()`` function that the webhook handler
and the dispute correction flow both use to send outbound messages.
When the selected provider is not configured, messages are logged to
stdout instead of being sent — this allows development and testing
without a live WhatsApp number.

Usage:
    from src.api.messaging import send_whatsapp

    result = await send_whatsapp(
        phone="+254711XXXYYY",
        message="Mradi wa Keringet uligharimu Kshs 16,999,852...",
    )
"""

import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MESSAGING_PROVIDER = os.getenv("MESSAGING_PROVIDER", "africastalking").lower()

# --- Africa's Talking ---
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

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # e.g. whatsapp:+14155238886
# Twilio signs the webhook URL it posts to. Behind Nginx/proxies the URL the
# app reconstructs may differ from what Twilio signed, so allow an explicit
# override of the exact public URL Twilio delivers to (scheme + host + path).
TWILIO_WEBHOOK_BASE_URL = os.getenv("TWILIO_WEBHOOK_BASE_URL")
# Dev/test escape hatch: skip signature validation entirely.
TWILIO_SKIP_SIGNATURE_VALIDATION = (
    os.getenv("TWILIO_SKIP_SIGNATURE_VALIDATION", "").strip().lower()
    in {"1", "true", "yes", "on"}
)


def _twilio_wa(phone: str) -> str:
    """Return ``phone`` in Twilio's ``whatsapp:+E164`` form."""
    phone = (phone or "").strip()
    if not phone:
        return phone
    if phone.startswith("whatsapp:"):
        return phone
    if not phone.startswith("+"):
        phone = "+" + phone
    return f"whatsapp:{phone}"


def validate_twilio_signature(url: str, params: dict, signature: str | None) -> bool:
    """Verify a Twilio webhook request using the Twilio SDK.

    Returns True when the signature is valid, or when validation is
    explicitly disabled / not configured (dev mode).  Returns False for a
    missing or mismatched signature so the caller can reject the request.

    The SDK handles the tricky parts (parameter ordering, whitespace) that
    break hand-rolled validators.
    """
    if TWILIO_SKIP_SIGNATURE_VALIDATION:
        return True
    if not TWILIO_AUTH_TOKEN:
        logger.warning(
            "Twilio signature validation skipped — TWILIO_AUTH_TOKEN not set"
        )
        return True
    if not signature:
        return False

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        return validator.validate(url, dict(params), signature)
    except Exception:  # noqa: BLE001 - never fail open on a validation error
        logger.exception("Twilio signature validation raised")
        return False


async def _send_africastalking(phone: str, message: str) -> dict:
    """Send via Africa's Talking (original AT implementation)."""
    if not AT_API_KEY:
        logger.info(
            "DEV MODE (africastalking) — message to %s: %s", phone[-4:], message[:80]
        )
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


async def _send_twilio(phone: str, message: str) -> dict:
    """Send via Twilio using the Twilio SDK."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        logger.info("DEV MODE (twilio) — message to %s: %s", phone[-4:], message[:80])
        return {"status": "logged", "message": message}

    if not TWILIO_WHATSAPP_NUMBER:
        return {"status": "error", "error": "TWILIO_WHATSAPP_NUMBER not configured"}

    def _create() -> str:
        from twilio.rest import Client

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        sent = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=_twilio_wa(phone),
            body=message,
        )
        return sent.sid

    try:
        sid = await asyncio.to_thread(_create)
        return {"status": "sent", "message_id": sid}
    except Exception as exc:  # noqa: BLE001 - surface any SDK error to the caller
        logger.error("Twilio send failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def send_whatsapp(phone: str, message: str) -> dict:
    """Send a WhatsApp message to a citizen via the configured provider.

    In development (selected provider not configured), messages are logged
    to the console instead of being sent.  This allows full end-to-end
    testing without a provisioned WhatsApp number.

    Args:
        phone: The citizen's phone number in E.164 form (``+2547...``) —
               only held in transient memory, never stored or logged by
               the caller.  Each provider formats it as needed.
        message: The text to send (should be <1000 chars for WhatsApp).

    Returns:
        A dict with ``status`` and either ``message_id`` (on success) or
        ``error`` (on failure).

        ``{"status": "sent", "message_id": "..."}``
        ``{"status": "logged", "message": "<the text>"}``  (dev mode)
        ``{"status": "error", "error": "..."}``
    """
    if MESSAGING_PROVIDER == "twilio":
        return await _send_twilio(phone, message)
    return await _send_africastalking(phone, message)
