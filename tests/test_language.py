"""Unit tests for reply-language detection and the source-label choice."""

import pytest

from src.shared.language import detect_language


@pytest.mark.parametrize("text", [
    "Kaunti ya Nakuru ilipokea Kshs. 4,200,000,000 kutoka Serikali Kuu.",
    "Mradi huu uligharimu Kshs. 16,999,852.",
    "Hakuna taarifa za kutosha.",
    "sina taarifa za kutosha",
    "Dooh, hii construction ya Njoro hospital ilikula how much?",
    "Asante. Jibu hili limeripotiwa na watu kadhaa.",
])
def test_detects_swahili_and_sheng(text):
    assert detect_language(text) == "sw"


@pytest.mark.parametrize("text", [
    "The project cost Kshs. 148,902,024.",
    "The contract sum is Kshs. 148,902,024 and 80 percent was paid.",
    "Nakuru County received Kshs. 4.2 billion from the National Treasury.",
])
def test_detects_english(text):
    assert detect_language(text) == "en"


def test_english_na_abbreviation_is_not_swahili():
    # "NA" -> token "na" would be a lone marker hit; the threshold must
    # not flip a short English sentence to Swahili on that single hit.
    assert detect_language("The value is NA for this line item.") == "en"


def test_source_label_matches_language():
    from src.api.webhooks import _source_label

    assert _source_label("The project cost Kshs. 148,902,024.") == "Source"
    assert _source_label("Mradi huu uligharimu Kshs. 16,999,852.") == "Chanzo"
    assert _source_label("Dooh, hii construction ya Njoro hospital ilikula how much?") == "Chanzo"
