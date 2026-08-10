"""Pipeline orchestration — ties retrieval + generation.

``get_response()`` is the main entry point.  It replaces the old
``pipeline.py`` ``get_response()`` with a clean separation: retrieve
chunks from pgvector, generate an answer via DeepSeek, and parse the
response into the standard ``{text, citation, last_updated}`` shape.

The old regex-based value-for-money check is replaced by a lightweight
LLM call in ``vfm.py``.
"""

from src.ingestion.retrieve import retrieve
from src.ingestion.generate import generate, parse_response
from src.ingestion.vfm import check_value_for_money
from src.shared import config


def get_response(query: str) -> dict:
    """Answer a citizen question, grounded in pgvector chunks.

    Returns:
        ``{"text": ..., "citation": ..., "last_updated": ...}``

    Any failure falls back to ``config.FALLBACK_ANSWERS`` rather than
    raising — the citizen always gets a response, even if it's "I don't know."
    """
    try:
        # LLM-driven VFM check takes precedence over general RAG.
        vfm = check_value_for_money(query)
        if vfm is not None:
            return vfm

        # k=8: the pending-bills answer lives in a chunk that ranks ~#8;
        # at k=4 it was a false negative. Verified on the old pipeline.
        chunks = retrieve(query, k=8)
        raw = generate(chunks, query)
        return parse_response(raw, chunks)

    except Exception as exc:  # noqa: BLE001
        print(f"[get_response] falling back: {type(exc).__name__}: {exc}")
        return dict(config.FALLBACK_ANSWERS["default"])


# Backward-compat alias so Streamlit and webhook can import from here.
get_response_from_query = get_response
