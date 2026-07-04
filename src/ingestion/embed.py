"""Embed chunks and provide FAISS-backed semantic retrieval.

Loads ``data/chunks.json``, embeds each chunk with sentence-transformers
(all-MiniLM-L6-v2), and builds an in-memory FAISS index. The index and its
parallel chunk list are built once at import time and cached in module globals,
so ``retrieve()`` never rebuilds on a per-call basis.
"""

import json
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_PATH = REPO_ROOT / "data" / "chunks.json"
# Multilingual model so Swahili/Sheng queries align with the English source
# text (cross-lingual retrieval). Same 384-dim output as all-MiniLM-L6-v2.
EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Lazily-loaded embedding model (shared by indexing and querying).
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def build_index() -> tuple["faiss.Index", list[dict]]:
    """Load chunks, embed them, and build a cosine-similarity FAISS index.

    Returns the FAISS index and a parallel list of the original chunk dicts,
    where list position N corresponds to index vector N (so a search hit maps
    straight back to its source/page/text).
    """
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    model = _get_model()

    embeddings = model.encode(
        [c["text"] for c in chunks],
        convert_to_numpy=True,
        normalize_embeddings=True,  # unit vectors -> inner product == cosine
        show_progress_bar=False,
    ).astype("float32")

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index, chunks


# Build once at module load and cache in memory.
_INDEX, _CHUNKS = build_index()


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Embed ``query`` and return the top-``k`` matching chunks.

    Each result is a dict with ``source``, ``page``, ``text`` (plus a ``score``
    for eyeballing relevance during development).
    """
    model = _get_model()
    q_emb = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    k = min(k, len(_CHUNKS))
    scores, indices = _INDEX.search(q_emb, k)

    results: list[dict] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:  # FAISS pads with -1 when fewer than k hits exist
            continue
        chunk = _CHUNKS[idx]
        results.append({
            "source": chunk["source"],
            "page": chunk["page"],
            "text": chunk["text"],
            "score": float(score),
        })
    return results
