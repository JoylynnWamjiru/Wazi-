"""No-Postgres retrieval from ``data/chunks.json`` for the citizen app.

The pgvector path (``retrieve.py``) needs a running PostgreSQL, which the
Streamlit Community Cloud demo does not have. This module provides a drop-in
replacement that:

  1. loads the gitignored ``data/chunks.json`` (regenerating it from the
     committed PDFs via ``build_corpus()`` if missing),
  2. embeds every chunk once with the same fastembed model (module singleton),
  3. answers a query with in-memory cosine similarity.

Vectors from ``embed_texts`` are L2-normalised, so cosine similarity is a plain
dot product. Results are shaped exactly like ``retrieve.retrieve()`` — same
keys (``chunk_id``, ``source_id``, ``page_number``, ``chunk_text``,
``government_arm``, ``similarity``) — so ``generate()`` and ``parse_response()``
consume them unchanged. Here ``source_id`` is the source *filename* (readable
in the citation, e.g. "source nakuru_birr_q1.pdf, page 2") rather than a DB id.

Selected via ``config.RETRIEVAL_BACKEND`` (``local``, or ``auto`` fallback).
"""

import json
from pathlib import Path

import numpy as np

from src.ingestion.embed import embed_texts

REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_JSON = REPO_ROOT / "data" / "chunks.json"

# Module-level singletons — the corpus and its embedding matrix are loaded and
# embedded once per process, then reused across every query.
_chunks: list[dict] | None = None
_matrix: np.ndarray | None = None


def _load() -> tuple[list[dict], np.ndarray]:
    """Load chunks.json (building it if absent) and embed every chunk once."""
    global _chunks, _matrix
    if _chunks is None or _matrix is None:
        if not CHUNKS_JSON.exists():
            # Regenerate deterministically from the committed PDFs. Imported
            # lazily to avoid a circular import (pipeline imports orchestrate).
            from src.ingestion.pipeline import build_corpus
            build_corpus()

        _chunks = json.loads(CHUNKS_JSON.read_text(encoding="utf-8"))
        texts = [c["text"] for c in _chunks]
        _matrix = (
            embed_texts(texts)
            if texts
            else np.zeros((0, 384), dtype="float32")
        )
    return _chunks, _matrix


def reset_cache() -> None:
    """Drop the cached corpus + matrix (tests / after a re-ingestion)."""
    global _chunks, _matrix
    _chunks = None
    _matrix = None


def retrieve(query: str, k: int = 8) -> list[dict]:
    """Return the top-``k`` chunks for ``query`` via in-memory cosine search.

    Shaped identically to ``retrieve.retrieve()`` so downstream generation is
    backend-agnostic.
    """
    chunks, matrix = _load()
    if not chunks:
        return []

    query_vec = embed_texts([query])[0]
    scores = matrix @ query_vec  # both L2-normalised -> dot product == cosine

    k = min(k, len(chunks))
    # argsort ascending, take the last k, reverse for descending score order.
    top_idx = np.argsort(scores)[-k:][::-1]

    results = []
    for i in top_idx:
        i = int(i)
        chunk = chunks[i]
        results.append({
            "chunk_id": chunk.get("chunk_id"),
            "source_id": chunk.get("source"),  # filename -> readable citation
            "page_number": chunk.get("page"),
            "chunk_text": chunk.get("text"),
            "government_arm": None,  # not tracked in the local corpus
            "similarity": round(float(scores[i]), 4),
        })
    return results
