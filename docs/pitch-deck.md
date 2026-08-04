# Wazi — Pitch Deck & Storyline

> 5-minute pitch with 5:20 hard stop
> Demo Day: 2026-07-31
> Audience: Mozilla Foundation & KamiLimu mentors/judges

---

## Timing Budget

| Section | Seconds | Cumulative |
|---------|---------|------------|
| Title (intro) | 5 | 0:05 |
| 1. Problem | 25 | 0:30 |
| 2. Community | 20 | 0:50 |
| 3. Solution | 25 | 1:15 |
| 4. Why AI | 25 | 1:40 |
| **5. Demo** | **90** | **3:10** |
| 6. What's left | 25 | 3:35 |
| 7. Responsible Computing | 30 | 4:05 |
| 8. Impact | 20 | 4:25 |
| 9. Resources | 25 | 4:50 |
| 10. Team | 15 | 5:05 |
| Closing | 10 | 5:15 |

---

## Story Spine

**Character:** Mwangi, 24, youth advocate, Nakuru County.

**Before — The world with the problem (Slide 1):**
Mwangi stands at a county budget forum. The official projects a 200-page PDF — English,
technical, unreadable on a phone. Mwangi asks about Kshs 17 million allocated for a
classroom project his community has been waiting for. The official says the money was
spent. Mwangi has no way to verify this. He leaves with a photocopy he cannot search and
a community that will ask him tomorrow what he found out. He has nothing to tell them.

**With solution — The world Wazi opens (Slide 5 — Demo):**
Mwangi opens WhatsApp. Types: "Je, mradi wa darasa Keringet uligharimu pesa ngapi?"
In under a minute, the reply: "Mradi huu uligharimu Kshs 16,999,852. Chanzo: ripoti ya
Mkaguzi Mkuu, ukurasa 15." Below the answer, a button: "🚩 Report this." Three citizens
from his community tap it. The answer is flagged, a human moderator reviews the retrieved
source chunks, and the claim is verified — or corrected. Mwangi walks into the next
community meeting with evidence, not just questions.

**After — The ideal (Slide 10 / Closing):**
It is 2027. Pre-election budget forums are happening across Nakuru. Mwangi opens
WhatsApp. He has answers. He shares them with his community group. The conversation
shifts from "they stole the money" to "here is what the Auditor-General found — let us
ask them about page 15." A public fund that once answered to no one now answers to
everyone, in a language they speak, on a channel they use, with receipts they can demand.

---

## Slide Content

### TITLE SLIDE

```
Wazi
Democratising County Budget Access — One WhatsApp Message at a Time

Chris Waweru Gichohi · Joyline Njeri Wanjiru
WAZIRI · Dedan Kimathi University of Technology · University of Nairobi
```

**Narration:** _(none — displayed while being introduced)_

---

### SLIDE 1 — The Problem

```
60% of Kenyans are dissatisfied with government transparency.
          — EACC National Ethics & Corruption Survey, 2023

The information exists. It is just not accessible to the people who need it.
```

**Narration (25s):**
"Sixty percent of Kenyans are dissatisfied with government transparency. Not because the
information doesn't exist — the Auditor-General publishes detailed reports. The Controller
of Budget tracks every shilling. But those reports are 200-page, technical English PDFs on
desktop websites. A youth advocate in Nakuru who speaks Swahili and Sheng, who uses
WhatsApp on a Tecno phone with intermittent data — that person cannot access any of it."

---

### SLIDE 2 — The Community

```
Primary user:   Youth advocates & community-based organisations in rural Kenyan counties

Channel:         WhatsApp — text and voice notes

Language:        Swahili · Sheng — not formal English

Current reality: Word-of-mouth · local radio · no way to verify claims against official records
```

**Narration (20s):**
"Our users are youth advocates like Mwangi. He is 24. He is the person his community
turns to when they want to know what happened to the classroom funds. He is WhatsApp-literate,
mobile-first, and Swahili-speaking. His current toolset for budget accountability is word of
mouth, local radio, and barazas where the answers come as unverifiable claims. He has
never once been able to check a budget figure against an official source — not because
he does not want to, but because no tool was built for someone like him."

---

### SLIDE 3 — The Solution

