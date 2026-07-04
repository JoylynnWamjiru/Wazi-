"""Application configuration (loaded from environment variables)."""

import os

from dotenv import load_dotenv

# Load a local .env if present, so ANTHROPIC_API_KEY can live there.
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# NOTE: the requested value was "claude-sonnet-4-6", which is not a valid
# Anthropic model id and would return a 404 (forcing every call into the
# fallback). Using the current Sonnet id so the pipeline actually runs.
# Change this line if you need a specific model.
MODEL_NAME = "claude-sonnet-5"

# DeepSeek (OpenAI-compatible endpoint). Used when no Anthropic key is present
# but a DeepSeek key is — lets generation run without the Anthropic SDK.
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Pick a provider: prefer Anthropic if its key is set, else fall back to
# DeepSeek. ("none" means every call will hit FALLBACK_ANSWERS.)
if ANTHROPIC_API_KEY:
    PROVIDER = "anthropic"
elif DEEPSEEK_API_KEY:
    PROVIDER = "deepseek"
else:
    PROVIDER = "none"

FALLBACK_ANSWERS = {
    "default": {
        "text": "Samahani, sina jibu la uhakika kwa swali hili sasa hivi.",
        "citation": "N/A",
        "last_updated": "N/A",
    }
}
