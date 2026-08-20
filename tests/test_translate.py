"""Tests for LLM query translation on the retrieval hot path.

No network: the LLM call is stubbed, or the fallback path (no API key) is
exercised directly.
"""

import pytest

from src.ingestion import translate
from src.ingestion.translate import translate_query
from src.shared import config


@pytest.fixture(autouse=True)
def clean_cache():
    translate.reset_cache()
    yield
    translate.reset_cache()


def test_empty_query_is_unchanged():
    assert translate_query("") == ""
    assert translate_query("   ") == "   "


def test_english_query_is_unchanged_and_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(translate, "_llm_translate", lambda q: calls.append(q) or "X")
    q = "How much did the Njoro hospital cost?"
    assert translate_query(q) == q
    assert calls == []


def test_english_query_with_county_word_does_not_trigger_translation(monkeypatch):
    # "county" is in the Sheng lexicon (English -> Swahili mapping), but an
    # English query using it must still pass through without an LLM call.
    calls = []
    monkeypatch.setattr(translate, "_llm_translate", lambda q: calls.append(q) or "X")
    q = "How much did Nakuru county allocate to the water project?"
    assert translate_query(q) == q
    assert calls == []


def test_swahili_query_uses_llm_translation(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        translate, "_llm_translate", lambda q: "How much did Njoro hospital cost?"
    )
    out = translate_query("Hospitali ya Njoro iligharimu pesa ngapi?")
    assert out == "How much did Njoro hospital cost?"


def test_swahili_query_falls_back_to_lexicon_when_llm_fails(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")

    def boom(q):
        raise RuntimeError("network down")

    monkeypatch.setattr(translate, "_llm_translate", boom)
    assert translate_query("hospitali ya Njoro ilikuwa pesa ngapi?") == \
        "hospital Njoro money cost how much?"


def test_swahili_query_falls_back_when_llm_echoes_swahili(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(translate, "_llm_translate", lambda q: q)  # echoed input
    assert translate_query("hospitali ya Njoro ilikuwa pesa ngapi?") == \
        "hospital Njoro money cost how much?"


def test_swahili_query_uses_lexicon_without_api_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", None)
    assert translate_query("hospitali ya Njoro ilikuwa pesa ngapi?") == \
        "hospital Njoro money cost how much?"


def test_mode_off_skips_llm_and_uses_lexicon(monkeypatch):
    monkeypatch.setattr(config, "QUERY_TRANSLATION", "off")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    calls = []
    monkeypatch.setattr(translate, "_llm_translate", lambda q: calls.append(q) or "X")
    assert translate_query("hospitali ya Njoro ilikuwa pesa ngapi?") == \
        "hospital Njoro money cost how much?"
    assert calls == []


def test_sheng_query_is_translated(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        translate, "_llm_translate", lambda q: "how much did the government spend?"
    )
    assert translate_query("Gava ilitumia doo ngapi?") == \
        "how much did the government spend?"


def test_short_swahili_query_triggers_translation(monkeypatch):
    # "pesa ngapi" has a single Swahili marker — the 2-hit reply detector would
    # call it English, but the query gate must still fire the LLM.
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(translate, "_llm_translate", lambda q: "how much money")
    assert translate_query("pesa ngapi") == "how much money"


def test_mixed_english_swahili_query_triggers_translation(monkeypatch):
    # One Swahili content word inside an otherwise-English query must trigger
    # translation, or "barabara" would never match the English "road".
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(translate, "_llm_translate", lambda q: "cost of that road")
    assert translate_query("cost of that barabara") == "cost of that road"


def test_english_na_abbreviation_does_not_trigger_translation(monkeypatch):
    # "NA" lowercases to "na", a Swahili marker — but the query gate excludes
    # ambiguous 2-letter tokens so a data abbreviation doesn't fire the LLM.
    calls = []
    monkeypatch.setattr(translate, "_llm_translate", lambda q: calls.append(q) or "X")
    q = "The value is NA for this line item"
    assert translate_query(q) == q
    assert calls == []


def test_repeated_query_is_cached(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    calls = []

    def fake(q):
        calls.append(q)
        return "money for Njoro hospital"

    monkeypatch.setattr(translate, "_llm_translate", fake)
    q = "pesa ya hospitali ya Njoro?"
    assert translate_query(q) == "money for Njoro hospital"
    assert translate_query(q) == "money for Njoro hospital"
    assert len(calls) == 1
