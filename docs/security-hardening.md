# VPS Security Hardening — Wazi

> Day 10–12 checklist for `157.230.232.223` (Ubuntu 24.04, 1 GB RAM).
> Run order: `vps_setup.sh` first, then `harden_vps.sh`, then the manual steps.

## Posture in one line

FastAPI (`:8000`) and PostgreSQL (`:5432`) are **never exposed to the
internet** — only Nginx (`:80`, later `:443`) and SSH (`:22`) are. Everything
citizen-facing goes through Nginx; the app talks to Postgres over localhost.

## What each script does

| Concern | Handled by | Detail |
|---------|-----------|--------|
| Uvicorn not public | `vps_setup.sh` | binds `127.0.0.1:8000`, Nginx proxies it |
| Reverse proxy | `vps_setup.sh` | Nginx `:80` → `127.0.0.1:8000` |
| Firewall | both | UFW allows only `22/80/443`; `8000` + `5432` internal |
| Low-RAM Postgres | `vps_setup.sh` | `shared_buffers=128MB`, swap file 2 GB |
| Secrets file perms | `harden_vps.sh` | `.env` → `600 root:root` |
| Postgres localhost bind | `harden_vps.sh` | asserts `listen_addresses='localhost'` |
| SSH brute-force | `harden_vps.sh` | `fail2ban` |
| Security patches | `harden_vps.sh` | `unattended-upgrades` |
| Webhook flood cap | `harden_vps.sh` | Nginx `limit_req_zone` (see "Apply rate limit") |

## Manual step 1 — SSH key-only auth  ⚠️ lockout risk

**Do this carefully — a wrong move locks you out of the VPS permanently.**

1. On **your laptop**, ensure you have a key: `ssh-keygen -t ed25519` (if none).
2. Copy it up: `ssh-copy-id root@157.230.232.223`.
3. **Open a SECOND terminal and prove the key works** —
   `ssh root@157.230.232.223` should log in with **no password prompt**.
   Keep this session open.
4. Only now, in that session, edit `/etc/ssh/sshd_config`:
   ```
   PasswordAuthentication no
   PermitRootLogin prohibit-password
   ```
5. `systemctl restart ssh`. **Test a brand-new connection before closing your
   working session.** If it fails, revert in the still-open session.

> Skipping step 3 is how people brick a VPS. Never disable password auth from
> your only open connection.

## Manual step 2 — HTTPS (needs a domain first)

Let's Encrypt **will not issue a certificate for a bare IP**, so HTTPS needs a
hostname pointing at `157.230.232.223`.

1. Point a domain/subdomain (e.g. `api.wazi.<something>`) `A` record at the IP.
2. Set `server_name` in `/etc/nginx/sites-available/wazi` to that hostname.
3. `apt install -y certbot python3-certbot-nginx`
4. `certbot --nginx -d api.wazi.<something>` — auto-configures `:443` + renewal.
5. Update the Africa's Talking webhook URL and `WAZI_API_URL` to `https://…`.

Until a domain exists, plain `:80` behind the firewall is the MVP posture —
acceptable for the demo, not for real citizen traffic.

## Apply the webhook rate limit

`harden_vps.sh` declares the zone; wire it into the location block once:

```nginx
# in /etc/nginx/sites-available/wazi, inside `location / { … }`
limit_req zone=wazi_webhook burst=20 nodelay;
```
Then `nginx -t && systemctl reload nginx`. This is network-level defence in
depth on top of the app-level anti-bot guards
(`src/api/middleware/anti_bot.py`).

## Secrets hygiene

- `.env` is gitignored and has **never** been committed — verified. Keep it
  that way: never `git add -f .env`.
- `ID_SALT` must be a real random value on the VPS
  (`python3 -c "import secrets; print(secrets.token_hex(32))"`), set **once**
  at setup. Changing it later detaches every existing hashed citizen id.
- The DeepSeek key is a **shared hackathon key** — it lives only in `.env`
  (local + VPS) and Streamlit Cloud secrets, never in the repo.

## Demo-day posture (honest summary)

Shippable now: firewall, reverse proxy, internal-only app + DB, fail2ban,
auto-patching, secrets locked down, rate limiting. **Deferred** (documented,
not done): HTTPS (blocked on a domain) and SSH key-only auth (manual, to avoid
lockout). Both are one step away and written up above.
