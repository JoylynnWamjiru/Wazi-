"""Embed chunks and provide FAISS-backed semantic retrieval.

Loads ``data/chunks.json``, embeds each chunk with fastembed (ONNX runtime —
no torch needed) using the multilingual MiniLM model, and builds an in-memory
FAISS index. Model and index are built lazily and cached in module globals, so
``retrieve()`` never rebuilds on a per-call basis and Streamlit can start
without racing heavy ML imports.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import faiss
    from fastembed import TextEmbedding

REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_PATH = REPO_ROOT / "data" / "chunks.json"
# Multilingual model so Swahili/Sheng queries align with the English source
# text (cross-lingual retrieval). Same model/vectors as the previous
# sentence-transformers setup, served via ONNX (~5x smaller footprint).
EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Lazily-loaded embedding model and FAISS index.
_model: "TextEmbedding | None" = None
_INDEX: "faiss.Index | None" = None
_CHUNKS: list[dict] | None = None


def _get_model() -> "TextEmbedding":
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=EMBED_MODEL_NAME)
    return _model


def _embed(texts: list[str]) -> "any":
    """Embed texts to L2-normalized float32 vectors (rows)."""
    import numpy as np

    model = _get_model()
    vectors = np.array(list(model.embed(texts)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)  # unit vectors -> IP == cosine


def build_index() -> tuple["faiss.Index", list[dict]]:
    """Load chunks, embed them, and build a cosine-similarity FAISS index.

    Returns the FAISS index and a parallel list of the original chunk dicts,
    where list position N corresponds to index vector N (so a search hit maps
    straight back to its source/page/text).
    """
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    embeddings = _embed([c["text"] for c in chunks])

    import faiss

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index, chunks


def _get_index() -> tuple["faiss.Index", list[dict]]:
    global _INDEX, _CHUNKS
    if _INDEX is None or _CHUNKS is None:
        _INDEX, _CHUNKS = build_index()
    return _INDEX, _CHUNKS


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Embed ``query`` and return the top-``k`` matching chunks.

    Each result is a dict with ``source``, ``page``, ``text`` (plus a ``score``
    for eyeballing relevance during development).
    """
    index, chunks = _get_index()
    q_emb = _embed([query])

    k = min(k, len(chunks))
    scores, indices = index.search(q_emb, k)

    results: list[dict] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:  # FAISS pads with -1 when fewer than k hits exist
            continue
        chunk = chunks[idx]
        results.append({
            "source": chunk["source"],
            "page": chunk["page"],
            "text": chunk["text"],
            "score": float(score),
        })
    return results
