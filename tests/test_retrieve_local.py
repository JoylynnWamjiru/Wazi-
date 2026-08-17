"""Unit tests for the no-Postgres local retrieval path (issue #27, item 3).

The embedding model is stubbed with deterministic one-hot vectors so these run
with no PostgreSQL, no network, and no 127 MB model download — they exercise the
loading / ranking / result-shape logic, not fastembed itself.
"""

import json

import numpy as np
import pytest

from src.ingestion import retrieve_local


def _fake_embed(texts):
    """Map a text whose last token is an int N to the unit basis vector e_N.

    Already L2-normalised, so dot product == cosine and a query "topic 1"
    scores 1.0 against the chunk "... 1" and 0.0 against the others.
    """
    vecs = []
    for t in texts:
        n = int(t.split()[-1])
        v = np.zeros(384, dtype="float32")
        v[n] = 1.0
        vecs.append(v)
    return np.array(vecs, dtype="float32")


@pytest.fixture
def local_corpus(tmp_path, monkeypatch):
    """Point retrieve_local at a tiny temp chunks.json with a stubbed embedder."""
    chunks = [
        {"chunk_id": "c0", "source": "a.pdf", "page": 2, "text": "topic 0"},
        {"chunk_id": "c1", "source": "b.pdf", "page": 5, "text": "topic 1"},
        {"chunk_id": "c2", "source": "c.pdf", "page": 9, "text": "topic 2"},
    ]
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps(chunks), encoding="utf-8")

    monkeypatch.setattr(retrieve_local, "CHUNKS_JSON", path)
    monkeypatch.setattr(retrieve_local, "embed_texts", _fake_embed)
    retrieve_local.reset_cache()
    yield chunks
    retrieve_local.reset_cache()


def test_ranks_the_matching_chunk_first(local_corpus):
    results = retrieve_local.retrieve("topic 1", k=3)
    assert results[0]["source_id"] == "b.pdf"
    assert results[0]["page_number"] == 5
    assert results[0]["similarity"] == pytest.approx(1.0)


def test_result_shape_matches_pgvector_contract(local_corpus):
    top = retrieve_local.retrieve("topic 0", k=1)[0]
    assert set(top) == {
        "chunk_id", "source_id", "source_title", "page_number",
        "chunk_text", "government_arm", "similarity",
    }
    assert top["chunk_id"] == "c0"
    assert top["chunk_text"] == "topic 0"
    assert top["government_arm"] is None
    assert isinstance(top["similarity"], float)


def test_k_caps_the_number_of_results(local_corpus):
    assert len(retrieve_local.retrieve("topic 2", k=2)) == 2
    # k larger than the corpus returns everything, not an error.
    assert len(retrieve_local.retrieve("topic 2", k=99)) == 3


def test_empty_corpus_returns_empty(tmp_path, monkeypatch):
    path = tmp_path / "chunks.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(retrieve_local, "CHUNKS_JSON", path)
    monkeypatch.setattr(retrieve_local, "embed_texts", _fake_embed)
    retrieve_local.reset_cache()
    try:
        assert retrieve_local.retrieve("topic 0", k=5) == []
    finally:
        retrieve_local.reset_cache()
