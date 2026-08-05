"""Embed chunks and store them in pgvector.

Uses fastembed (ONNX runtime) with the multilingual MiniLM model for
cross-lingual retrieval.  Chunks are stored in PostgreSQL via pgvector
instead of the old in-memory FAISS index.

The embedding model is a module-level singleton — loaded once, reused
across requests.  ``_get_model()`` and ``embed_texts()`` are consumed by
``retrieve.py`` for query embedding and scrapers for bulk chunk storage.
"""

import numpy as np
from sqlalchemy import func

from src.shared.database import get_session
from src.shared.models import Chunk, GovernmentArm

# Multilingual model so Swahili/Sheng queries align with English source text
# (cross-lingual retrieval).  ONNX runtime — no torch needed.
EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model = None


def _get_model():
    """Lazy-load the embedding model once."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=EMBED_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts to L2-normalized float32 vectors.

    Returns a (N, 384) numpy array of unit vectors — inner product == cosine.
    """
    model = _get_model()
    vectors = np.array(list(model.embed(texts)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


def store_chunks(
    chunks: list[dict],
    source_id: int,
    government_arm: GovernmentArm,
    county: str,
) -> int:
    """Embed and store chunks in pgvector.  Returns count of stored chunks.

    Args:
        chunks: List of dicts from ``chunk_pages()`` —
                ``{chunk_id, source, page, text}``.
        source_id: FK to the ``sources`` table.
        government_arm: Denormalised for filtered retrieval.
        county: Denormalised for filtered retrieval.
    """
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts)

    with get_session() as session:
        for i, chunk in enumerate(chunks):
            row = Chunk(
                source_id=source_id,
                government_arm=government_arm,
                county=county,
                chunk_text=chunk["text"],
                embedding=embeddings[i].tolist(),
                page_number=chunk["page"],
                chunk_index=i,
            )
            session.add(row)

        session.flush()

    return len(chunks)


def chunk_count(source_id: int) -> int:
    """Return the number of chunks for a given source."""
    with get_session() as session:
        return (
            session.query(func.count(Chunk.id))
            .filter(Chunk.source_id == source_id)
            .scalar()
        ) or 0


def delete_chunks(source_id: int) -> int:
    """Delete all chunks for a source.  Returns number of deleted rows."""
    with get_session() as session:
        deleted = (
            session.query(Chunk)
            .filter(Chunk.source_id == source_id)
            .delete()
        )
        session.flush()
    return deleted
