"""Orchestrate the ingestion + retrieval + generation pipeline.

- ``build_corpus()``  : check -> extract -> chunk -> save data/chunks.json
- ``get_response()``  : retrieve grounded chunks -> ask Claude -> cited answer
"""

import json
import re
import sys
from pathlib import Path

# Repo root is three levels up from this file: src/ingestion/pipeline.py
REPO_ROOT = Path(__file__).resolve().parents[2]

# Put the REPO ROOT (not src/) on the path so the `src.*` import style below
# resolves identically whether this module is run as a script or imported by
# the Streamlit UI / FastAPI app. Every entry point must use the same style:
# mixing `ingestion.embed` with `src.ingestion.embed` makes Python create two
# distinct module objects, each loading its own copy of the ONNX embedding
# model — and the second load fails with "bad allocation", which surfaces to
# the citizen as the Swahili fallback instead of a real answer.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.extract import check_text_layer, extract_pages
from src.ingestion.chunk import chunk_pages
from src.ingestion.embed import retrieve
from src.shared import config

DATA_DIR = REPO_ROOT / "data"

PDF_FILES = [
    "nakuru_audit_report.pdf",
    "nakuru_birr_q2.pdf",
]

# --- Value-for-money comparison (one scripted, grounded example) -------------
VALUE_FOR_MONEY_BENCHMARKS = {
    "classroom_construction": {
        "typical_range_kes": (2_000_000, 4_000_000),
        "unit": "per classroom block",
        "note": "Illustrative benchmark based on publicly reported public school construction costs in Kenya; used for comparative reasoning only, not a certified cost standard."
    }
}

# Query words that signal a value-for-money question (English + Swahili).
_VFM_TRIGGERS = ("worth", "reasonable", "value for money", "gharama", "thamani")

# Distinctive phrase identifying the specific delayed/incomplete construction
# finding in the audit report. NOTE: the corpus has no primary-school classroom
# contract; this is the closest real delayed-and-incomplete building project
# with a stated contract sum (two dormitories, kitchen, dining area and a shed
# at Keringet Sports Center, page 15). Swap the marker to target a different
# project if needed.
_VFM_PROJECT_MARKER = "two dormitories, kitchen, dining area and a shed"

SYSTEM_PROMPT = """You are Wazi, a civic assistant that helps Kenyan citizens \
understand their county government's fiscal documents (audit reports and budget \
implementation reports).

Follow these rules strictly:

1. GROUNDING: Answer ONLY using the numbered CONTEXT chunks provided by the user. \
Do not use any outside knowledge. Every figure you state must appear verbatim in \
the context — never invent, estimate, or round a number.

2. NO ANSWER: If the context does not actually contain the answer to the \
question, reply with exactly this phrase: "sina taarifa za kutosha" (I don't have \
enough information). Do not guess.

3. LANGUAGE REGISTER: Detect the register of the citizen's question and reply in \
the SAME register:
   - Formal Swahili  -> reply in formal Swahili
   - Sheng (Kenyan street slang) -> reply in Sheng
   - English -> reply in English

4. STYLE: Keep the answer short and clear, suitable for reading on WhatsApp.

5. CITATION: Always end your reply with a citation line on its own line that \
names the source document and page, for example:
   Chanzo: nakuru_birr_q2.pdf, ukurasa 2

6. SOURCE MARKER: After the citation line, add one final line in this exact \
machine-readable format naming which numbered CONTEXT chunk your answer is \
based on:
   USED_CHUNK: <number>
Use the bracketed number of the chunk you actually drew the answer from. If you \
did not have enough information to answer, write `USED_CHUNK: none`."""

# Matches the machine-readable marker the model appends, e.g. "USED_CHUNK: 2".
_USED_CHUNK_RE = re.compile(r"^\s*USED_CHUNK:\s*(\d+|none)\s*$", re.IGNORECASE | re.MULTILINE)

