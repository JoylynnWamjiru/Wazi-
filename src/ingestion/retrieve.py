"""pgvector-backed semantic retrieval.

Replaces the old FAISS IndexFlatIP with PostgreSQL pgvector cosine
similarity search.  Uses the same multilingual MiniLM embedding model
loaded by ``embed.py``.

Supports optional filtering by ``government_arm`` for disambiguation
(e.g. Assembly vs. Executive audit reports).
"""

from sqlalchemy import func, text

from src.ingestion.embed import embed_texts
from src.shared.database import get_session
from src.shared.models import Chunk, GovernmentArm


def retrieve(
    query: str,
    k: int = 4,
    government_arm: GovernmentArm | None = None,
) -> list[dict]:
    """Embed ``query`` and return the top-``k`` matching chunks from pgvector.

    Each result is a dict with ``source_id``, ``page_number``, ``chunk_text``,
    ``government_arm``, and ``similarity`` (1 - cosine distance, higher = better).

    Args:
        query: Citizen's question in Swahili, Sheng, or English.
        k: Number of chunks to retrieve (default 4).
        government_arm: If set, filter chunks by government arm.
    """
    query_vec = embed_texts([query])[0].tolist()

    with get_session() as session:
        # L2-normalised vectors: cosine similarity = 1 - L2 distance.
        # pgvector <=> operator computes cosine distance.
        conditions = []
        params: dict = {"embedding": query_vec, "k": min(k, 50)}

        if government_arm is not None:
            conditions.append("c.government_arm = :arm")
            params["arm"] = government_arm.value

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        sql = text(f"""
            SELECT
                c.id as chunk_id,
                c.source_id,
                c.page_number,
                c.chunk_text,
                c.government_arm,
                1 - (c.embedding <=> :embedding) AS similarity
            FROM chunks c
            WHERE {where_clause}
            ORDER BY c.embedding <=> :embedding
            LIMIT :k
        """)

        rows = session.execute(sql, params).fetchall()

        return [
            {
                "chunk_id": row.chunk_id,
                "source_id": row.source_id,
                "page_number": row.page_number,
                "chunk_text": row.chunk_text,
                "government_arm": row.government_arm,
                "similarity": round(float(row.similarity), 4),
            }
            for row in rows
        ]
