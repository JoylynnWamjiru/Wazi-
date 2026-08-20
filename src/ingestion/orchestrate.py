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
from src.ingestion.translate import translate_query
from src.ingestion.vfm import check_value_for_money
from src.shared import config
from src.shared.messages import system_error

# A follow-up with at most this many words is treated as a continuation of
# the prior turn and anchored to it for retrieval ("how much did it cost?").
_FOLLOWUP_MAX_WORDS = 5


def _compose_retrieval_query(query: str, history: list[dict] | None) -> str:
    """Anchor a terse follow-up to the most recent user turn for retrieval.

    A follow-up like "how much did it cost?" is unretrievable on its own; the
    prior turn supplies the entity ("what about Njoro hospital?").  Long,
    self-contained questions are left untouched so a topic switch doesn't
    inherit stale terms.
    """
    if not history or len(query.split()) > _FOLLOWUP_MAX_WORDS:
        return query
    prior_user = [m["text"] for m in history if m.get("role") == "user"]
    if not prior_user:
        return query
    return f"{prior_user[-1]} {query}".strip()


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


def get_response(query: str, history: list[dict] | None = None) -> dict:
    """Answer a citizen question, grounded in pgvector chunks.

    ``history`` is the recent conversation (``{"role", "text"}`` pairs) that
    precedes ``query``, oldest first.  It is used two ways: a terse follow-up
    is anchored to the prior user turn for retrieval, and the full history is
    passed to the generator so the answer stays in context.

    Returns:
        ``{"text": ..., "citation": ..., "last_updated": ...}``

    Any failure falls back to a friendly, register-matched message rather than
    raising — the citizen always gets a response.
    """
    try:
        # LLM-driven VFM check takes precedence over general RAG.
        vfm = check_value_for_money(query)
        if vfm is not None:
            return vfm

        # Anchor terse follow-ups to the prior turn, then translate Swahili/
        # Sheng to English for retrieval.  The corpus is 100% English, so the
        # retrieval string should be too.  The ORIGINAL query (plus history)
        # is passed to generate() so the answer matches the citizen's register.
        retrieval_query = translate_query(_compose_retrieval_query(query, history))

        # k=8: the pending-bills answer lives in a chunk that ranks ~#8;
        # at k=4 it was a false negative. Verified on the old pipeline.
        chunks = _retrieve(retrieval_query, k=8)
        raw = generate(chunks, query, history=history)
        return parse_response(raw, chunks)

    except Exception as exc:  # noqa: BLE001
        print(f"[get_response] falling back: {type(exc).__name__}: {exc}")
        return {
            "text": system_error(query),
            "citation": "N/A",
            "last_updated": "N/A",
            "chunks": [],
        }


# Backward-compat alias so Streamlit and webhook can import from here.
get_response_from_query = get_response
