"""Sheng-aware query normalization for cross-lingual retrieval.

The multilingual MiniLM embedder handles formal Swahili and English well but
is weak on **Sheng** (Kenyan urban slang): words like ``doo`` (money) or
``gava`` (government) don't embed near the formal English/Swahili terms in the
corpus, so the right chunk is never retrieved.

This module bridges that gap *before* embedding — no model retraining (which
is off the table on the dev machine and deferred anyway). Two mechanisms:

1. ``expand_sheng`` — a deterministic lexicon that rewrites common Sheng terms
   to their standard-Swahili equivalents. Zero cost, no network.
2. ``llm_normalize`` — an optional DeepSeek rewrite for coverage beyond the
   lexicon. NOT wired into the hot retrieval path by default (adds latency);
   available for offline expansion or a future toggle.

``normalize_query`` returns the query variants to embed. When the query
contains no mapped term the expansion is a no-op, so it returns just the
original and the working path is unaffected. Only a query containing a mapped
term gains a second, normalized variant. Most mapped terms are Sheng slang;
one English civic term is included (``county`` -> ``kaunti``), so an English
query that uses it is normalized too — helpful, since it aligns with the
corpus, but it means "English is untouched" is not literally true.

The lexicon is a starter set. Grow it with native-speaker input via the
linguist-validation loop (`/api/validation/*`).
"""

import re

# Sheng term -> standard Swahili equivalent. Focused on civic / budget
# vocabulary, since that is what citizens ask Wazi about. Keys are matched
# case-insensitively on word boundaries.
SHENG_LEXICON: dict[str, str] = {
    # money (kept to unambiguous Sheng terms; dropped "mabao"/"dough"/"mullah"
    # which collide with planks/literal-dough/the religious title)
    "doo": "pesa",
    "ganji": "pesa",
    "chapaa": "pesa",
    "mkwanja": "pesa",
    "munde": "pesa",
    # government
    "gava": "serikali",
    "gavaa": "serikali",
    # projects / work
    "prao": "mradi",
    "proja": "mradi",
    "job": "kazi",
    # places / services  (NB: "sato" deliberately excluded — it means tilapia,
    # and would wreck a fisheries-budget query)
    "hosi": "hospitali",
    "barabra": "barabara",
    "rodi": "barabara",
    # question / quantity
    "aje": "vipi",
    "mangapi": "ngapi",
    # English-in-Sheng civic term
    "county": "kaunti",
}

# Precompiled, word-boundary, case-insensitive pattern over all lexicon keys.
# Longer keys first so an entry never loses to a shorter one that is its prefix.
_KEYS_SORTED = sorted(SHENG_LEXICON, key=len, reverse=True)
_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _KEYS_SORTED) + r")\b",
    re.IGNORECASE,
)

# Swahili -> English, for cross-lingual retrieval. The corpus is English and
# the multilingual embedder's Swahili<->English alignment is too weak for many
# civic terms ("hospitali" vs "hospital", "pesa" vs "money"), so we translate
# the content words deterministically and retrieve with the English variant too.
SWAHILI_TO_ENGLISH: dict[str, str] = {
    # question words / common verbs
    "nini": "what",
    "nani": "who",
    "wapi": "where",
    "lini": "when",
    "gani": "which",
    "ngapi": "how much",
    "kulipwa": "paid",
    "gharimu": "cost",
    "uligharimu": "cost",
    "iligharimu": "cost",
    # Swahili function words — dropped (no English content value)
    "hiyo": "",
    "hii": "",
    "ya": "",
    "za": "",
    "kwa": "",
    "ilikuwa": "",
    # civic / budget nouns
    "hospitali": "hospital",
    "pesa": "money cost",
    "gharama": "cost",
    "bei": "price",
    "mradi": "project",
    "miradi": "projects",
    "kaunti": "county",
    "barabara": "road",
    "shule": "school",
    "maji": "water",
    "umeme": "electricity",
    "mkataba": "contract",
    "mwaka": "year",
    "miaka": "years",
    "serikali": "government",
    "kiasi": "amount",
    "malipo": "payments",
    "bajeti": "budget",
    "makadirio": "estimates",
    "matumizi": "expenditure",
    "mapato": "revenue",
    "madeni": "debts",
    "kazi": "work",
    "ujenzi": "construction",
    "afya": "health",
    "elimu": "education",
    "huduma": "services",
    "ripoti": "report",
    "ukaguzi": "audit",
}

_EN_KEYS_SORTED = sorted(SWAHILI_TO_ENGLISH, key=len, reverse=True)
_EN_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _EN_KEYS_SORTED) + r")\b",
    re.IGNORECASE,
)


def translate_to_english(query: str) -> str:
    """Rewrite Swahili content words to English (word-level, case-insensitive).

    Words not in the lexicon are untouched; Swahili function words are dropped.
    An English query comes back unchanged.
    """
    def _sub(match: re.Match) -> str:
        return SWAHILI_TO_ENGLISH[match.group(0).lower()]

    translated = _EN_PATTERN.sub(_sub, query)
    return re.sub(r"\s+", " ", translated).strip()


def expand_sheng(query: str) -> str:
    """Rewrite known Sheng terms in ``query`` to standard Swahili.

    Word-boundary, case-insensitive. Words not in the lexicon are untouched,
    so a formal-Swahili or English query comes back unchanged.
    """
    def _sub(match: re.Match) -> str:
        return SHENG_LEXICON[match.group(0).lower()]

    return _PATTERN.sub(_sub, query)


def normalize_query(query: str) -> list[str]:
    """Return the query variants to embed for retrieval.

    Always includes the original. Adds the Sheng->Swahili expansion when the
    query contains a mapped term, and the Swahili->English translation when it
    contains Swahili content words — so a Swahili query can match the English
    corpus. A query with no mapped terms returns a single variant.
    """
    variants = [query]
    expanded = expand_sheng(query)
    if expanded != query:
        variants.append(expanded)
    english = translate_to_english(expanded)
    if english and english not in variants:
        variants.append(english)
    return variants


def llm_normalize(query: str) -> str | None:
    """Rewrite a Sheng query into formal Swahili via DeepSeek (optional).

    Returns ``None`` if no API key is configured or the call fails. NOT used
    in the default retrieval path — kept for offline corpus-gap analysis or a
    future opt-in toggle, so a network hiccup never breaks live retrieval.
    """
    from src.shared import config

    if not getattr(config, "DEEPSEEK_API_KEY", None):
        return None

    try:
        import httpx

        response = httpx.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={
                "model": config.DEEPSEEK_MODEL,
                "max_tokens": 128,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Rewrite the user's Kenyan Sheng question into clear "
                            "formal Swahili with the same meaning. Output ONLY the "
                            "rewritten question, nothing else."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
