"""Orchestrate the ingestion + retrieval + generation pipeline.

- ``build_corpus()``  : check -> extract -> chunk -> save data/chunks.json
- ``get_response()``  : retrieve grounded chunks -> ask Claude -> cited answer
"""

import json
import sys
from pathlib import Path

# Put src/ on the path so `shared` and sibling `ingestion.*` modules import
# cleanly whether run as `python src/ingestion/pipeline.py` or imported.
SRC_DIR = Path(__file__).resolve().parents[1]  # .../src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ingestion.extract import check_text_layer, extract_pages
from ingestion.chunk import chunk_pages
from ingestion.embed import retrieve
from shared import config

# Repo root is three levels up from this file: src/ingestion/pipeline.py
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

PDF_FILES = [
    "nakuru_audit_report.pdf",
    "nakuru_birr_q2.pdf",
]

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
   Chanzo: nakuru_birr_q2.pdf, ukurasa 2"""


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


def get_response(query: str) -> dict:
    """Answer a citizen question, grounded in the retrieved corpus chunks.

    Returns a dict matching the pipeline_interface contract:
    ``{"text": ..., "citation": ..., "last_updated": ...}``. Any failure in
    retrieval or the LLM call falls back to ``config.FALLBACK_ANSWERS`` rather
    than raising. The provider (Anthropic or DeepSeek) is chosen in config
    based on which API key is present.
    """
    try:
        chunks = retrieve(query, k=4)
        context = "\n\n".join(
            f"[{i + 1}] Source: {c['source']}, page {c['page']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        user_content = f"CONTEXT:\n{context}\n\nQUESTION: {query}"

        if config.PROVIDER == "anthropic":
            text = _generate_anthropic(SYSTEM_PROMPT, user_content)
        elif config.PROVIDER == "deepseek":
            text = _generate_deepseek(SYSTEM_PROMPT, user_content)
        else:
            raise RuntimeError("No LLM API key configured (Anthropic or DeepSeek)")

        # Citation is taken from the top retrieved chunk's metadata, so it is
        # always accurate regardless of how the model phrases its own line.
        if chunks:
            top = chunks[0]
            citation = f"{top['source']}, page {top['page']}"
        else:
            citation = "N/A"

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
