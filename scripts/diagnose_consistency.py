"""Standalone diagnostic for Wazi pipeline output consistency.

Does NOT modify any production code. It calls the real production generation
functions (``generate.generate`` / ``generate.parse_response``) and mirrors the
real ``orchestrate.get_response`` + ``vfm.check_value_for_money`` control flow.

Retrieval caveat (transparent): pgvector/psycopg2 is not available on this dev
machine, so both the RAG path and the VFM path are run through the LOCAL
``chunks.json`` retrieval (``src.ingestion.retrieve_local``) instead of
pgvector. The embedding model and corpus are identical to what pgvector would
hold, so retrieval evidence is representative and generation evidence is exact.

Usage (from repo root):
    $env:PYTHONPATH="."; venv/Scripts/python.exe scripts/diagnose_consistency.py
"""

import os

# The DB is never queried here (retrieval is local chunks.json; generation is
# DeepSeek over HTTP), but importing src.shared.database builds a SQLAlchemy
# engine at module load. Point it at SQLite BEFORE any src import so it doesn't
# require psycopg2 (not installed on this dev machine). Mirrors conftest.py.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_diag_tmp.db")

import re

import httpx

from src.ingestion import retrieve_local
from src.ingestion.generate import generate, parse_response
from src.ingestion.vfm import _VFM_SYSTEM_PROMPT, _VFM_TRIGGERS
from src.shared import config

# --- Test questions ----------------------------------------------------------
# 3 golden regression questions + 3 "inconsistent output" candidates.
QUESTIONS = [
    {
        "label": "GOLDEN 1 — revenue share (formal Swahili)",
        "q": "Serikali ya Kaunti ya Nakuru inatarajia kupokea kiasi gani kutoka "
             "kwa Serikali ya Kitaifa kama mgao wa mapato?",
        "expected_src": "birr", "expected_page": 2, "expected_text": None,
    },
    {
        "label": "GOLDEN 2 — deposits & retentions (English)",
        "q": "What did the Auditor-General find about deposits and retentions "
             "not disclosed in the statement of cash flows?",
        "expected_src": "audit", "expected_page": 4, "expected_text": "104,985,718",
    },
    {
        "label": "GOLDEN 3 — value-for-money (Keringet, VFM trigger)",
        "q": "Je, mradi wa Keringet ulikuwa na thamani ya pesa iliyotumika?",
        "expected_src": "audit", "expected_page": 15, "expected_text": "16,999,852",
    },
    {
        "label": "FLAKY 1 — pending bills (English, borderline retrieval)",
        "q": "What did the Auditor-General find about pending bills?",
        "expected_src": None, "expected_page": None, "expected_text": "pending bill",
    },
    {
        "label": "FLAKY 2 — revenue share (casual Sheng)",
        "q": "Nakuru inapata pesa ngapi kutoka serikali kuu?",
        "expected_src": "birr", "expected_page": 2, "expected_text": None,
    },
    {
        "label": "FLAKY 3 — development spending (coverage probe)",
        "q": "How did Nakuru County spend its development budget?",
        "expected_src": None, "expected_page": None, "expected_text": None,
    },
]


# --- Faithful local replicas (retrieval swapped to chunks.json) --------------

