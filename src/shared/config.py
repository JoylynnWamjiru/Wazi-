"""Application configuration (loaded from environment variables).

All secrets come from environment variables or a .env file.
.env is in .gitignore — never commit it.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM Provider ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- Database ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://wazi:wazi_password@localhost:5432/wazi_db",
)

# --- Retrieval backend ---
# Which retrieval path the citizen pipeline uses:
#   "pgvector" — always query PostgreSQL/pgvector (the VPS / production path)
#   "local"    — read data/chunks.json + in-memory cosine (no PostgreSQL; set
#                this on Streamlit Community Cloud, which has no database)
#   "auto"     — try pgvector, transparently fall back to local when the DB is
#                unreachable (default: resilient everywhere, slightly slower on
#                the first failed connection)
RETRIEVAL_BACKEND = os.getenv("RETRIEVAL_BACKEND", "auto").lower()

# --- Query translation ---
# How Swahili/Sheng queries are turned into English before retrieval (the
# corpus is 100% English, so the retrieval string should be too):
#   "auto"    — DeepSeek translation, falling back to the deterministic lexicon
#   "lexicon" — deterministic Sheng->Swahili->English lexicon only (no LLM)
#   "off"     — pass the query through unchanged (retrieve()'s own lexicon
#               normalization still applies)
QUERY_TRANSLATION = os.getenv("QUERY_TRANSLATION", "auto").lower()

# --- Messaging provider ---
# Which WhatsApp gateway the outbound layer uses:
#   "africastalking" — Africa's Talking (default)
#   "twilio"         — Twilio WhatsApp (sandbox or production number)
MESSAGING_PROVIDER = os.getenv("MESSAGING_PROVIDER", "africastalking").lower()

# --- Africa's Talking ---
AT_API_KEY = os.getenv("AT_API_KEY")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
WA_BOT_NUMBER = os.getenv("WA_BOT_NUMBER")

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
TWILIO_WEBHOOK_BASE_URL = os.getenv("TWILIO_WEBHOOK_BASE_URL")

# --- Identity ---
ID_SALT = os.getenv("ID_SALT", "dev-salt-change-in-production")

# --- Admin ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# --- Retention ---
CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "90"))
DISPUTE_RETENTION_DAYS = int(os.getenv("DISPUTE_RETENTION_DAYS", "365"))

# --- Fallback ---
FALLBACK_ANSWERS = {
    "default": {
        # Last-resort reply for paths with no query string available.  The
        # language-aware paths use src.shared.messages.system_error instead.
        "text": (
            "Samahani, mtandao wangu una shida kidogo kwa sasa. "
            "Tafadhali jaribu tena baadaye!\n\n"
            "Sorry, I'm having a little network trouble right now. "
            "Please try again later!"
        ),
        "citation": "N/A",
        "last_updated": "N/A",
    }
}
