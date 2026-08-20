"""Backend selection for the citizen pipeline (issue #27, item 3).

Verifies ``orchestrate._retrieve`` honours ``config.RETRIEVAL_BACKEND`` and that
``auto`` falls back to the local corpus when pgvector raises (no PostgreSQL).
The retrieval functions are stubbed, so no DB / model is touched.
"""

import pytest

from src.ingestion import orchestrate
from src.shared import config


@pytest.fixture
def stub_backends(monkeypatch):
    monkeypatch.setattr(orchestrate, "retrieve_pgvector", lambda q, k: [{"via": "pgvector"}])
    monkeypatch.setattr(orchestrate.retrieve_local, "retrieve", lambda q, k: [{"via": "local"}])


def test_local_backend_uses_local(monkeypatch, stub_backends):
    monkeypatch.setattr(config, "RETRIEVAL_BACKEND", "local")
    assert orchestrate._retrieve("q", 8)[0]["via"] == "local"


def test_pgvector_backend_uses_pgvector(monkeypatch, stub_backends):
    monkeypatch.setattr(config, "RETRIEVAL_BACKEND", "pgvector")
    assert orchestrate._retrieve("q", 8)[0]["via"] == "pgvector"


def test_auto_prefers_pgvector_when_available(monkeypatch, stub_backends):
    monkeypatch.setattr(config, "RETRIEVAL_BACKEND", "auto")
    assert orchestrate._retrieve("q", 8)[0]["via"] == "pgvector"


def test_auto_falls_back_to_local_when_pgvector_raises(monkeypatch, stub_backends):
    monkeypatch.setattr(config, "RETRIEVAL_BACKEND", "auto")

    def boom(q, k):
        raise RuntimeError("could not connect to server")

    monkeypatch.setattr(orchestrate, "retrieve_pgvector", boom)
    assert orchestrate._retrieve("q", 8)[0]["via"] == "local"


# --- multi-turn: follow-up anchoring -----------------------------------------

def test_compose_anchors_terse_followup_to_prior_user_turn():
    history = [
        {"role": "user", "text": "What about Njoro hospital?"},
        {"role": "assistant", "text": "Ujenzi ulisimama."},
    ]
    out = orchestrate._compose_retrieval_query("how much did it cost?", history)
    assert out == "What about Njoro hospital? how much did it cost?"


def test_compose_leaves_long_self_contained_query_untouched():
    history = [{"role": "user", "text": "What about Njoro hospital?"}]
    q = "How much did the Njoro hospital project cost in total?"
    assert orchestrate._compose_retrieval_query(q, history) == q


def test_compose_returns_query_when_no_history():
    assert orchestrate._compose_retrieval_query("how much?", None) == "how much?"


def test_compose_returns_query_when_no_prior_user_turn():
    history = [{"role": "assistant", "text": "Jibu"}]
    assert orchestrate._compose_retrieval_query("how much?", history) == "how much?"


# --- clarification gate ------------------------------------------------------

def test_retrieval_is_weak_empty_and_low_and_high():
    assert orchestrate._retrieval_is_weak([]) is True
    assert orchestrate._retrieval_is_weak([{"similarity": 0.1}]) is True
    assert orchestrate._retrieval_is_weak([{"similarity": 0.6}]) is False


def test_retrieval_is_weak_lexical_only_hit_is_not_weak():
    # A lexical (full-text) match carries similarity 0.0 but a real
    # lexical_rank — exact proper nouns must not be misread as weak.
    chunks = [{"chunk_id": 1, "similarity": 0.0, "lexical_rank": 0.5}]
    assert orchestrate._retrieval_is_weak(chunks) is False


def test_get_response_asks_clarification_when_retrieval_weak(monkeypatch):
    weak = [{"chunk_id": 1, "similarity": 0.1, "page_number": 1, "chunk_text": "x"}]
    monkeypatch.setattr(orchestrate, "check_value_for_money", lambda q: None)
    monkeypatch.setattr(orchestrate, "translate_query", lambda q: q)
    monkeypatch.setattr(orchestrate, "_retrieve", lambda q, k: weak)
    monkeypatch.setattr(
        orchestrate, "maybe_clarify", lambda q, c, h: "Which project do you mean?"
    )
    generated = []
    monkeypatch.setattr(
        orchestrate, "generate", lambda c, q, history=None: generated.append(q) or "x"
    )
    res = orchestrate.get_response("mradi wa njoro")
    assert res["text"] == "Which project do you mean?"
    assert res["chunks"] == []
    assert generated == []


def test_get_response_does_not_clarify_when_retrieval_strong(monkeypatch):
    strong = [{"chunk_id": 1, "similarity": 0.6, "page_number": 1, "chunk_text": "x"}]
    monkeypatch.setattr(orchestrate, "check_value_for_money", lambda q: None)
    monkeypatch.setattr(orchestrate, "translate_query", lambda q: q)
    monkeypatch.setattr(orchestrate, "_retrieve", lambda q, k: strong)
    clarified = []
    monkeypatch.setattr(
        orchestrate, "maybe_clarify", lambda q, c, h: clarified.append(q) or "x"
    )
    monkeypatch.setattr(
        orchestrate, "generate", lambda c, q, history=None: "ANSWER. USED_CHUNK: 1"
    )
    monkeypatch.setattr(
        orchestrate, "parse_response",
        lambda raw, c: {"text": raw, "citation": "N/A"},
    )
    res = orchestrate.get_response("how much did the njoro hospital cost?")
    assert res["text"] == "ANSWER. USED_CHUNK: 1"
    assert clarified == []


def test_get_response_skips_clarify_for_long_specific_query(monkeypatch):
    # A long query that misses is "not in corpus", not "vague" — no clarify.
    weak = [{"chunk_id": 1, "similarity": 0.1, "page_number": 1, "chunk_text": "x"}]
    monkeypatch.setattr(orchestrate, "check_value_for_money", lambda q: None)
    monkeypatch.setattr(orchestrate, "translate_query", lambda q: q)
    monkeypatch.setattr(orchestrate, "_retrieve", lambda q, k: weak)
    clarified = []
    monkeypatch.setattr(
        orchestrate, "maybe_clarify", lambda q, c, h: clarified.append(q) or "x"
    )
    monkeypatch.setattr(
        orchestrate, "generate",
        lambda c, q, history=None: "USED_CHUNK: none\nno answer",
    )
    monkeypatch.setattr(
        orchestrate, "parse_response",
        lambda raw, c: {"text": raw, "citation": "N/A"},
    )
    q = "what is the weather forecast for marsabit county next week please"
    orchestrate.get_response(q)
    assert clarified == []
