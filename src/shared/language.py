"""Language detection for citizen-facing replies (Swahili/Sheng vs English).

The WhatsApp reply's citation label should match the reply's language:
``Chanzo:`` for Swahili/Sheng, ``Source:`` for English.  Rather than asking
the LLM to report its own language (an extra, fragile round-trip), we
classify the answer text with a lightweight lexicon of Swahili function
words and common civic terms — words that essentially never appear as
English, so a couple of hits is a strong signal.

This is a heuristic, not a classifier: it errs toward ``"en"`` for very
short or vocabulary-poor Swahili sentences.  The failure mode is cosmetic
(the citation label word), never a wrong answer or citation.
"""

import re

# Unambiguous Swahili function words + common civic vocabulary.  Deliberately
# excludes tokens that could also be English ("do", "i", "a", ...).
_SWAHILI_MARKERS = frozenset({
    "na", "ya", "za", "wa", "ni", "kwa", "katika", "kwamba", "kuhusu",
    "ambayo", "ambao", "ambacho", "ime", "zime", "hii", "hili", "huu",
    "haya", "hizo", "hivyo", "vile", "vya", "cha", "kila", "kuwa", "kama",
    "bila", "kutoka", "hadi", "zaidi", "pia", "sasa", "tayari", "jibu",
    "swali", "asante", "tafadhali", "sana", "hakuna", "sina", "samahani",
    "taarifa", "pesa", "mradi", "miradi", "kaunti", "serikali", "ripoti",
    "ukaguzi", "msimamizi", "mapato", "matumizi", "mgao", "mwaka", "watu",
    "ujenzi", "hospitali", "barabara", "mkataba", "kazi", "elimu", "afya",
    "maji", "umeme", "uchunguzi",
})

# Number of marker hits that flips the classification to Swahili.  One hit is
# too eager ("NA" -> "na" would flip short English replies); two is a strong
# signal while still catching normal-length Swahili/Sheng sentences.
_SW_HIT_THRESHOLD = 2


def detect_language(text: str) -> str:
    """Return ``"sw"`` if *text* looks Swahili/Sheng, else ``"en"``."""
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for word in words if word in _SWAHILI_MARKERS)
    return "sw" if hits >= _SW_HIT_THRESHOLD else "en"
