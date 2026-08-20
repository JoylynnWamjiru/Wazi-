# Wazi — Full System Startup Guide

> Last updated: 2026-08-11

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│ Your Local Machine (Windows)                                  │
│                                                                │
│  Docker Desktop → PostgreSQL 16 + pgvector (port 5432)        │
│  Terminal 1 → FastAPI backend (port 8502)                      │
│  Terminal 2 → Citizen Chat Streamlit (port 8501)               │
│  Terminal 3 → Admin Dashboard Streamlit (port 8503)            │
│                                                                │
│  Admin dashboard talks to FastAPI via WAZI_API_URL env var.   │
│  Citizen chat imports the RAG pipeline directly (no HTTP).     │
└──────────────────────────────────────────────────────────────┘
                              ↕
┌──────────────────────────────────────────────────────────────┐
│ VPS (157.230.232.223) — Ubuntu 24.04, 1GB RAM                │
│                                                                │
│  PostgreSQL 16 + pgvector (port 5432, localhost only)         │
│  FastAPI via systemd (port 8000 → Nginx reverse proxy :80)    │
│  systemctl {start,stop,status,restart} wazi                    │
└──────────────────────────────────────────────────────────────┘
```

### Port Layout

| Port | Service | Notes |
|------|---------|-------|
| `5432` | PostgreSQL + pgvector | Docker (local) or native (VPS) |
| `8501` | Citizen Chat (Streamlit) | Local dev/demo only — WhatsApp-style UI |
| `8502` | FastAPI backend | Swagger at `/docs`, admin routes at `/api/*` |
| `8503` | Admin Dashboard (Streamlit) | Connects to FastAPI via `WAZI_API_URL` |

### Communication Flow

```
Citizen (WhatsApp)
    │  Africa's Talking webhook
    ▼
FastAPI :8502  ◄──── HTTP (httpx) ────  Admin Dashboard :8503
    │  │                                      (CRUD sources, disputes, sessions)
    │  │  direct Python import
    │  └──────────────────────────────  Citizen Chat :8501
    │                                      (get_response from orchestrate)
    ▼
PostgreSQL :5432  (pgvector cosine search, all app data)
```

All three apps share the same PostgreSQL database. The citizen chat imports
the RAG pipeline directly (no HTTP overhead), while the admin dashboard talks
to the FastAPI REST API so it can work against a remote VPS backend too.

---

## Local Development Startup

All commands run from `C:\Users\USER\Desktop\Wazi-` with the venv activated.

### Prerequisites

```powershell
# One-time: create venv and install dependencies
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# One-time: ensure .env exists with required secrets
# DEEPSEEK_API_KEY, DATABASE_URL, ADMIN_PASSWORD, ID_SALT are mandatory
```

### Step 1: Start PostgreSQL

```powershell
docker compose up -d
docker compose ps   # verify: wazi-postgres status is "healthy"
```

### Step 2: Start FastAPI backend (Terminal 1)

```powershell
.\venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --port 8502
```

Verify:
```powershell
curl http://localhost:8502/health
# Expected: {"status":"healthy","service":"wazi-api"}
```

### Step 3: Start Citizen Chat (Terminal 2)

```powershell
.\venv\Scripts\python.exe -m streamlit run src/app/streamlit_app.py --server.port 8501
```

Open `http://localhost:8501`. On first run the ONNX embedding model downloads
(~127 MB, one-time). The status message _"Inaandaa nyaraka za kaunti..."_ shows
during this download. Subsequent runs start instantly.

### Step 4: Start Admin Dashboard (Terminal 3)

```powershell
.\venv\Scripts\python.exe -m streamlit run src/admin/dashboard.py --server.port 8503
```

Open `http://localhost:8503` → login with `ADMIN_PASSWORD` from `.env`.

### Step 5: Verify seed data

```powershell
curl -H "Authorization: Bearer admin" http://localhost:8502/api/sources
# Expected: {"sources": [...], "total": 9}
```

### Quick Verification Checklist

- [ ] `docker compose ps` → wazi-postgres healthy
- [ ] `curl localhost:8502/health` → 200 OK
- [ ] `http://localhost:8501` → chat input visible, can ask questions
- [ ] `http://localhost:8503` → login succeeds, Sources tab shows 9 documents
- [ ] `http://localhost:8502/docs` → Swagger UI loads

---

## VPS Deployment

The VPS at `157.230.232.223` runs Ubuntu 24.04 with PostgreSQL 16 + pgvector
installed natively (not Docker). The FastAPI app runs as a systemd service
behind Nginx.

### VPS Provisioning (one-time)

Already done via `scripts/vps_setup.sh`. This installed:
- PostgreSQL 16 + pgvector extension
- Python 3.13 venv at `/opt/wazi/venv`
- Nginx reverse proxy (port 80 → uvicorn port 8000)
- systemd service `wazi.service`
- 2 GB swap (VPS has only 1 GB RAM)
- PostgreSQL tuned for low RAM: `shared_buffers=128MB`

### Landing page (wazi.aibuildathon.dev root)

The static splash page lives in the repo at `web/splash/index.html` and is
served by Nginx at the exact root `/` — everything else (`/health`, `/api/*`,
`/whatsapp/*`, `/docs`) still proxies to uvicorn on `:8000`.

The Nginx site config is `/etc/nginx/sites-available/wazi` (symlinked from
`sites-enabled`). The 443 server block needs an exact-match `location = /`:

```nginx
server {
   server_name wazi.aibuildathon.dev 157.230.232.223;

    location = / {
        root /opt/wazi/web/splash;
        try_files /index.html =404;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    listen 443 ssl; # managed by Certbot
    # ... existing cert lines unchanged ...
}
```

To (re)apply it:

```bash
cd /opt/wazi && git pull origin main        # file lands at /opt/wazi/web/splash/index.html
# edit /etc/nginx/sites-available/wazi with the block above
nginx -t                                   # must pass
systemctl reload nginx
curl -s -o /dev/null -w "%{http_code}" https://wazi.aibuildathon.dev/          # 200
curl -s https://wazi.aibuildathon.dev/health                                    # {"status":"healthy"}
```

Gotcha: use `try_files /index.html =404;` — NOT `index index.html;`. The
`index` directive did not serve inside the exact-match `location = /`, so `/`
fell through to the proxy and FastAPI returned `{"detail":"Not Found"}`.

### Full VPS startup sequence

Bring the production stack up (cold start or after a deploy), end to end:

```powershell
# 1. SSH in
ssh root@157.230.232.223

# 2. Confirm PostgreSQL is up and pgvector is installed
systemctl is-active postgresql
sudo -u postgres psql -d wazi_db -c "SELECT count(*) FROM pg_extension WHERE extname='vector';"

# 3. Pull the latest merged code and restart the API
cd /opt/wazi && git pull origin main
systemctl restart wazi
systemctl is-active wazi                    # -> active

# 4. Health checks (internal uvicorn, then public via Nginx)
curl http://localhost:8000/health
curl https://wazi.aibuildathon.dev/health          # -> {"status":"healthy"}

# 5. Seed sources if the registry is empty (both idempotent)
venv/bin/python scripts/migrate.py          # enum values, content_hash column
venv/bin/python scripts/seed_db.py          # registers the 9 sources as PENDING

# 6. Reset any FAILED sources before a bulk retry
sudo -u postgres psql -d wazi_db -c "UPDATE sources SET ingestion_status='PENDING' WHERE ingestion_status='FAILED';"

# 7. Run ingestion — one source, or every PENDING source
venv/bin/python -m src.ingestion.scraper --source-id 8   # fast smoke test
venv/bin/python -m src.ingestion.scraper --all           # full corpus (10–30 min)

# 8. Verify chunks landed
sudo -u postgres psql -d wazi_db -c "SELECT id, ingestion_status FROM sources ORDER BY id;"
sudo -u postgres psql -d wazi_db -c "SELECT count(*) FROM chunks;"
```

Notes:
- `ingestion_status` is a native enum whose **DB labels are uppercase**
  (`PENDING`, `COMPLETED`, `FAILED`). The SQLAlchemy ORM translates its
  lowercase values automatically, but **raw SQL must use uppercase**.
- For a long bulk run, background it so it survives SSH disconnect:
  `cd /opt/wazi && nohup venv/bin/python -m src.ingestion.scraper --all > scraper-all.log 2>&1 &`
  then watch with `tail -f scraper-all.log`.

### Check VPS status

```powershell
ssh root@157.230.232.223 "systemctl status wazi --no-pager"
```

### Deploy code updates to VPS

```powershell
# On your local machine — push merged code:
git push origin main

# On the VPS — pull and restart:
ssh root@157.230.232.223
cd /opt/wazi && git pull origin main
systemctl restart wazi
curl http://localhost:8000/health
```

### View VPS logs

```powershell
ssh root@157.230.232.223 "journalctl -u wazi -n 50 --no-pager"
```

### Watch live disputes/sessions (admin dashboard)

The admin dashboard is a **local** Streamlit app that reads live VPS data over
HTTP. Point it at the VPS and run it on your laptop:

```powershell
# One-off: point the dashboard at the live VPS API (or set this in .env)
$env:WAZI_API_URL = "https://wazi.aibuildathon.dev"

# Run from the repo root with the venv activated:
.\venv\Scripts\python.exe -m streamlit run src/admin/dashboard.py --server.port 8503
```

Open `http://localhost:8503` and log in with the **VPS's** `ADMIN_PASSWORD`
(the dashboard validates it against the backend — not your local `.env`):

```powershell
ssh root@157.230.232.223 "grep ADMIN_PASSWORD /opt/wazi/.env"
```

The sidebar's **Disputes** page is the human-verification loop: a moderator
sees the citizen's question, the AI's answer + citation, and the retrieved
source passages, then either resolves it (correction message) or escalates it
(an anonymised escalation report is generated). **Sessions** shows live
transcripts as real users message the bot.

### VPS database access

```bash
ssh root@157.230.232.223
sudo -u postgres psql -d wazi_db
# Useful queries:
#   SELECT count(*) FROM sources;
#   SELECT count(*) FROM chunks;
#   SELECT count(*) FROM messages;
#   \dt   (list all tables)
```

### Point local apps at VPS database (optional)

**Not currently enabled.** PostgreSQL on the VPS listens on `127.0.0.1:5432`
only, and `ufw` allows just ports 22/80/443 — there is no 5432 rule. Local
`.env` therefore still points at the Docker instance
(`postgresql://wazi:wazi_password@localhost:5432/wazi_db`).

To enable remote access you must, on the VPS:

```bash
# 1. Bind PostgreSQL to the public interface
sudo sed -i "s/^#listen_addresses.*/listen_addresses = '*'/" /etc/postgresql/16/main/postgresql.conf