```
         ┌──────────┐
         │ Citizen  │  "Mradi uligharimu pesa ngapi?"
         │ WhatsApp │
         └────┬─────┘
              │
              ▼
    ┌─────────────────┐
    │  RAG Pipeline   │  Retrieval-Augmented Generation
    │  (pgvector)     │  over curated county PDF corpus
    └────────┬────────┘
              │
              ▼
    ┌─────────────────┐
    │  DeepSeek LLM   │  Answer grounded in source,
    │  Swahili/Sheng  │  register-matched, with citation
    └────────┬────────┘
              │
              ▼
         ┌──────────┐
         │ Citizen  │  "Kshs 16,999,852. Chanzo: ripoti ya
         │ WhatsApp │   Mkaguzi Mkuu, ukurasa 15."
         └──────────┘
              │
              ▼
    ┌─────────────────┐
    │  Human Review   │  Community disputes → moderation
    │  Dashboard      │  queue → resolution or escalation
    └─────────────────┘
```

**Narration (25s):**
"A citizen sends a Swahili question on WhatsApp. Our retrieval engine searches a curated
corpus of county budget documents — audit reports, BIRRs, budget estimates — and finds
the relevant passages. DeepSeek generates an answer grounded ONLY in those chunks, in
the same language register the citizen used. Every answer carries a source citation —
document name and page number. If the community disputes an answer, a human moderator
reviews the original source text and issues a correction or escalates."

---

### SLIDE 4 — Why AI-Powered

```
Why AI?

✗ Rule-based:     Cannot handle Swahili/Sheng variability or open-ended questions
✗ Translation-only: Loses the connection between citizen query and fiscal evidence
✗ Direct PDF:     200 pages, English, inaccessible on a feature phone

✓ RAG pipeline:   Retrieves only from verified government documents
✓ Multilingual:   Same embedding space for English sources + Swahili/Sheng queries
✓ Grounded:       Every figure traceable to a specific source page — no hallucination
```

**Narration (25s):**
"You cannot solve this with a rule-based chatbot — Swahili and Sheng are too fluid,
and citizen questions are too open-ended. You cannot solve it by just publishing translated
PDFs — the document is still 200 pages and unsearchable on a phone. Retrieval-Augmented
Generation is the right lever here: the AI retrieves only from verified government documents,
and the multilingual embedding model places Swahili queries and English source text in
the same mathematical space. The AI does not guess — it either finds the answer in the
corpus, or it says 'sina taarifa za kutosha.'"

---

### SLIDE 5 — Demo (90 seconds)

```
What we have built since the hackathon:

✓  PostgreSQL + pgvector database — 6 tables, persistent storage
✓  WhatsApp webhook receiver — HMAC identity hashing, no PII stored
✓  9-document source registry — OAG audits, CoB BIRRs, KIPPRA budget documents
✓  Full admin moderation dashboard — dispute workflow with status transitions
✓  FastAPI backend with 13 API endpoints
✓  Automated test suite

[LIVE DEMO — switch to screen share]
```

**Narration — Part 1, Context (15s):**
"Since the hackathon four weeks ago, we have moved from a single-file Streamlit prototype
to a production-architected system. Here is what that looks like."

**Demo sequence (60s):**

1. **Admin dashboard login → Overview tab** (10s)
   "This is the moderator dashboard. Seven sources registered — we just added two more
   from KIPPRA this week. Zero chunks ingested — our next sprint pushes data into pgvector."

2. **Sources tab** (10s)
   "Nine documents across the budget cycle: Auditor-General reports, quarterly BIRRs,
   a CBROP, and programme-based budget estimates. Every source is registered, traceable,
   and ready for the scraper."

3. **WhatsApp webhook demo** (15s)
   "Citizen sends a message. The webhook receives it via form-encoded POST from
   Africa's Talking. The phone number is HMAC-hashed with a secret salt before it
   touches any database. The citizen gets an immediate acknowledgment, and the
   pipeline runs in a background thread so the event loop stays free."

4. **Sessions browser** (10s)
   "The message appears in the sessions tab. Moderators can open any conversation
   transcript. The user ID is the salted hash — not a phone number, never reversible."

