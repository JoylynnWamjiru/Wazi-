"""Ask Wazi through the full RAG pipeline (retrieval + DeepSeek generation)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.orchestrate import get_response

QUERIES = [
    "How much did the construction of the outpatient block at Njoro Level 4 Hospital cost?",
]

for q in QUERIES:
    print(f"\n=== QUESTION: {q!r}")
    answer = get_response(q)
    print(f"ANSWER: {answer.get('text')}")
    print(f"CITATION: {answer.get('citation')}")
    chunks = answer.get("chunks", [])
    print(f"RETRIEVED ({len(chunks)} chunks) — top 3:")
    for c in chunks[:3]:
        snip = " ".join(c.get("chunk_text", "").split())[:110]
        print(f"  [{c.get('source_title', '?')[:40]} p{c.get('page_number')}] {snip}")