# Matches the model's own in-register citation line (Chanzo/Source/Rejea: ...).
# The UI renders the derived citation separately, so we strip it from the text
# to avoid showing the citation twice.
_CITATION_LINE_RE = re.compile(r"^\s*(chanzo|source|rejea)\s*:.*$", re.IGNORECASE | re.MULTILINE)


def build_corpus() -> list[dict]:
    """Build the combined chunk corpus from the Nakuru county PDFs."""
    pdf_paths = [DATA_DIR / name for name in PDF_FILES]

    for path in pdf_paths:
        if not path.exists():
            raise FileNotFoundError(f"Expected PDF not found: {path}")
        if not check_text_layer(str(path)):
            raise ValueError(
                f"Text-layer check failed for '{path.name}': the PDF appears "
                f"to be scanned/image-only and would need OCR before extraction."
            )

    corpus: list[dict] = []
    for path in pdf_paths:
        pages = extract_pages(str(path))
        corpus.extend(chunk_pages(pages))

    out_path = DATA_DIR / "chunks.json"
    out_path.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return corpus


def _generate_anthropic(system_prompt: str, user_content: str) -> str:
    """Generate an answer with the Anthropic (Claude) API."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.MODEL_NAME,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(
        block.text for block in message.content
        if getattr(block, "type", None) == "text"
    ).strip()


def _generate_deepseek(system_prompt: str, user_content: str) -> str:
    """Generate an answer with DeepSeek's OpenAI-compatible chat endpoint."""
    import httpx

    response = httpx.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        json={
            "model": config.DEEPSEEK_MODEL,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def check_value_for_money(query: str) -> dict | None:
    """One scripted value-for-money comparison, grounded in a real corpus figure.

    If the query contains a value-for-money trigger word, this finds the
    delayed/incomplete construction project in the audit report, pulls its real
    contract sum and page, and compares it against the classroom_construction
    benchmark. Returns a pipeline-shaped dict, or None if not triggered (so
    normal RAG handling takes over).

    The comparison is always framed as "warrants further clarification" — never
    as an accusation of wrongdoing. This is a hard requirement.
    """
    if not any(trigger in query.lower() for trigger in _VFM_TRIGGERS):
        return None

    chunks = json.loads((DATA_DIR / "chunks.json").read_text(encoding="utf-8"))
    chunk = next(
        (c for c in chunks if _VFM_PROJECT_MARKER.lower() in c["text"].lower()),
        None,
    )
    if chunk is None:
        return None

    # Pull the contract sum that follows the project marker in the chunk (the
    # marker anchors us to this project, not another one on the same page).
    start = chunk["text"].lower().find(_VFM_PROJECT_MARKER.lower())
    match = re.search(r"contract sum of Kshs[.\s]*([0-9,]+)", chunk["text"][start:])
    if match is None:
        return None

    amount = match.group(1)  # e.g. "16,999,852"
    amount_value = int(amount.replace(",", ""))
    page = chunk["page"]

    benchmark = VALUE_FOR_MONEY_BENCHMARKS["classroom_construction"]
    low, high = benchmark["typical_range_kes"]
    within = low <= amount_value <= high
    verdict_sw = "kiko ndani ya" if within else "kimezidi"

    text = (
        f"Kulingana na ripoti ya Mkaguzi Mkuu (ukurasa {page}), mradi huu "
        f"uligharimu Kshs {amount}. Miradi ya aina hii kwa kawaida hugharimu "
        f"kati ya Kshs 2,000,000 na 4,000,000 kwa darasa moja. Kiasi hiki "
        f"{verdict_sw} wigo wa kawaida, na kinahitaji ufafanuzi zaidi."
    )

    return {
        "text": text,
        "citation": f"{chunk['source']}, page {page}",
        "last_updated": "N/A",
    }


def get_response(query: str) -> dict:
    """Answer a citizen question, grounded in the retrieved corpus chunks.

    Returns a dict matching the pipeline_interface contract:
    ``{"text": ..., "citation": ..., "last_updated": ...}``. Any failure in
    retrieval or the LLM call falls back to ``config.FALLBACK_ANSWERS`` rather
    than raising. The provider (Anthropic or DeepSeek) is chosen in config
    based on which API key is present.
    """
    try:
        # Scripted value-for-money comparison takes precedence over RAG.
        vfm = check_value_for_money(query)
        if vfm is not None:
            return vfm

        chunks = retrieve(query, k=4)
        context = "\n\n".join(
            f"[{i + 1}] Source: {c['source']}, page {c['page']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        user_content = f"CONTEXT:\n{context}\n\nQUESTION: {query}"

        if config.PROVIDER == "anthropic":
            raw = _generate_anthropic(SYSTEM_PROMPT, user_content)
        elif config.PROVIDER == "deepseek":
            raw = _generate_deepseek(SYSTEM_PROMPT, user_content)
        else:
            raise RuntimeError("No LLM API key configured (Anthropic or DeepSeek)")

        # The model names the chunk it used via a trailing "USED_CHUNK: N"
        # marker. Derive the citation from THAT chunk's metadata, then strip the
        # marker from the user-facing text.
        match = _USED_CHUNK_RE.search(raw)
        text = _USED_CHUNK_RE.sub("", raw)
        text = _CITATION_LINE_RE.sub("", text).strip()

        citation = "N/A"
        if match and match.group(1).lower() != "none":
            idx = int(match.group(1)) - 1  # marker is 1-indexed over `chunks`
            if 0 <= idx < len(chunks):
                used = chunks[idx]
                citation = f"{used['source']}, page {used['page']}"
        elif match is None and chunks:
            # Model didn't emit a usable marker: fall back to the top chunk.
            top = chunks[0]
            citation = f"{top['source']}, page {top['page']}"

        return {"text": text, "citation": citation, "last_updated": "N/A"}
    except Exception as exc:  # noqa: BLE001 - any failure -> graceful fallback
        print(f"[get_response] falling back due to: {type(exc).__name__}: {exc}")
        return dict(config.FALLBACK_ANSWERS["default"])


if __name__ == "__main__":
    # Two real, grounded questions in different registers, to eyeball whether
    # retrieval + generation actually stays anchored to the Nakuru documents.
    QUESTIONS = [
        ("Swahili / BIRR",
         "Serikali ya Kaunti ya Nakuru inatarajia kupokea kiasi gani kutoka "
         "kwa Serikali ya Kitaifa kama mgao wa mapato?"),
        ("English / Audit",
         "What did the Auditor-General find about deposits and retentions not "
         "disclosed in the statement of cash flows?"),
    ]

    _model = config.MODEL_NAME if config.PROVIDER == "anthropic" else config.DEEPSEEK_MODEL
    print(f"Provider: {config.PROVIDER}  |  Model: {_model}")

    for label, question in QUESTIONS:
        print("\n" + "=" * 72)
        print(f"[{label}] Q: {question}")

        print("\n-- retrieved chunks (grounding evidence) --")
        for c in retrieve(question, k=4):
            snippet = " ".join(c["text"].split())[:150]
            print(f"  {c['source']} p{c['page']} (score={c['score']:.3f}): {snippet}...")

        print("\n-- get_response() --")
        result = get_response(question)
        print("  text        :", result["text"])
        print("  citation    :", result["citation"])
        print("  last_updated:", result["last_updated"])

    # Value-for-money scripted comparison (should pull the real contract sum,
    # stay comparative, and never accuse).
    vfm_query = "Je, hii shule ilikuwa na thamani ya pesa iliyotumika?"
    print("\n" + "=" * 72)
    print(f"[Value-for-money] Q: {vfm_query}")
    print("\n-- get_response() --")
    vfm_result = get_response(vfm_query)
    print("  text        :", vfm_result["text"])
    print("  citation    :", vfm_result["citation"])
    print("  last_updated:", vfm_result["last_updated"])
