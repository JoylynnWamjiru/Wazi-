"""LLM generation via DeepSeek API.

Takes retrieved chunks and a citizen query, formats a grounded prompt,
and returns the AI's answer.  Extracted from the old ``pipeline.py`` god
module so it can be tested and swapped independently.
"""

import re

import httpx

from src.shared import config

SYSTEM_PROMPT = """You are Wazi, a civic assistant that helps Kenyan citizens \
understand their county government's fiscal documents (audit reports and budget \
implementation reports).

Follow these rules strictly:

1. GROUNDING: Answer ONLY using the numbered CONTEXT chunks provided by the user. \
Do not use any outside knowledge. Every figure you state must appear verbatim in \
the context — never invent, estimate, or round a number.

2. NO ANSWER: If the context does not actually contain the answer to the \
question, reply with exactly this phrase: "sina taarifa za kutosha" (I don't have \
enough information). Do not guess.

3. LANGUAGE REGISTER: Detect the register of the citizen's question and reply in \
the SAME register:
   - Formal Swahili  -> reply in formal Swahili
   - Sheng (Kenyan street slang) -> reply in Sheng
   - English -> reply in English

4. STYLE: Keep the answer short and clear, suitable for reading on WhatsApp.

5. CITATION: Always end your reply with a citation line on its own line that \
names the source document and page, for example:
   Chanzo: nakuru_birr_q1.pdf, ukurasa 2

6. SOURCE MARKER: After the citation line, add one final line in this exact \
machine-readable format naming which numbered CONTEXT chunk your answer is \
based on:
   USED_CHUNK: <number>
Use the bracketed number of the chunk you actually drew the answer from. If you \
did not have enough information to answer, write `USED_CHUNK: none`."""

# Matches the marker the model appends: "USED_CHUNK: 2".
_USED_CHUNK_RE = re.compile(
    r"^\s*USED_CHUNK:\s*(\d+|none)\s*$", re.IGNORECASE | re.MULTILINE
)

# Matches the model's own citation line so we strip it before display.
_CITATION_LINE_RE = re.compile(
    r"^\s*(chanzo|source|rejea)\s*:.*$", re.IGNORECASE | re.MULTILINE
)


def generate(chunks: list[dict], query: str) -> str:
    """Generate a grounded answer from the retrieved chunks.

    Args:
        chunks: Retrieved chunks from ``retrieve.py``, each with keys
                ``source_id``, ``page_number``, ``chunk_text``.
        query: The citizen's original question.

    Returns:
        The raw LLM response (includes USED_CHUNK marker and citation line).
    """
    if not chunks:
        return "USED_CHUNK: none\nsina taarifa za kutosha"

    context = "\n\n".join(
        f"[{i + 1}] Source chunk (page {c['page_number']}):\n{c['chunk_text']}"
        for i, c in enumerate(chunks)
    )
    user_content = f"CONTEXT:\n{context}\n\nQUESTION: {query}"

    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    response = httpx.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        json={
            "model": config.DEEPSEEK_MODEL,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def parse_response(raw: str, chunks: list[dict]) -> dict:
    """Parse the LLM response into a clean answer + citation.

    Returns a dict matching the ``PipelineResponse`` contract:
    ``{"text": ..., "citation": ..., "last_updated": ...}``
    """
    # The model names the chunk it used via "USED_CHUNK: N".
    match = _USED_CHUNK_RE.search(raw)
    text = _USED_CHUNK_RE.sub("", raw)
    text = _CITATION_LINE_RE.sub("", text).strip()

    citation = "N/A"
    if match and match.group(1).lower() != "none":
        idx = int(match.group(1)) - 1  # 1-indexed -> 0-indexed
        if 0 <= idx < len(chunks):
            used = chunks[idx]
            citation = f"source {used['source_id']}, page {used['page_number']}"
    elif match is None and chunks:
        top = chunks[0]
        citation = f"source {top['source_id']}, page {top['page_number']}"

    return {"text": text, "citation": citation, "last_updated": "N/A"}