def local_vfm(query: str) -> dict | None:
    """Mirror of vfm.check_value_for_money, using local retrieval.

    Kept prod-faithful: NO temperature override (so it reflects the VFM path's
    real, still-default decoding — the point is to observe it, not fix it).
    """
    if not any(t in query.lower() for t in _VFM_TRIGGERS):
        return None
    if not config.DEEPSEEK_API_KEY:
        return None
    try:
        chunks = retrieve_local.retrieve(query, k=3)
        if not chunks:
            return None
        context = "\n\n".join(f"[{i + 1}] {c['chunk_text']}" for i, c in enumerate(chunks))
        response = httpx.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={
                "model": config.DEEPSEEK_MODEL,
                "max_tokens": 512,
                "messages": [
                    {"role": "system", "content": _VFM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"{context}\n\n{query}"},
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        return parse_response(raw, chunks)
    except Exception as exc:  # noqa: BLE001
        print(f"   [local_vfm error: {type(exc).__name__}: {exc}]")
        return None


def local_get_response(query: str) -> dict:
    """Faithful replica of orchestrate.get_response with local retrieval."""
    try:
        vfm = local_vfm(query)
        if vfm is not None:
            return vfm
        chunks = retrieve_local.retrieve(query, k=8)
        raw = generate(chunks, query)  # real production generation (now temp=0)
        return parse_response(raw, chunks)
    except Exception as exc:  # noqa: BLE001
        print(f"   [local_get_response fallback: {type(exc).__name__}: {exc}]")
        return dict(config.FALLBACK_ANSWERS["default"])


# --- Consistency comparison --------------------------------------------------

def extract_figures(text: str) -> set:
    """Pull monetary-looking figures from an answer, normalised for comparison.

    Keeps numbers that carry a comma, a decimal, a magnitude word, or >=5
    digits — filters out page numbers and 4-digit fiscal years.
    """
    out = set()
    for num, mag in re.findall(
        r"(\d[\d,]*(?:\.\d+)?)\s*(bilioni|billion|milioni|million)?", text, re.I
    ):
        norm = num.replace(",", "")
        if mag or "." in num or "," in num or len(norm) >= 5:
            out.add((norm, mag.lower()))
    return out


def compare(r1: dict, r2: dict) -> tuple[bool, str]:
    fig1, fig2 = extract_figures(r1["text"]), extract_figures(r2["text"])
    cit1, cit2 = r1["citation"], r2["citation"]
    same = (fig1 == fig2) and (cit1 == cit2)
    if same:
        return True, ""
    diffs = []
    if cit1 != cit2:
        diffs.append(f"citation: '{cit1}' vs '{cit2}'")
    if fig1 != fig2:
        diffs.append(f"figures: {sorted(fig1)} vs {sorted(fig2)}")
    return False, "; ".join(diffs)


def chunk_has_expected(chunks: list[dict], item: dict) -> bool | None:
    src, page, text = item["expected_src"], item["expected_page"], item["expected_text"]
    if not src and not text:
        return None  # coverage probe — nothing specific expected
    for c in chunks:
        csrc = (c.get("source_id") or "").lower()
        if src and page is not None and src in csrc and c.get("page_number") == page:
            return True
        if text and text.lower() in (c.get("chunk_text") or "").lower():
            return True
    return False


# --- Driver ------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("WAZI PIPELINE CONSISTENCY DIAGNOSTIC")
    print("temperature=0 (generate.py) · retrieval=local chunks.json "
          "(pgvector unavailable here)")
    print("=" * 78)

    summary = []
    for item in QUESTIONS:
        print("\n" + "#" * 78)
        print(item["label"])
        print("#" * 78)
        print(f"QUESTION: {item['q']}\n")

        # (b) retrieval only
        chunks = retrieve_local.retrieve(item["q"], k=8)
        print(f"RETRIEVED {len(chunks)} chunks (k=8):")
        for i, c in enumerate(chunks, 1):
            snippet = (c.get("chunk_text") or "").replace("\n", " ")[:200]
            print(f"  [{i}] src={c.get('source_id')}  p{c.get('page_number')}  "
                  f"id={c.get('chunk_id')}  sim={c.get('similarity')}")
            print(f"       {snippet}")
        has_expected = chunk_has_expected(chunks, item)
        print(f"\nCorrect chunk in retrieved set: "
              f"{'YES' if has_expected else 'NO' if has_expected is False else 'N/A (coverage probe)'}")

        # (c) two runs
        print("\n--- RUN 1 ---")
        r1 = local_get_response(item["q"])
        print(f"{r1['text']}\n[citation: {r1['citation']}]")
        print("\n--- RUN 2 ---")
        r2 = local_get_response(item["q"])
        print(f"{r2['text']}\n[citation: {r2['citation']}]")

        # (d) verdict
        same, note = compare(r1, r2)
        verdict = "CONSISTENT" if same else "INCONSISTENT"
        print(f"\n>>> {verdict}" + (f" — {note}" if note else ""))
        summary.append((item["label"], verdict, has_expected))

    # summary table
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'Question':<52} {'Consistency':<13} {'Correct chunk?'}")
    print("-" * 78)
    for label, verdict, has_expected in summary:
        chunk = "YES" if has_expected else "NO" if has_expected is False else "N/A"
        print(f"{label[:51]:<52} {verdict:<13} {chunk}")


if __name__ == "__main__":
    main()