5. **Dispute moderation** (15s)
   "When citizens dispute an answer, it enters a moderation queue. The moderator sees
   the original question, the AI's answer, and exactly which source chunks the AI was
   given. They can resolve with a correction message — which triggers a WhatsApp
   notification back to the citizen — or escalate with a generated report."

**Narration — Part 2, Honesty (15s):**
"What you are not seeing yet: the pgvector search is not live — our pipeline still uses
the original FAISS index. The WhatsApp send path is in dev mode — our Africa's Talking
billing is being provisioned by the buildathon facilitators. And the scheduled scraper is
architected but not implemented. We are honest about what is left."

---

### SLIDE 6 — What Is Left to Build Before 17 August

```
Remaining (3 weeks):

Week 2-3:   Pipeline refactor — FAISS → pgvector, DeepSeek-only generation
Week 3:     Scheduled scraper — APScheduler pulling from CoB, OAG, KIPPRA
Week 3-4:   WhatsApp send path — activate once AT billing clears
Week 4:     Anti-bot dispute thresholds — time-window + hashed-ID diversity
Week 4-5:   Linguist validation integration
Week 5:     Security hardening, retention cron, production deploy on Digital Ocean
```

**Narration (25s):**
"Our remaining work is well-scoped. The pipeline refactor is the critical path — migrating
from in-memory FAISS to pgvector for persistent, scalable vector search. The scraper is a
single APScheduler job pulling from three government URLs we have already identified and
verified. WhatsApp activation is waiting on billing — the code is written, tested with curl,
and ready to swap. Everything else — anti-bot thresholds, linguist validation UI, security
hardening — fits within the remaining three weeks."

---

### SLIDE 7 — Responsible Computing

```
Built in:
  • No PII stored — wa_id is HMAC-SHA256 hashed + salted on receipt
  • Identity separated from content — disputes and messages live in
    separate tables with no join path to the questioner's identity
  • Grounded-only generation — the AI answers from the corpus or says
    "sina taarifa za kutosha" — it never guesses

Trade-off acknowledged:
  Wazi answers LESS than a general chatbot.
  Anything outside our curated document corpus gets an honest "I don't know."
  We chose trust over breadth — a wrong number about public money is worse
  than no number at all.

How we'll measure it:
  Answer grounding score — percentage of generated claims verifiable against
  the cited source chunk, measured via automated natural language inference.
  Target: >95% of claims directly attributable to the cited passage.
```

**Narration (30s):**
"Responsible computing is not an afterthought — it is in the architecture. Phone numbers
are HMAC-hashed with a secret salt on receipt and never stored. Disputes and chat history
live in separate database tables with no join path — you cannot query 'who reported what.'
The AI is constrained to a curated document corpus and instructed to say 'I don't know'
rather than fabricate. The trade-off: Wazi answers less than a general chatbot. We chose
trust over breadth because a wrong number about public money is worse than no number.
And we will measure our grounding: over 95 percent of generated claims should be directly
attributable to the cited source passage, verified via automated inference."

---

### SLIDE 8 — Opportunity for Impact

```
Before Wazi:                             With Wazi:
────────────────────────────              ────────────────────────────
A 200-page PDF on a desktop website      →  A 30-second WhatsApp answer
Technical English, 47-county format      →  Swahili or Sheng, Nakuru-specific
No way to verify claims at a baraza      →  Cited source, page number, dispute button
Citizen leaves the meeting with nothing  →  Citizen arrives at the meeting with evidence

Scale path:
Nakuru (MVP) → all 47 Kenyan counties via the same source registry pattern
```

**Narration (20s):**
"A 200-page PDF on a desktop website becomes a 30-second WhatsApp answer in Swahili.
Technical English becomes Sheng. A citizen who used to leave a baraza with nothing now
arrives at the next one with a cited source, a page number, and a community that has
already verified the claim. The path from one county to forty-seven is a configuration
change — every source URL follows the same pattern, and the pipeline is county-agnostic
by design."

---

### SLIDE 9 — What It Would Take to Launch

