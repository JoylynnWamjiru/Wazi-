"""Clarifying-question generation for vague queries.  LLM call is stubbed."""

import httpx

from src.ingestion.clarify import maybe_clarify
from src.shared import config


def _fake_post(monkeypatch, content: str):
    def fake_post(url, **kwargs):
        class R:
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"message": {"content": content}}]}
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)


def test_returns_question_when_model_answers_with_question(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    _fake_post(monkeypatch, "Which project do you mean?")
    assert maybe_clarify("mradi wa njoro", [{"chunk_text": "x"}]) == "Which project do you mean?"


def test_returns_none_for_not_vague_sentinel(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    _fake_post(monkeypatch, "NOT_VAGUE")
    assert maybe_clarify("mradi wa njoro", []) is None


def test_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", None)
    assert maybe_clarify("mradi wa njoro", []) is None


def test_strips_quotes_from_model_output(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    _fake_post(monkeypatch, '"Unamaanisha mradi gani?"')
    assert maybe_clarify("mradi wa njoro", []) == "Unamaanisha mradi gani?"
