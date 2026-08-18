"""Tests for Sheng query normalization. Pure functions — no DB, no network."""

import pytest

from src.ingestion.normalize import expand_sheng, normalize_query, translate_to_english


# --- expand_sheng -----------------------------------------------------------

def test_formal_swahili_is_unchanged():
    q = "Serikali ya Kaunti ya Nakuru imetumia pesa ngapi kwa mradi wa maji?"
    assert expand_sheng(q) == q


def test_english_without_slang_is_unchanged():
    q = "How much did the government allocate for the water project?"
    assert expand_sheng(q) == q


def test_common_sheng_money_and_gov_terms_expand():
    assert expand_sheng("Gava imetumia doo ngapi?") == "serikali imetumia pesa ngapi?"


def test_project_slang_expands():
    assert expand_sheng("hii prao ya barabra imegharimu ngapi") == \
        "hii mradi ya barabara imegharimu ngapi"


def test_expansion_is_case_insensitive():
    assert expand_sheng("GAVA na Doo") == "serikali na pesa"


def test_substring_is_not_replaced():
    # "doondoo" contains "doo" but not as a whole word — must stay intact.
    assert expand_sheng("doondoo") == "doondoo"


def test_multiple_terms_in_one_query():
    out = expand_sheng("gava ilitumia ganji kwa proja")
    assert out == "serikali ilitumia pesa kwa mradi"


# --- translate_to_english ---------------------------------------------------

def test_swahili_content_words_translate_to_english():
    assert translate_to_english("hospitali ya Njoro ilikuwa pesa ngapi?") == \
        "hospital Njoro money cost how much?"


def test_english_is_unchanged_by_translation():
    q = "How much did the hospital cost?"
    assert translate_to_english(q) == q


# --- normalize_query --------------------------------------------------------

def test_english_query_returns_single_variant():
    q = "How much did the Njoro hospital cost?"
    assert normalize_query(q) == [q]


def test_formal_swahili_query_gets_english_variant():
    q = "Kaunti ilipokea kiasi gani?"
    variants = normalize_query(q)
    assert variants[0] == q                       # original preserved first
    assert variants[-1] == "county ilipokea amount which?"
    assert len(variants) == 2


def test_sheng_query_returns_original_plus_expanded_plus_english():
    q = "Gava ilitumia doo ngapi?"
    variants = normalize_query(q)
    assert variants[0] == q                       # original Sheng first
    assert variants[1] == "serikali ilitumia pesa ngapi?"  # Sheng -> Swahili
    assert variants[2] == "government ilitumia money cost how much?"  # -> English
    assert len(variants) == 3


def test_variants_never_empty():
    assert normalize_query("") == [""]
