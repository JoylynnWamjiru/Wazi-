# Wazi — 12-Day Build Sprint (Final Push)

> 2026-08-05 → 2026-08-17
> Build hard stop: 17 August 2026

---

## VPS Assessment

| Spec | Value | Implication |
|------|-------|-------------|
| CPU | 2 Intel vCPU | Sufficient for FastAPI + PostgreSQL |
| RAM | 1 GB | **Tight.** No Docker — install PostgreSQL directly on Ubuntu. Embedding model (~470MB) cannot run here alongside PostgreSQL. |
| Disk | 35 GB NVMe | Plenty for OS, PostgreSQL data, and PDF corpus |
| Bandwidth | 1000 GB transfer | More than sufficient |
| OS | Ubuntu 24.04 LTS | Standard, well-supported |

**Architecture decision:** The VPS runs PostgreSQL + the FastAPI backend (webhook + admin API routes ONLY — not the embedding model). The Streamlit citizen chat app stays on Streamlit Community Cloud (which has more RAM for the ONNX model). The admin dashboard also stays on Streamlit Cloud (no reason to move it).

```
VPS (157.230.232.223)                    Streamlit Community Cloud
├── PostgreSQL 16 + pgvector              ├── Citizen chat (src/app/streamlit_app.py)
└── FastAPI                               └── Admin dashboard (src/admin/dashboard.py)
    ├── Webhook (WhatsApp receiver)
    ├── Admin API (disputes, sources,     Admin dashboard → WAZI_API_URL=157.230.232.223
    │   stats, sessions, messages)
    └── Pipeline (retrieval + generation)
        ├── MiniLM embeddings (~470MB)
        └── DeepSeek API calls

RAM budget (VPS):                        RAM budget (Streamlit Cloud):
  PostgreSQL:         ~250 MB               Managed by Streamlit
  FastAPI + Python:   ~200 MB               No cost to us
  OS:                 ~200 MB
  Embedding model:    ~470 MB (spike)
  Buffer:             ~80 MB
  Total peak:         ~1.2 GB  ⚠ TIGHT
```

**Risk:** The embedding model loading may spike RAM past 1GB. Mitigation: configure PostgreSQL `shared_buffers = 128MB` (low), set a swap file (2GB) as safety net. If the VPS runs out of memory and crashes during embedding, the swap file prevents OOM-kill. Acceptable for MVP.

---

## 12-Day Sprint Plan

### Day 1-3 (Aug 5-7): Pipeline Refactor + pgvector Migration

**Goal:** Split `pipeline.py` (god module) into clean modules. Migrate from FAISS IndexFlatIP to pgvector HNSW.

Files to create/modify:
```
src/ingestion/
├── extract.py          (unchanged)
├── chunk.py            (unchanged)
├── embed.py            ← refactor: embed() stores in pgvector, not FAISS
├── retrieve.py         ← NEW: pgvector cosine similarity search
├── generate.py         ← NEW: DeepSeek API call with system prompt
├── orchestrate.py      ← NEW: get_response() — ties retrieve + generate
├── vfm.py              ← NEW: LLM-driven value-for-money (replace regex)
└── pipeline.py         ← stripped: re-exports orchestrate.get_response for backward compat
```

Key changes:
1. `embed.py`: Replace `IndexFlatIP` with pgvector `INSERT INTO chunks (...) VALUES (...) RETURNING id`
2. `retrieve.py`: `SELECT ... ORDER BY embedding <=> query_embedding LIMIT k` with optional `government_arm` filter
3. `generate.py`: Extract `_generate_deepseek()` and `SYSTEM_PROMPT` from old `pipeline.py`
4. `orchestrate.py`: `get_response()` — calls retrieve → generate → parse USED_CHUNK → return
5. `vfm.py`: Replace hardcoded regex with LLM prompt: "Compare this contract sum against typical Kenyan construction benchmarks..."
6. `pipeline.py`: Keep `build_corpus()` + re-export `orchestrate.get_response` for backward compat

**Success criteria:** `python src/ingestion/orchestrate.py` runs the CLI demo with real data from pgvector, DeepSeek answers are grounded and cited.

### Day 4-5 (Aug 6-7): VPS Setup + PostgreSQL Install

**Goal:** PostgreSQL 16 + pgvector running on the VPS. FastAPI deployed and responding to `/health`.

Step-by-step VPS setup:
```bash
# 1. SSH into VPS
ssh root@157.230.232.223

# 2. Update system
apt update && apt upgrade -y

# 3. Install PostgreSQL 16 + pgvector
apt install -y postgresql-16 postgresql-16-pgvector python3-pip python3-venv git nginx

# 4. Create swap file (2GB safety net for RAM spikes)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 5. Configure PostgreSQL for low RAM
# Edit /etc/postgresql/16/main/postgresql.conf:
#   shared_buffers = 128MB
#   effective_cache_size = 256MB
#   maintenance_work_mem = 32MB
#   work_mem = 4MB
#   max_connections = 10

# 6. Create database and user
sudo -u postgres psql -c "CREATE USER wazi WITH PASSWORD 'strong-password-here';"
sudo -u postgres psql -c "CREATE DATABASE wazi_db OWNER wazi;"
sudo -u postgres psql -d wazi_db -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 7. Clone repo
cd /opt
git clone https://github.com/JoylynnWamjiru/Wazi-.git wazi
cd wazi

# 8. Setup Python venv + install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 9. Create .env
cp .env.example .env
# Edit .env: DATABASE_URL, DEEPSEEK_API_KEY, ID_SALT, ADMIN_PASSWORD

# 10. Seed database
python scripts/seed_db.py

# 11. Test FastAPI
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
curl http://localhost:8000/health

# 12. Setup systemd service (auto-restart)
# (see systemd unit file below)
```

