"""pgvector-backed semantic retrieval.

Replaces the old FAISS IndexFlatIP with PostgreSQL pgvector cosine
similarity search.  Uses the same multilingual MiniLM embedding model
loaded by ``embed.py``.

Supports optional filtering by ``government_arm`` for disambiguation
(e.g. Assembly vs. Executive audit reports).
"""

from sqlalchemy import func, text

from src.ingestion.embed import embed_texts
from src.ingestion.normalize import normalize_query
from src.shared.database import get_session
from src.shared.models import Chunk, GovernmentArm


def retrieve(
    query: str,
    k: int = 8,
    government_arm: GovernmentArm | None = None,
) -> list[dict]:
    """Embed ``query`` and return the top-``k`` matching chunks from pgvector.

    Each result is a dict with ``source_id``, ``page_number``, ``chunk_text``,
    ``government_arm``, and ``similarity`` (1 - cosine distance, higher = better).

    Args:
        query: Citizen's question in Swahili, Sheng, or English.
        k: Number of chunks to retrieve (default 8 — low enough for a tight
            DeepSeek context, high enough to catch answers that rank ~#8,
            e.g. the pending-bills figure).
        government_arm: If set, filter chunks by government arm.
    """
    # Sheng-aware multi-query retrieval: search with the original query AND any
    # lexicon-normalized variant, then merge, keeping each chunk's BEST
    # similarity across variants. For a formal-Swahili or English query there is
    # a single variant, so this is exactly one query — the working path is
    # unchanged. A Sheng query adds the normalized variant (e.g. "doo" -> "pesa")
    # WITHOUT diluting it: the normalized form's strong matches come through at
    # full strength, which averaging the two vectors would have muted.
    variants = normalize_query(query)
    vectors = embed_texts(variants)          # (N, 384), each L2-normalised

    with get_session() as session:
        # L2-normalised vectors: cosine similarity = 1 - L2 distance.
        # pgvector <=> operator computes cosine distance.
        conditions = []
        base_params: dict = {}

        if government_arm is not None:
            conditions.append("c.government_arm = :arm")
            base_params["arm"] = government_arm.value

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        limit = min(k, 50)

        sql = text(f"""
            SELECT
                c.id as chunk_id,
                c.source_id,
                s.title AS source_title,
                c.page_number,
                c.chunk_text,
                c.government_arm,
                1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
            WHERE {where_clause}
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :k
        """)

        # Merge results across variants, keeping each chunk's best similarity.
        best: dict = {}
        for vec in vectors:
            params = {**base_params, "embedding": vec.tolist(), "k": limit}
            for row in session.execute(sql, params).fetchall():
                sim = round(float(row.similarity), 4)
                existing = best.get(row.chunk_id)
                if existing is None or sim > existing["similarity"]:
                    best[row.chunk_id] = {
                        "chunk_id": row.chunk_id,
                        "source_id": row.source_id,
                        "source_title": row.source_title,
                        "page_number": row.page_number,
                        "chunk_text": row.chunk_text,
                        "government_arm": row.government_arm,
                        "similarity": sim,
                    }

    return sorted(best.values(), key=lambda r: r["similarity"], reverse=True)[:k]
