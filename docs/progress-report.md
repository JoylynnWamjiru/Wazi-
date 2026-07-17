# Wazi — Progress Report

> Prepared: 2026-07-17 · Team WAZIRI (Chris Waweru Gichohi, Joyline Njeri Wanjiru)
> For: mentor review — implemented work mapped against the [5-week strategic plan](strategic-plan.md)
> Repository: https://github.com/JoylynnWamjiru/Wazi-

---

## 1. Executive Summary

The Democracy & AI Hackathon (July 4) produced a **working, end-to-end, verified prototype**: a citizen asks a question in Swahili, Sheng, or English through a WhatsApp-style chat; the system retrieves passages from real Nakuru County fiscal documents, generates a grounded answer in the citizen's own language register, and cites the exact source document and page. Every strength listed in §1.3 of the strategic plan exists in the repository today and was verified against live queries.

The strategic plan (July 16) charts the path from this prototype to a real WhatsApp-based MVP over 5 weeks. As of today we are at **Day 1–2 of Week 1**. This report shows exactly which planned capabilities already exist, which are partially built, and which start from zero.

**In one line:** the AI core (ingestion → retrieval → grounded generation → citation) is done and tested; the productization layer (WhatsApp, persistence, moderation, scheduling) is the 5-week work ahead.

---

## 2. What Is Already Implemented (and Verified)

### 2.1 Ingestion pipeline — `src/ingestion/extract.py`, `chunk.py` (commit `5fc7aec`)

- **Text-layer detection:** `check_text_layer()` inspects the first pages of each PDF and refuses scanned/image-only documents that would need OCR — both corpus PDFs pass.
- **Per-page extraction** with PyMuPDF; blank/cover pages (< 20 chars) skipped; every page record keeps `{source, page, text}`.
- **Page-bounded chunking:** ~500-word chunks with 50-word overlap that **never cross page boundaries**, so every chunk is traceable to exactly one page — the foundation of trustworthy citations. Chunk IDs are human-readable (`nakuru_audit_report_p12_c0`).
- **Corpus:** 34 chunks from two real documents — the Auditor-General's report on the Nakuru County Executive (16) and the Nakuru BIRR FY2024/25 (18) — written to a human-inspectable `data/chunks.json`.
- **Verified:** schema integrity, unique chunk IDs, word-count bounds, page traceability, and the overlap logic proven on synthetic long pages (real pages are short enough to fit single chunks).

### 2.2 Cross-lingual retrieval — `src/ingestion/embed.py` (commits `8fb208e`, `6c4b56c`)

- **Multilingual embeddings** (`paraphrase-multilingual-MiniLM-L12-v2`) served via **fastembed/ONNX** — no torch dependency, ~5× smaller install footprint.
- **FAISS `IndexFlatIP`** over L2-normalized vectors (cosine), lazy-built once and cached.
- **Measured impact:** the original English-only model failed a Swahili test query (top score 0.359, wrong chunk → the system correctly refused to answer). Switching to the multilingual model retrieves the correct chunk at score **0.601**. This is exactly the "shared vector space, no translation middleware" approach the plan endorses (§2.5).

### 2.3 Grounded generation — `src/ingestion/pipeline.py` (commits `8fb208e`, `6c4b56c`)

- **DeepSeek** as the generation LLM (plan §2.1), behind a provider switch that is Anthropic-ready.
- **Strict grounding prompt:** answer only from retrieved chunks; never invent or round a figure; detect the citizen's register (formal Swahili / Sheng / English) and reply in the same register; refuse with *"sina taarifa za kutosha"* when the context doesn't contain the answer.
- **Citation from the chunk actually used:** the model emits a machine-readable `USED_CHUNK: N` marker; the citation field derives from that chunk's metadata rather than blindly trusting the top retrieval hit (this fixed a real observed drift where the top chunk was p6 but the answer came from p4).
- **Two-layer failure safety:** the pipeline catches any retrieval/API error and returns the configured Swahili fallback; the UI wraps the call again. Verified by deliberately blanking the API key — the citizen sees a clean fallback message, never a traceback.

### 2.4 Value-for-money comparison — scripted v1 (commit `6c4b56c`)

- Trigger-word detection (English + Swahili) routes value-for-money questions to a benchmark comparison built on a **real corpus figure**: the delayed, incomplete Keringet construction contract of **Kshs 16,999,852** (audit report, p15) against an illustrative Kshs 2,000,000–4,000,000 benchmark, with the verdict computed, not hardcoded.
- **Hard framing requirement honored:** output always says the amount *"kinahitaji ufafanuzi zaidi"* (warrants further clarification) — never an accusation.
- The plan correctly labels this a scripted shortcut (§1.1 note); replacing it with LLM-driven comparative reasoning (`vfm.py`) is planned work.

### 2.5 Citizen-facing UI — `src/app/streamlit_app.py` (commit `6c4b56c`)

