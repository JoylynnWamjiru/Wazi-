"""Citizen-facing refusal and fallback messages, by language register.

These are the single source of truth for the "I don't have the answer" and
"system error" replies.  Two consumers:

- The LLM system prompt in ``src/ingestion/generate.py`` (which detects the
  register itself and picks the right string).
- The deterministic paths here — ``no_answer()`` / ``system_error()`` — used
  when there are no retrieved chunks or the pipeline raises.

``_register()`` mirrors the 1-hit query gate in ``src/ingestion/translate.py``
rather than the 2-hit reply detector in ``src.shared.language``, because
queries are terse ("pesa ngapi" is one Swahili marker but still Swahili).
Sheng is not reliably distinguishable from formal Swahili by a cheap
heuristic, so Sheng speakers receive the Swahili text (which they understand);
the LLM prompt handles the Sheng register itself.
"""

import re

from src.shared.language import SWAHILI_MARKERS

# 2-letter Swahili function words that collide with English abbreviations
# ("na" = NA, "wa" = WA, "ni" = NI) — excluded so an English "NA" isn't
# misread as Swahili.  Kept in sync with src/ingestion/translate.py.
_AMBIGUOUS_SHORT_TOKENS = frozenset({"na", "wa", "ni"})

# "The answer isn't in the documents yet" — friendly, expectation-setting.
NO_ANSWER = {
    "en": (
        "I'm sorry, I don't have the answer to this yet. My knowledge is "
        "currently limited to a few official county reports, but we are "
        "working on adding more documents soon!"
    ),
    "sw": (
        "Samahani, sina jibu la swali hili kwa sasa. Taarifa nilizonazo "
        "zinatokana na ripoti chache rasmi za kaunti, lakini tunazidi "
        "kuongeza nyaraka zaidi hivi karibuni!"
    ),
    "sheng": (
        "Pole, sina ansa ya hii swali kwa sasa. Info niko nayo inatoka kwa "
        "ma-ripoti official chache za kaunti, but tunazidi kuongeza ma-docs "
        "mob hivi karibuni!"
    ),
}

# "The system hit an error" — used when the pipeline crashes.
SYSTEM_ERROR = {
    "en": "Sorry, I'm having a little trouble right now. Please try again later!",
    "sw": "Samahani, mtandao wangu una shida kidogo kwa sasa. Tafadhali jaribu tena baadaye!",
    "sheng": "Pole, kuna ka-shida kidogo kwa system sasa hivi. Jaribu tena baadaye.",
}


def _register(query: str) -> str:
    """Return ``"sw"`` if the query looks Swahili/Sheng, else ``"en"``."""
    words = re.findall(r"[a-z]+", query.lower())
    if any(w in SWAHILI_MARKERS and w not in _AMBIGUOUS_SHORT_TOKENS for w in words):
        return "sw"
    return "en"


def no_answer(query: str) -> str:
    """Friendly "not in my documents yet" refusal in the query's register."""
    return NO_ANSWER[_register(query)]


def system_error(query: str) -> str:
    """Friendly "try again later" message in the query's register."""
    return SYSTEM_ERROR[_register(query)]
