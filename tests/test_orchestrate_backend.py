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