```
To take Wazi into the community after 21 August:

Resources needed:
  • Africa's Talking WhatsApp Business API — $135 setup + $50/month (in progress)
  • Digital Ocean droplet — $24/month (hosting FastAPI + PostgreSQL)
  • DeepSeek API credits — ~$20/month at projected query volume
  • Native Swahili/Sheng linguist — 5 hours/week for answer quality validation

Sustainability:
  • Partnership with IBP Kenya / Bajeti Hub — access to structured budget data
  • Integration into existing civic-tech networks (Mzalendo, BudgIT)
  • Open-source codebase — community contributions, transparent audit trail
```

**Narration (25s):**
"To launch, we need about seventy dollars a month in infrastructure — Digital Ocean droplet,
DeepSeek API credits — plus the WhatsApp Business API which the buildathon facilitators
are already provisioning. Sustaining it means partnerships: IBP Kenya for structured
budget data, the Controller of Budget for machine-readable reports, and integration into
existing civic-tech networks so Wazi is not a standalone tool but part of a transparency
ecosystem. The code is open source — anyone can audit it, and that matters when you are
building trust tools for civic accountability."

---

### SLIDE 10 — The Team

```
Chris Waweru Gichohi          Joyline Njeri Wanjiru
Solutions Architect           Backend & AI Engineer
Frontend · Architecture       Database · LLMs · RAG pipelines
Dedan Kimathi University      University of Nairobi

Built together: 6,000+ lines of code in 4 weeks, across 5 merged PRs,
13atabase tables, 9 government sources.
```

**Narration (15s):**
"Chris brings systems architecture and frontend engineering — he designed the API contract,
built the admin dashboard, and architected the messaging abstraction that lets us swap
WhatsApp for any channel. Joyline brings backend and AI engineering — she designed the
PostgreSQL schema with pgvector, the HMAC identity layer, and the pipeline architecture.
We have shipped six thousand lines of code in four weeks, across five merged pull requests."

---

### CLOSING

```
Wazi
Democratising County Budget Access — One WhatsApp Message at a Time

Chris Waweru Gichohi · Joyline Njeri Wanjiru
```

**Narration (10s):**
"It is 2027. Mwangi opens WhatsApp. He has answers — grounded, cited, verified by his
community. He walks into the pre-election baraza not with questions but with evidence.
Because a public fund that once answered to no one now answers to everyone, in a
language they speak, on a channel they use. That is Wazi. Asanteni."

---

## Honesty Audit

| Claim in deck | Status | Risk if challenged |
|--------------|--------|-------------------|
| "PostgreSQL + pgvector database" | ✅ Built and merged | None |
| "WhatsApp webhook receiver with HMAC hashing" | ✅ Built, tested with curl | Judge may ask: "Show me a message arriving from WhatsApp." Honest answer: "WhatsApp send/receive is in dev mode — AT billing is being provisioned. The webhook handler is written, tested synthetically, and ready to activate." |
| "9-document source registry" | ✅ Seeded in PostgreSQL | None |
| "Full admin moderation dashboard" | ✅ Built, tested against real backend | None |
| "Pipeline runs in background thread" | ✅ `asyncio.to_thread()` implemented | None |
| "Correction message triggers WhatsApp notification" | ⚠️ Code path exists but AT send is dev-mode | Honest answer: "The correction is stored and the send function is architected — it logs in dev mode and will activate when billing clears." |
| "pgvector search" | ❌ Pipeline still uses FAISS | Framed as "next sprint" — honest |
| "Scheduled scraper" | ❌ Not built | Framed as "remaining work" — honest |
| "Answer grounding score >95%" | ❌ Not measured yet | Framed as "how we'll measure it" — honest |

---

## RC Dimensions That Apply to Wazi

| Dimension | How it is built in |
|-----------|-------------------|
| **Privacy / surveillance** | HMAC-hashed wa_id, no PII stored, identity separated from content |
| **Misinformation / hallucination** | Grounded-only generation, curated corpus, "sina taarifa za kutosha" fallback |
| **Language exclusion** | Multilingual embedding model, register-matched responses (Swahili/Sheng/English) |
| **Accessibility** | WhatsApp-native — works on feature phones, low-bandwidth, no app install |
| **Misuse by bad actors** | Disputes require human review before surfacing; unverified claims never shown as fact |
| **Data retention** | 90-day chat retention, 1-year dispute retention — documented policy, cron-enforced |
