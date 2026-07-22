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

# --- Africa's Talking ---
AT_API_KEY = os.getenv("AT_API_KEY")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
WA_BOT_NUMBER = os.getenv("WA_BOT_NUMBER")

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
        "text": "Samahani, sina jibu la uhakika kwa swali hili sasa hivi.",
        "citation": "N/A",
        "last_updated": "N/A",
    }
}