Systemd unit file (`/etc/systemd/system/wazi.service`):
```ini
[Unit]
Description=Wazi FastAPI
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/wazi
Environment=PATH=/opt/wazi/venv/bin
ExecStart=/opt/wazi/venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Day 6-7 (Aug 10-11): Wire Pipeline into Webhook + End-to-End Test

**Goal:** Replace the fallback "Samahani..." response in `webhooks.py` with actual pipeline output.

What changes:
1. `webhooks.py` `_run_pipeline()` imports `orchestrate.get_response` instead of the old god module
2. Verify: citizen sends WhatsApp message → webhook hashes wa_id → pipeline retrieves from pgvector → DeepSeek generates answer → answer stored with citation → answer sent back
3. The citizen chat Streamlit app is not the target channel, but verify it still works as a fallback demo
4. Admin dashboard pointed at `WAZI_API_URL=http://157.230.232.223:8000` — verify all 4 tabs load real data from the VPS

**Success criteria:** `curl -X POST /whatsapp/incoming` with a Swahili query → assistant answer with real Kshs figure and citation stored in PostgreSQL, visible in admin dashboard Sessions tab.

### Day 8-9 (Aug 12-13): Testing + Anti-Bot Dispute Thresholds

**Goal:** Automated tests for pipeline. Anti-bot logic in dispute creation.

1. **Tests to write:**
   - `tests/test_extract.py` — verify PDF text extraction
   - `tests/test_chunk.py` — verify chunk boundaries, overlap, page preservation
   - `tests/test_retrieve.py` — verify pgvector search returns correct chunks
   - `tests/test_webhook.py` — verify webhook hashes wa_id, creates user/session/message
   - `tests/test_api.py` — verify all admin API endpoints return correct shapes

2. **Anti-bot dispute thresholds:**
   - Before creating a Dispute record, check:
     - Hashed wa_id has not reported the same message_id before (dedup)
     - Time since last dispute from this wa_id > 30 seconds (velocity check)
     - At least N distinct hashed wa_ids must report same message before `report_count` increments (diversity threshold, N=3)
   - This lives in a new `src/api/middleware/anti_bot.py` dependency injected into the webhook's dispute endpoint

### Day 10-12 (Aug 14-16): Security Hardening, Bug Fixes, Polish

1. **Security checklist:**
   - [ ] Rotate all API keys committed or shared in chat
   - [ ] Verify `.env` not in repo (double-check git history)
   - [ ] SSH: disable password auth, use keys only
   - [ ] UFW firewall: allow only ports 22, 80, 443, 8000
   - [ ] Nginx reverse proxy in front of FastAPI (port 80 → 8000)
   - [ ] PostgreSQL: bind to localhost only (not 0.0.0.0)
   - [ ] HTTPS via Let's Encrypt / certbot

2. **Retention cron:** Implement `DATA_RETENTION.md` policy — delete messages older than 90 days, disputes older than 1 year.

3. **Bug fixes:** Fix any issues found during testing. Priority: anything that breaks the demo flow.

4. **Demo dry run:** Full run-through of the pitch flow against the VPS deployment.

---

## Deployment Architecture (Final)

```
┌─────────────────────────────────────────────────────────┐
│ VPS (157.230.232.223) — Ubuntu 24.04, 1GB RAM           │
│                                                         │
│  ┌──────────────────┐   ┌──────────────────────────┐   │
│  │ PostgreSQL 16    │   │ FastAPI (Uvicorn)         │   │
│  │ + pgvector       │   │ Port 8000                 │   │
│  │ Port 5432        │   │                           │   │
│  │ (localhost only) │   │ /whatsapp/incoming        │   │
│  └──────────────────┘   │ /api/disputes             │   │
│                          │ /api/sources              │   │
│  ┌──────────────────┐   │ /api/stats                │   │
│  │ Embedding model  │   │ /api/sessions             │   │
│  │ (MiniLM, ~470MB) │   │ /api/messages             │   │
│  │ Loaded on demand │   │ /health                   │   │
│  └──────────────────┘   └──────────────────────────┘   │
│                                                         │
│  ┌──────────────────┐                                  │
│  │ Nginx            │                                  │
│  │ Port 80 → 8000   │                                  │
│  └──────────────────┘                                  │
└─────────────────────────────────────────────────────────┘
          ▲                              ▲
          │                              │
          ▼                              ▼
┌──────────────────┐    ┌──────────────────────────────┐
│ Africa's Talking │    │ Streamlit Community Cloud     │
│ WhatsApp API     │    │                              │
│ (pending billing)│    │ Citizen chat (port 8501)      │
└──────────────────┘    │ Admin dashboard (port 8502)   │
                        │                              │
                        │ WAZI_API_URL =               │
                        │ http://157.230.232.223:8000  │
                        └──────────────────────────────┘
```

---

## What We Are NOT Building

These are explicitly deferred to post-MVP:
- Scheduled scraper (APScheduler) — the source registry and URLs exist; scraping is manual until then
- Sheng embedding fine-tuning — the multilingual model works for formal Swahili; Sheng is weak but honest about it
- TTS / voice notes
- Multi-county support
- Public transparency dashboard
- Linguist validation integration
- EACC auto-email (escalation report generation exists, manual send is fine)
