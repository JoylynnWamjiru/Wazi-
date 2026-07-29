"""Identity middleware — hashes WhatsApp IDs on receipt.

Every incoming WhatsApp message carries a raw wa_id (the citizen's phone
number).  This module hashes it with HMAC-SHA256 using a secret salt before
it ever touches a database, log, or response.  The raw wa_id exists ONLY in
the transient memory of the webhook handler and is garbage-collected after
the request.

HMAC-SHA256 is used instead of plain SHA-256 concatenation because plain
concatenation is vulnerable to length-extension attacks (an attacker who
knows H(wa_id + salt) for one wa_id can compute H(wa_id + salt + padding + X)
without knowing the salt).  HMAC is immune to this class of attack.

Usage:
    from src.api.middleware.identity import hash_wa_id

    user_id = hash_wa_id(raw_wa_id)
    # user_id is a 64-char hex string — never reversible without the salt
"""

import hashlib
import hmac
import os

from dotenv import load_dotenv

load_dotenv()

_SALT = os.getenv("ID_SALT", "dev-salt-change-in-production").encode()

if _SALT == b"dev-salt-change-in-production":
    import warnings
    warnings.warn(
        "ID_SALT is set to the default dev value. "
        "Generate a real salt for production with: "
        "python -c \"import secrets; print(secrets.token_hex(32))\"",
        RuntimeWarning,
    )


def hash_wa_id(wa_id: str) -> str:
    """Hash a raw WhatsApp ID with HMAC-SHA256 using the secret salt.

    Returns a 64-character hex digest.  The raw wa_id is NEVER stored,
    logged, or returned — only the hash is persisted.

    Uses HMAC-SHA256 (not plain SHA-256 concatenation) to prevent
    length-extension attacks.

    Args:
        wa_id: The raw WhatsApp ID from Africa's Talking
            (e.g. \"+254711XXXYYY\").

    Returns:
        A 64-character hex digest:
        ``hmac.new(salt, wa_id.encode(), hashlib.sha256).hexdigest()``
    """
    return hmac.new(_SALT, wa_id.encode(), hashlib.sha256).hexdigest()
