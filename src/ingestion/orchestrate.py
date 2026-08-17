"""Pipeline orchestration — ties retrieval + generation.

``get_response()`` is the main entry point.  It replaces the old
``pipeline.py`` ``get_response()`` with a clean separation: retrieve
chunks from pgvector, generate an answer via DeepSeek, and parse the
response into the standard ``{text, citation, last_updated}`` shape.

The old regex-based value-for-money check is replaced by a lightweight
LLM call in ``vfm.py``.
"""

from src.ingestion import retrieve_local
from src.ingestion.retrieve import retrieve as retrieve_pgvector
from src.ingestion.generate import generate, parse_response
from src.ingestion.vfm import check_value_for_money
from src.shared import config


def _retrieve(query: str, k: int) -> list[dict]:
    """Retrieve chunks using the configured backend (``config.RETRIEVAL_BACKEND``).

    - ``pgvector`` : PostgreSQL/pgvector only (production / VPS).
    - ``local``    : in-memory chunks.json only (no DB, e.g. Streamlit Cloud).
    - ``auto``     : try pgvector, fall back to local when the DB is unreachable.
    """
    backend = config.RETRIEVAL_BACKEND
    if backend == "local":
        return retrieve_local.retrieve(query, k=k)
    if backend == "pgvector":
        return retrieve_pgvector(query, k=k)

    # auto: prefer pgvector, fall back to the local corpus if it's unavailable
    # (e.g. no PostgreSQL on Streamlit Community Cloud).
    try:
        return retrieve_pgvector(query, k=k)
    except Exception as exc:  # noqa: BLE001 - any DB/driver failure -> local
        print(
            f"[retrieve] pgvector unavailable ({type(exc).__name__}), "
            "falling back to local chunks.json"
        )
        return retrieve_local.retrieve(query, k=k)


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
        chunks = _retrieve(query, k=8)
        raw = generate(chunks, query)
        return parse_response(raw, chunks)

    except Exception as exc:  # noqa: BLE001
        print(f"[get_response] falling back: {type(exc).__name__}: {exc}")
        fallback = dict(config.FALLBACK_ANSWERS["default"])
        fallback["chunks"] = []
        return fallback


# Backward-compat alias so Streamlit and webhook can import from here.
get_response_from_query = get_response
