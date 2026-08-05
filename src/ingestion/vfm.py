"""LLM-driven value-for-money (VFM) comparison.

Replaces the old hardcoded regex-based VFM check with a lightweight
DeepSeek call that compares a contract sum against typical Kenyan
construction benchmarks.

The comparison is ALWAYS framed as "warrants further clarification" —
never as an accusation of wrongdoing.
"""

from src.ingestion.retrieve import retrieve
from src.shared import config

_VFM_SYSTEM_PROMPT = """You are a comparative reasoning assistant for Kenyan \
county fiscal data.  The user will give you a contract sum from an audit report \
and ask whether it represents value for money.

Your job:
1. Identify the project type from the context (e.g. classroom construction, \
road works, water project).
2. Compare the stated contract sum against typical benchmarks for that project \
type in Kenya.
3. Frame the comparison as "the stated amount is within/outside typical ranges \
and warrants further clarification" — NEVER accuse anyone of wrongdoing.
4. Reply in Swahili or Sheng if the query is in that register.
5. Format: answer on one line, then a "Chanzo:" citation line, then \
"USED_CHUNK: <number>" on the final line."""

# Trigger words that signal a value-for-money question.
_VFM_TRIGGERS = (
    "worth", "reasonable", "value for money",
    "gharama", "thamani", "bei", "reasonable",
)


def check_value_for_money(query: str) -> dict | None:
    """Check if a query is a VFM question and, if so, compare against benchmarks.

    Returns a pipeline-shaped dict, or None if the query is not a VFM question
    or the LLM call fails.
    """
    if not any(t in query.lower() for t in _VFM_TRIGGERS):
        return None

    if not config.DEEPSEEK_API_KEY:
        return None

    try:
        chunks = retrieve(query, k=3)
        if not chunks:
            return None

        context = "\n\n".join(
            f"[{i + 1}] {c['chunk_text']}" for i, c in enumerate(chunks)
        )

        import httpx
        response = httpx.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={
                "model": config.DEEPSEEK_MODEL,
                "max_tokens": 512,
                "messages": [
                    {"role": "system", "content": _VFM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"{context}\n\n{query}"},
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()

        citation = "N/A"
        if chunks:
            c = chunks[0]
            citation = f"source {c['source_id']}, page {c['page_number']}"

        return {"text": text, "citation": citation, "last_updated": "N/A"}
    except Exception:
        return None
