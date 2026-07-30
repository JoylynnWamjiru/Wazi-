# Deploying Wazi (Streamlit Community Cloud + companion stub API)

Three services, two platforms. The two Streamlit apps go on **Streamlit
Community Cloud**; the FastAPI **dev stub API** cannot run there (Streamlit
Cloud only runs `streamlit run ...`), so it goes on a small container host
(**Render** free tier used below; Railway/Fly work the same way).

```
Citizen chat  (src/app/streamlit_app.py)   -> Streamlit Community Cloud
Admin dashboard (src/admin/dashboard.py)   -> Streamlit Community Cloud
Dev stub API  (scripts/dev_stub_api.py)    -> Render (or Railway/Fly)
                                               dashboard talks to it via WAZI_API_URL
```

> `data/chunks.json` is gitignored. The citizen app rebuilds it automatically
> on first boot from the committed PDFs (`_warm_pipeline` in `streamlit_app.py`),
> so no manual step is needed on deploy.

## Before you start

- **Rotate the DeepSeek API key.** The old one was shared in chat. Generate a
  new key and only ever paste it into a provider's *secrets* UI — never the repo.
- Deploy from a branch you control (this `deploy/streamlit-cloud` branch, or
  `main` once merged). Streamlit Cloud lets you pick the branch per app.

## Step 1 — Dev stub API on Render

1. render.com -> New -> **Web Service** -> connect the GitHub repo.
2. Runtime: Python. **Build command:** `pip install fastapi "uvicorn[standard]"`
   **Start command:** `uvicorn scripts.dev_stub_api:app --host 0.0.0.0 --port $PORT`
3. Environment variable: `ADMIN_PASSWORD` = (a strong value you choose).
4. Deploy. Note the public URL, e.g. `https://wazi-stub.onrender.com`.
5. Verify: open `<url>/health` — expect `{"status":"healthy",...}`.

   Note: Render's free tier sleeps after inactivity; the first request after
   idle takes ~30–50s to wake. Hit `/health` once right before the demo.

## Step 2 — Citizen chat on Streamlit Community Cloud

1. share.streamlit.io -> **New app** -> pick the repo + branch.
2. **Main file path:** `src/app/streamlit_app.py`
3. **Secrets** (Advanced settings -> Secrets), TOML format:
   ```toml
   DEEPSEEK_API_KEY = "sk-...new-rotated-key..."
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   DEEPSEEK_MODEL = "deepseek-chat"
   ```
4. Deploy. First boot is slow: it installs deps, rebuilds the corpus, and
   downloads the ~470 MB ONNX model. Watch the logs.

## Step 3 — Admin dashboard on Streamlit Community Cloud

1. New app -> same repo + branch.
2. **Main file path:** `src/admin/dashboard.py`
3. **Secrets:**
   ```toml
   WAZI_API_URL = "https://wazi-stub.onrender.com"   # the Render URL from Step 1
   ```
4. Deploy. Log in with the `ADMIN_PASSWORD` you set on Render in Step 1.

## Known risks / things to check

- **RAM.** Streamlit Community Cloud's free tier is memory-limited. The ONNX
  model + FAISS index for the citizen app may be tight. If the app restarts or
  shows a resource error, that's the cause — the fallback for the pitch is to
  run the citizen app locally. Verify by loading the deployed URL and asking a
  golden question before relying on it.
- **Secrets as env vars.** `config.py` and `dashboard.py` read secrets via
  `os.getenv`. Streamlit Cloud exposes `st.secrets` entries as environment
  variables, so this works — but confirm on first boot that answers are grounded
  (not the "Samahani, sina jibu la uhakika" fallback, which would mean the key
  isn't being read).
- **Requirements weight.** The root `requirements.txt` includes the full
  backend stack (fastapi, sqlalchemy, psycopg2, pgvector, apscheduler…) that the
  Streamlit apps don't need. It installs fine (all have Linux wheels) but slows
  the build. Trim later if build time is a problem.
- **This deploys the stub, not the real backend.** The dashboard shows
  consistent sample data, not live citizen traffic. That is the intended,
  honest demo configuration.

## Post-deploy smoke test (do this before the pitch)

1. Citizen app: ask "Serikali ya Kaunti ya Nakuru inatarajia kupokea kiasi gani
   kutoka kwa Serikali ya Kitaifa?" -> expect Kshs 14.13 bilioni citing
   `nakuru_birr_q1.pdf, page 2`.
2. Citizen app: ask an out-of-corpus question -> expect "sina taarifa za kutosha".
3. Dashboard: log in, confirm all five tabs render and the sidebar shows
   "API healthy".
