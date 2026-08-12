"""Tests for Sheng query normalization. Pure functions — no DB, no network."""

import pytest

from src.ingestion.normalize import expand_sheng, normalize_query


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


# --- normalize_query --------------------------------------------------------

def test_non_sheng_query_returns_single_variant():
    q = "Kaunti ilipokea kiasi gani?"
    assert normalize_query(q) == [q]


def test_sheng_query_returns_original_plus_expanded():
    q = "Gava ilitumia doo ngapi?"
    variants = normalize_query(q)
    assert variants[0] == q                       # original preserved first
    assert variants[1] == "serikali ilitumia pesa ngapi?"
    assert len(variants) == 2


def test_variants_never_empty():
    assert normalize_query("") == [""]
