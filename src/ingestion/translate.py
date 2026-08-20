"""LLM query translation for cross-lingual retrieval.

The corpus is 100% formal English (OAG audit reports, CoB BIRRs, KIPPRA
CBROP / Programme-Budget), and the multilingual MiniLM embedder's
Swahili<->English alignment is too weak for many civic terms.  The static
``normalize.py`` lexicon bridges the common cases, but it cannot cover every
Swahili/Sheng term or verb form — and a missed translation means a missed
chunk, which means "sina taarifa".

``translate_query()`` therefore does the translation with DeepSeek on the hot
path: better retrieval is worth an extra ~1-2s of latency, because a wrong
retrieval ruins the whole RAG answer regardless of how fast it returns.

Design constraints:

- Lives HERE, not in ``normalize_query`` (which stays pure and synchronous so
  the test suite runs with no network) and not in ``retrieve()`` (which stays
  a "dumb" text-in -> vectors-out DB utility — ``vfm.py`` also calls
  ``retrieve()`` and must not trigger a hidden translation).
- English queries return unchanged (no LLM call) — gated by ``detect_language``.
- Any failure (no API key, network, timeout, junk output) falls back to the
  deterministic lexicon, then to the original query — never empty, never a
  raised exception.
- Results are cached in a small in-memory LRU so repeated questions don't
  re-spend a translation call.
"""

import re
from collections import OrderedDict

import httpx

from src.shared import config
from src.shared.language import SWAHILI_MARKERS, detect_language
from src.ingestion.normalize import SHENG_LEXICON, expand_sheng, translate_to_english

# Strict single-purpose translation + query-expansion prompt.  The output is
# embedded directly, so conversational filler ("Sure! Here is the
# translation:") would poison the vector.  temperature=0 keeps it
# deterministic.
_TRANSLATION_SYSTEM_PROMPT = """You are an expert Kenyan linguist and public \
finance translator. The user will give you a citizen query in Swahili, Sheng, \
or a mix of languages. Translate it into formal English public finance \
terminology for use as a database search query.

RULES:
1. Output ONLY the English translation. No quotes, no explanations, no \
conversational filler such as "Here is the translation:".
2. Expand street slang and informal terms into official audit/budget terms.
   - "pesa" -> "expenditure, budget, or allocation"
   - "imekwama" -> "stalled, delayed, or terminated project"
   - "kujenga" -> "construction or infrastructure"
3. Keep proper nouns, numbers, and currency figures exactly as written \
(e.g. "Njoro", "Kshs. 148,902,024").
4. If the query is already in English, output the original query unchanged.
"""

# Common conversational prefixes the model sometimes emits despite the rules.
_FILLER_RE = re.compile(
    r"^(sure|here is the translation|the translation|translation|in english)"
    r"\s*[:：\-]\s*",
    re.IGNORECASE,
)

# In-memory LRU for translated queries (bounded, so it can't grow unbounded on
# a long-running VPS process).
_cache: OrderedDict[str, str] = OrderedDict()
_CACHE_MAX = 256

# Sheng terms that signal a non-English query.  "county" is excluded: it is an
# English word the lexicon maps to Swahili for a different reason, and must not
# cause an English query to trigger a translation round-trip.
_SLANG_SIGNAL = re.compile(
    r"\b(" + "|".join(
        re.escape(k)
        for k in sorted((k for k in SHENG_LEXICON if k != "county"), key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)

# Single-token Swahili markers that collide with common English abbreviations
# ("na" = NA, "wa" = WA, "ni" = NI).  The query gate below uses a 1-hit
# threshold, so these are excluded to avoid misclassifying an English query —
# a real Swahili query virtually always carries another marker beyond these
# function words.
_AMBIGUOUS_SHORT_TOKENS = frozenset({"na", "wa", "ni"})


def needs_translation(query: str) -> bool:
    """Inverted query gate: assume translation is needed unless clearly English.

    ``detect_language`` is tuned for *replies* (verbose paragraphs), where a
    2-hit threshold survives abbreviations like "NA".  Queries are a different
    shape: terse and often mixed-language, so a 2-hit gate would silently
    bypass the LLM for "pesa ngapi" or "cost of that barabara" — exactly the
    queries that most need query expansion.  A single Swahili/Sheng token is
    therefore enough to trigger translation.
    """
    words = re.findall(r"[a-z]+", query.lower())
    if any(w in SWAHILI_MARKERS and w not in _AMBIGUOUS_SHORT_TOKENS for w in words):
        return True
    return bool(_SLANG_SIGNAL.search(query))


def _cache_key(query: str) -> str:
    """Collapse case/whitespace so "Pesa?" and "pesa ?" share a translation."""
    return " ".join(query.lower().split())


def reset_cache() -> None:
    """Drop cached translations (tests, or after a lexicon update)."""
    _cache.clear()


def _llm_translate(query: str) -> str:
    """Call DeepSeek to translate ``query`` to English.  Raises on failure."""
    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    response = httpx.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        json={
            "model": config.DEEPSEEK_MODEL,
            "max_tokens": 128,
            # Deterministic decoding — a translation should be stable, and a
            # high temperature invites filler and dropped proper nouns.
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _TRANSLATION_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        },
        # Short timeout: a slow translation should fail fast and fall back to
        # the lexicon rather than stall the citizen's answer.
        timeout=15.0,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"].strip()
    text = text.strip('"\'`')
    text = _FILLER_RE.sub("", text).strip()
    return text


def _lexicon_translate(query: str) -> str:
    """Deterministic fallback: Sheng -> Swahili -> English, or the original."""
    english = translate_to_english(expand_sheng(query))
    return english or query


def translate_query(query: str) -> str:
    """Return an English retrieval query for ``query``.

    - Empty / English queries: returned unchanged (no LLM call).
    - Swahili / Sheng queries: DeepSeek translation; falls back to the
      deterministic lexicon when translation is disabled or fails.
    """
    if not query or not query.strip():
        return query

    mode = config.QUERY_TRANSLATION
    if mode == "off":
        return _lexicon_translate(query)

    # English queries pass through untouched; anything Swahili/Sheng gets
    # translated.  The gate is inverted (1-hit) because queries are terse —
    # see needs_translation().  Short Swahili that slips through still gets
    # deterministic treatment inside retrieve() as a safety net.
    if not needs_translation(query):
        return query

    key = _cache_key(query)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    translated = ""
    if mode == "auto" and config.DEEPSEEK_API_KEY:
        try:
            translated = _llm_translate(query)
        except Exception as exc:  # noqa: BLE001 - network/timeout/format
            print(
                f"[translate] LLM translation failed ({type(exc).__name__}), "
                f"falling back to lexicon: {query[:80]}"
            )

    # Validate: the model must return new, English-looking content.  If it
    # echoed the Swahili back or produced nothing useful, use the lexicon.
    if not translated or translated == query or detect_language(translated) == "sw":
        translated = _lexicon_translate(query)

    _cache[key] = translated
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)  # evict the least-recently used entry
    return translated
