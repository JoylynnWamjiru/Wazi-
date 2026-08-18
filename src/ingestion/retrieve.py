"""pgvector-backed semantic retrieval.

Replaces the old FAISS IndexFlatIP with PostgreSQL pgvector cosine
similarity search.  Uses the same multilingual MiniLM embedding model
loaded by ``embed.py``.

Supports optional filtering by ``government_arm`` for disambiguation
(e.g. Assembly vs. Executive audit reports).
"""

import re

from sqlalchemy import text

from src.ingestion.embed import embed_texts
from src.ingestion.normalize import normalize_query
from src.shared.database import get_session
from src.shared.models import GovernmentArm

# Common English + Swahili function words dropped from the lexical query so
# the full-text match is driven by content words and proper nouns.
_LEX_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or",
    "is", "are", "was", "were", "be", "been", "did", "does", "do", "has",
    "have", "had", "what", "which", "who", "how", "when", "where", "why",
    "much", "many", "this", "that", "these", "those", "it", "its", "about",
    "with", "from", "their", "there", "they", "you", "your", "not", "no",
    "status", "can", "could", "would", "should", "will", "all", "any",
    "na", "ya", "za", "kwa", "cha", "hiyo", "hii", "ili", "kuhusu", "ngapi",
    "nini", "gani", "je",
})


def _lexical_tsquery(query: str) -> str:
    """OR-join the query's content words into a lenient tsquery."""
    words = [
        w for w in re.findall(r"[a-z0-9]+", query.lower())
        if w not in _LEX_STOPWORDS
    ]
    return " | ".join(words)


def _fts_search(
    query: str,
    k: int,
    government_arm: GovernmentArm | None = None,
) -> list[dict]:
    """Lexical full-text search over ``chunks.fts`` for exact nouns/names.

    Vector search matches concepts but misses exact proper nouns ("Njoro",
    "Keringet"). PostgreSQL ``to_tsquery('simple', ...)`` OR-matches the
    query's content words with no stemming, so a chunk naming the entity
    surfaces even when its embedding similarity is diluted.
    """
    lexquery = _lexical_tsquery(query)
    if not lexquery:
        return []

    conditions = ["c.fts @@ to_tsquery('simple', :lexquery)"]
    params: dict = {"lexquery": lexquery, "k": k}
    if government_arm is not None:
        conditions.append("c.government_arm = :arm")
        params["arm"] = government_arm.value
    where = " AND ".join(conditions)

    sql = text(f"""
        SELECT
            c.id as chunk_id,
            c.source_id,
            s.title AS source_title,
            c.page_number,
            c.chunk_text,
            c.government_arm,
            ts_rank(c.fts, to_tsquery('simple', :lexquery)) AS lexical_rank
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE {where}
        ORDER BY lexical_rank DESC
        LIMIT :k
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()

    return [
        {
            "chunk_id": r.chunk_id,
            "source_id": r.source_id,
            "source_title": r.source_title,
            "page_number": r.page_number,
            "chunk_text": r.chunk_text,
            "government_arm": r.government_arm,
            "similarity": 0.0,
            "lexical_rank": round(float(r.lexical_rank), 4),
        }
        for r in rows
    ]


def _fuse(*ranked_lists: list[dict], k: int) -> list[dict]:
    """Reciprocal Rank Fusion over one or more ranked result lists.

    Each list is a separate ranker (vector, Swahili lexical, English lexical).
    A chunk found by several rankers sums its reciprocal ranks, so a chunk
    matching multiple query variants outranks one matching only one.  Chunks
    keep their original dict shape; callers never depend on ``similarity`` for
    ordering after fusion.
    """
    scores: dict = {}
    merged: dict = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            scores[chunk["chunk_id"]] = scores.get(chunk["chunk_id"], 0.0) + 1.0 / (60 + rank + 1)
            merged.setdefault(chunk["chunk_id"], chunk)
    return sorted(merged.values(), key=lambda c: scores[c["chunk_id"]], reverse=True)[:k]


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

    vector_results = sorted(best.values(), key=lambda r: r["similarity"], reverse=True)[:k]

    # Hybrid retrieval: merge semantic hits with lexical full-text hits so
    # exact nouns surface even when their embedding similarity is weak.  Run the
    # lexical search on the MOST-ENGLISH variant (normalize_query's last item:
    # the English translation for a Swahili/Sheng query, or the original for an
    # English query) so it matches English corpus words ("hospital") rather than
    # Swahili ones ("hospitali").  If the fts column isn't present, fall back
    # to vector-only.
    try:
        lexical = _fts_search(variants[-1], k, government_arm)
    except Exception as exc:  # noqa: BLE001
        print(f"[retrieve] lexical search unavailable ({type(exc).__name__}), vector-only")
        lexical = []
    return _fuse(vector_results, lexical, k=k)