- WhatsApp-style chat: user messages right-aligned in green bubbles, bot replies left-aligned in white cards, dark-mode aware.
- Welcome state with **tap-to-ask example questions**; upfront index warm-up with a visible status (no silent first-question hang); bilingual labels throughout.
- Every answer carries a **muted citation line** (📄 Chanzo · Source: document, page).
- **Community dispute signal:** a 🚩 "Report this project status" button per reply with per-session counting — at 3 independent reports a banner appears: *"flagged for human/journalist review."* Verified by clicking through the full flow.
- Sidebar: trusted sources with descriptions, corpus last-updated date, and the quarterly re-ingestion cadence note.

### 2.6 Engineering hygiene

- Clean commit history (4 commits, each a coherent layer) pushed to GitHub.
- Secrets kept out of the repo (`.env` gitignored, `.env.example` template committed) — matching plan §8.2.
- Generated artifacts (`data/chunks.json`) and machine-local settings gitignored.
- Interface contract defined (`PipelineResponse` TypedDict + `Pipeline` Protocol) — the plan notes the Protocol is not yet consumed by the UI; that refactor is Week 2 work.

---

## 3. Verification Evidence

| Test | Result | Grounding |
|------|--------|-----------|
| Swahili revenue question (live UI) | "Kshs. 2,242,915,078 … 16% ya bajeti ya kila mwaka ya Kshs. 14,133,795,185" | `nakuru_birr_q2.pdf`, p3 |
| Swahili revenue question (pipeline) | "Kshs. 14.13 bilioni kutoka kwa Serikali ya Kitaifa" | `nakuru_birr_q2.pdf`, p2 |
| English audit question | Undisclosed variance of Kshs. 104,985,718 in deposits & retentions | `nakuru_audit_report.pdf`, p4 |
| Value-for-money question | Kshs 16,999,852 vs 2–4M benchmark → "kimezidi … kinahitaji ufafanuzi zaidi" | `nakuru_audit_report.pdf`, p15 |
| No-answer guard | Refused with "sina taarifa za kutosha" when retrieval missed the relevant chunk | — |
| API-failure path | Key removed → clean Swahili fallback, no traceback anywhere in UI | — |
| Dispute threshold | 3 reports → human/journalist review banner above the reply | — |
| Register matching | Swahili in → Swahili out; English in → English out | — |

All figures above appear verbatim in the source documents — none were fabricated by the model.

---

## 4. Progress Against the Plan's Tier-1 Features

| Tier-1 feature (plan §4) | Status | Where we are |
|---|---|---|
| RAG pipeline (→ pgvector) | 🟢 **Core built & verified** | Retrieval + grounded generation working end-to-end on FAISS in-memory; pgvector migration is Week 2 |
| Admin dashboard (authenticated) | 🟡 **Foundation exists** | Streamlit app built and styled; plan demotes it to admin role — needs auth + moderation views |
| Dispute database + moderation queue | 🟡 **UX proven, persistence pending** | Full citizen-side flow (report → threshold → review banner) verified; currently in-memory only |
| Source registry + scheduled ingestion | 🟡 **Machinery exists, automation pending** | The extract→chunk→embed pipeline a scheduler would invoke is done; sources are still a hardcoded 2-PDF list |
| WhatsApp webhook receiver | 🔴 **Not started** | Week 1 critical path — Africa's Talking docs research is the Day-1 action |
| Hashed `wa_id` identity | 🔴 **Not started** | Depends on webhook; design (SHA-256 + salt) already specified in plan §8 |

**Responsible computing already embodied in the prototype:** no PII collected or stored (nothing is persisted at all yet), corpus limited to curated official sources, mandatory citations, non-accusatory framing enforced in code, dispute claims framed for human review, graceful bilingual failure modes, secrets outside the repository. The plan's additions (hashed identity, retention policy, encryption at rest, threat model, ODPC research) are productization work, not gaps in the prototype's principles.

---

## 5. Known Gaps (Acknowledged, Planned)

These match the plan's own analysis (§1.4) and are scheduled, not surprises: no persistence layer (index, disputes, chat history all in-memory), zero automated tests, hardcoded two-document corpus, brute-force FAISS (fine at 34 chunks; pgvector HNSW planned), scripted rather than LLM-driven value-for-money reasoning, Streamlit standing in for WhatsApp, and single-county coverage.

---

## 6. Immediate Next Actions (Week 1, from plan §10)

1. Both: read Africa's Talking WhatsApp API documentation (critical path).
2. Joyline: PostgreSQL schema + FastAPI webhook scaffold with `wa_id` hashing on receipt.
3. Chris: Digital Ocean droplet + Docker Compose; deploy current Streamlit app as placeholder; CI/CD.
4. Both: write `docs/api-contract.md`; schedule threat-modeling session, IBP Kenya meeting, and linguist outreach.

---

*Commit history: `b389dd9` scaffold → `5fc7aec` extraction & chunking → `8fb208e` retrieval & generation → `6c4b56c` demo UI, VFM, citation-from-used-chunk.*