# 2. Allow only your IP in client auth
sudo sh -c 'echo "host wazi_db wazi YOUR_PUBLIC_IP/32 scram-sha-256" >> /etc/postgresql/16/main/pg_hba.conf'

# 3. Open 5432 for your IP only
sudo ufw allow from YOUR_PUBLIC_IP to any port 5432 proto tcp

# 4. Reload
sudo systemctl restart postgresql
```

Then set `.env` locally:

```
DATABASE_URL=postgresql://wazi:wazi_password@157.230.232.223:5432/wazi_db
```

**Recommended instead — SSH tunnel** (no firewall changes, encrypted, no
internet exposure of PostgreSQL):

```powershell
# Terminal A (keep running): tunnel local 5433 -> VPS localhost:5432
ssh -N -L 5433:localhost:5432 root@157.230.232.223

# Terminal B: point .env at the tunnel
#   DATABASE_URL=postgresql://wazi:wazi_password@localhost:5433/wazi_db
```

For scraping specifically, prefer running the scraper **on the VPS** (see
"Full VPS startup sequence") — no remote database access is needed at all.

---

## Smoke Tests

### Test 1: Health check (local API)
```powershell
curl http://localhost:8502/health
# Expected: {"status":"healthy","service":"wazi-api"}
```

### Test 2: Health check (VPS)
```powershell
curl http://157.230.232.223/health
# Expected: {"status":"healthy","service":"wazi-api"}
```

### Test 3: Admin auth required
```powershell
curl http://localhost:8502/api/sources
# Expected: 401 Unauthorized
```

### Test 4: Admin auth succeeds
```powershell
curl -H "Authorization: Bearer admin" http://localhost:8502/api/sources
# Expected: {"sources": [...], "total": 9}
```

### Test 5: WhatsApp webhook (dev mode — logs to console)
```powershell
curl -X POST http://localhost:8502/whatsapp/incoming -d "from=+254700000001" -d "text=Kaunti ya Nakuru inapokea pesa ngapi?"
# Expected: 200 — check Sessions tab in admin dashboard for the new message
```

### Test 6: Stats endpoint
```powershell
curl -H "Authorization: Bearer admin" http://localhost:8502/api/stats
# Expected: {"total_sources": 9, "total_chunks": 0, "total_messages": ..., ...}
```

### Test 7: Full CRUD on sources
```powershell
.\venv\Scripts\python.exe scripts/test_admin_api.py
# Expected: ALL TESTS PASSED (uses localhost:8000 — update if needed)
```

### Test 8: Citizen chat app (local only)
Open `http://localhost:8501`, ask:
- "Kaunti ya Nakuru inapokea pesa ngapi kutoka kwa Serikali ya Kitaifa?"
- "What did the Auditor-General find about pending bills?"
- "Mradi wa Keringet uligharimu pesa ngapi?"
- "Je, unaweza kuniambia kuhusu mazingira ya Mars?" → "sina taarifa za kutosha"

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DEEPSEEK_API_KEY` | Yes | — | DeepSeek API key for LLM calls |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com` | LLM provider endpoint |
| `DEEPSEEK_MODEL` | No | `deepseek-chat` | Model name |
| `DATABASE_URL` | No | `postgresql://wazi:wazi_password@localhost:5432/wazi_db` | PostgreSQL connection |
| `AT_API_KEY` | No | — | Africa's Talking API key (WhatsApp) |
| `AT_USERNAME` | No | `sandbox` | AT username (sandbox = dev mode) |
| `WA_BOT_NUMBER` | No | — | WhatsApp bot phone number |
| `ID_SALT` | Yes | — | HMAC-SHA256 salt for wa_id hashing |
| `ADMIN_PASSWORD` | Yes | `admin` | Dashboard and API admin auth |
| `WAZI_API_URL` | No | `http://localhost:8000` | Admin dashboard → API URL |
| `CHAT_RETENTION_DAYS` | No | `90` | Auto-delete old chat sessions |
| `DISPUTE_RETENTION_DAYS` | No | `365` | Auto-delete old disputes |

---

## Current Known Issues

| Issue | Impact | Resolution |
|-------|--------|------------|
| ~~pgvector empty / CoB BIRR failing~~ | — | **Fixed** (`fix/county-section-extraction`, commit `6de67b7`): 9/9 sources ingest (702 chunks). County resolved against a canonical 47-county list; body text no longer mis-detected as headings; BIRR edition (Q1/Half/Nine-Months) disambiguated |
| `build_corpus()` / `pipeline.py` are hackathon-era | They write `chunks.json` and hardcoded paths, not pgvector | Replaced by `src/ingestion/scraper.py`; keep only for offline demo |
| Admin dashboard default port is 8000 | `WAZI_API_URL` must be set in `.env` | Added `WAZI_API_URL=http://localhost:8502` to `.env` |
| ONNX model download on first run | ~8 min wait for 127 MB download | One-time; subsequent runs use cached model |
| VPS: uvicorn on port 8000 (behind Nginx) | Local uses 8502, VPS uses 8000 | Keep separate — VPS has its own `.env` and port convention |
